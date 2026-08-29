import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Transaction, User
from app.schemas.chat import ChatMessage, ChatResponse
from app.schemas.transactions import TransactionOut
from app.services import kb_service, llm_client, prompts, session_log, transaction_service
from app.services.tools_schema import (
    ALL_TOOLS,
    ANSWER_FROM_KB,
    INSUFFICIENT_KB_INFO,
    NO_SINGLE_MATCH,
    RESOLVE_TRANSACTIONS,
)

logger = logging.getLogger(__name__)

NO_INFO_MESSAGE = (
    "I don't have enough information in our knowledge base to answer that. "
    "Could you rephrase, or ask about something else?"
)

ESCALATION_MESSAGE = "I'd be happy to connect you with a human support agent who can help further."

SELECTION_MESSAGES = {
    "list_requested": "Here are your recent transactions:",
    "ambiguous": "Which transaction are you referring to?",
}


def _consecutive_trailing_declines(history: list[ChatMessage]) -> int:
    """Counts consecutive KB declines at the end of the conversation, most-recent
    assistant turn first. A "decline" is detected by an exact match against
    NO_INFO_MESSAGE - a fixed constant this app itself always returns verbatim
    for that case, never LLM-authored prose - so this is a reliable structural
    check, not fragile text parsing. Resets to 0 as soon as a real answer
    appears, so a customer who gets helped in between starts fresh."""
    count = 0
    for msg in reversed(history):
        if msg.role != "assistant":
            continue
        if msg.content.strip() == NO_INFO_MESSAGE:
            count += 1
        else:
            break
    return count


def chat_turn(
    db: Session,
    user: User,
    message: str,
    history: list[ChatMessage],
    conversation_id: str | None = None,
    judgment_model: str | None = None,
    judgment_reasoning_effort: str | None = None,
) -> ChatResponse:
    # `judgment_model`/`judgment_reasoning_effort` only affect the KB answer_from_kb/
    # insufficient_kb_info call (see _handle_knowledge_base) - for controlled experiments,
    # not something any real request path sets.
    session_id = conversation_id or f"anon-{uuid.uuid4()}"
    with session_log.session_scope(session_id) as session:
        session.log("user_message", user_id=str(user.id), content=message)
        response = _chat_turn(db, user, message, history, judgment_model, judgment_reasoning_effort)
        session.log("final_response", type=response.type.value, message=response.message, data=response.data)
        return response


def _chat_turn(
    db: Session,
    user: User,
    message: str,
    history: list[ChatMessage],
    judgment_model: str | None = None,
    judgment_reasoning_effort: str | None = None,
) -> ChatResponse:
    # Checked before any LLM call: two (settings.escalation_decline_threshold)
    # consecutive KB declines in a row means this conversation has hit a wall -
    # offer a human agent instead of a third generic "I don't know" (also saves
    # the cost of the routing call on this turn). Bonus feature from the
    # assignment's "human-agent escalation when confidence is low" idea.
    if _consecutive_trailing_declines(history) >= settings.escalation_decline_threshold:
        return ChatResponse.escalate(ESCALATION_MESSAGE, settings.support_contact_email)

    system_prompt = prompts.render("system_prompt.j2", display_name=user.display_name)
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": h.role, "content": h.content} for h in history]
    messages.append({"role": "user", "content": message})

    try:
        assistant_message = llm_client.chat_completion(messages, tools=ALL_TOOLS, tool_choice="auto")
    except Exception:
        logger.exception("Chat completion (intent routing) failed")
        return ChatResponse.error("llm_unavailable", "The assistant is temporarily unavailable. Please try again.")

    tool_calls = getattr(assistant_message, "tool_calls", None)
    if not tool_calls:
        return ChatResponse.text_answer(assistant_message.content or "How can I help you today?", grounded=True)

    call = tool_calls[0]
    tool_name = call.function.name

    if tool_name == "search_knowledge_base":
        return _handle_knowledge_base(db, user, message, judgment_model, judgment_reasoning_effort)

    if tool_name == "get_recent_transactions":
        return _handle_recent_transactions(db, user, message, history)

    if tool_name == "request_human_agent":
        return ChatResponse.escalate(ESCALATION_MESSAGE, settings.support_contact_email)

    logger.error("Model requested unsupported tool: %s", tool_name)
    return ChatResponse.error("unsupported_tool", "The assistant tried to use an unsupported action.")


def _handle_knowledge_base(
    db: Session,
    user: User,
    query: str,
    judgment_model: str | None = None,
    judgment_reasoning_effort: str | None = None,
) -> ChatResponse:
    # `judgment_model`/`judgment_reasoning_effort` override which model (and, for
    # reasoning-family models, effort level) makes the answer_from_kb/insufficient_kb_info
    # call, for controlled experiments comparing judgment quality across models on a fixed
    # question set (scripts/eval_judgment_model.py) - not something any real request path sets.
    # Always search on the customer's own message verbatim - letting the model
    # rephrase it before searching measurably hurt retrieval (see scripts/eval_kb.py):
    # rewording even slightly (dropping "my", "How can I" -> "how to") was enough to
    # push genuine matches below the similarity threshold in most tested cases.
    try:
        result = kb_service.search_knowledge_base(db, query)
    except Exception:
        logger.exception("Knowledge base search failed")
        return ChatResponse.error("kb_unavailable", "Search is temporarily unavailable. Please try again.")

    if not result.articles:
        return ChatResponse.text_answer(NO_INFO_MESSAGE, grounded=False)

    # Relevance is judged by the model reading the actual content, not by the raw
    # similarity ranking alone - a compound question ("do I need to pay extra if I
    # purchase gold?") can score higher against an unrelated article ("How do I buy
    # gold?") than the one that actually answers it ("What fees do you charge?"),
    # since one clause of the question dominates the embedding. Widening the candidate
    # pool (kb_service's top_k) and having the model pick the real answer out of it is
    # far more robust than any single cosine cutoff.
    articles_by_id = {a.id: a for a in result.articles}
    system_prompt = prompts.render("kb_judgment.j2", articles=result.articles, display_name=user.display_name)
    grounded_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]
    try:
        resolved = llm_client.chat_completion(
            grounded_messages,
            tools=[ANSWER_FROM_KB, INSUFFICIENT_KB_INFO],
            tool_choice="required",
            model=judgment_model,
            reasoning_effort=judgment_reasoning_effort,
        )
        for call in getattr(resolved, "tool_calls", None) or []:
            args = json.loads(call.function.arguments or "{}")
            if call.function.name == "answer_from_kb" and args.get("answer"):
                cited_ids = [i for i in args.get("source_article_ids", []) if i in articles_by_id]
                return ChatResponse.text_answer(args["answer"], grounded=True, sources=cited_ids)
            if call.function.name == "insufficient_kb_info":
                return ChatResponse.text_answer(NO_INFO_MESSAGE, grounded=False)
    except Exception:
        logger.exception("Chat completion (grounded answer) failed")
        return ChatResponse.error("llm_unavailable", "The assistant is temporarily unavailable. Please try again.")

    return ChatResponse.text_answer(NO_INFO_MESSAGE, grounded=False)


def _handle_recent_transactions(
    db: Session, user: User, message: str, history: list[ChatMessage]
) -> ChatResponse:
    try:
        transactions = transaction_service.get_recent_transactions(db, user)
    except Exception:
        logger.exception("Fetching recent transactions failed")
        return ChatResponse.error("db_unavailable", "We couldn't load your transactions. Please try again.")

    if not transactions:
        return ChatResponse.text_answer("You don't have any recent transactions yet.", grounded=True)

    txn_out = [TransactionOut.model_validate(t) for t in transactions]
    txn_by_id = {t.id: t for t in transactions}

    # Try to resolve a single specific transaction from the customer's own wording before
    # falling back to a card list. This list is already scoped to `user`, so whichever id
    # the model picks (if any) can only ever be one of the authenticated user's own records.
    resolve_system_prompt = prompts.render(
        "transaction_resolve.j2",
        transactions_json=json.dumps([t.model_dump(mode="json") for t in txn_out]),
        display_name=user.display_name,
    )
    resolve_messages = [{"role": "system", "content": resolve_system_prompt}]
    resolve_messages += [{"role": h.role, "content": h.content} for h in history]
    resolve_messages.append({"role": "user", "content": message})

    selection_message = SELECTION_MESSAGES["ambiguous"]
    try:
        resolved = llm_client.chat_completion(
            resolve_messages,
            tools=[RESOLVE_TRANSACTIONS, NO_SINGLE_MATCH],
            tool_choice="required",
            model=settings.resolve_model,
            reasoning_effort=settings.resolve_reasoning_effort,
        )
        for call in getattr(resolved, "tool_calls", None) or []:
            args = json.loads(call.function.arguments or "{}")
            if call.function.name == "resolve_transactions":
                # Only ids that are actually in this user's own fetched list count - a
                # hallucinated or injected id is silently dropped, never looked up fresh.
                ids = [i for i in args.get("transaction_ids", []) if i in txn_by_id]
                if len(ids) == 1:
                    chosen = txn_by_id[ids[0]]
                    explanation = explain_transaction(chosen, user.display_name)
                    return ChatResponse.transaction_explanation(explanation, chosen)
                if len(ids) > 1:
                    chosen = [txn_by_id[i] for i in ids]
                    explanation = explain_transactions(chosen, message, user.display_name)
                    return ChatResponse.transaction_summary(explanation, chosen)
                # ids empty (every id hallucinated) - fall through to the safe list below
            elif call.function.name == "no_single_match":
                selection_message = SELECTION_MESSAGES.get(args.get("reason"), SELECTION_MESSAGES["ambiguous"])
    except Exception:
        logger.exception("Transaction resolution call failed; falling back to selection list")

    return ChatResponse.transaction_selection(selection_message, txn_out)


def _transaction_record(transaction: Transaction) -> dict:
    return {
        "id": transaction.id,
        "type": transaction.type,
        "product": transaction.product,
        "amount": float(transaction.amount),
        "status": transaction.status,
        "failure_reason": transaction.failure_reason,
        "payment_method": transaction.payment_method,
        "created_at": transaction.created_at.isoformat(),
        "updated_at": transaction.updated_at.isoformat(),
    }


def explain_transaction(transaction: Transaction, display_name: str) -> str:
    """Turns one already-authorized, already-fetched transaction record into a
    friendly explanation. Deliberately not routed through intent classification:
    the user's card click is already an unambiguous, explicit action."""
    system_prompt = prompts.render(
        "transaction_explain.j2", record_json=json.dumps(_transaction_record(transaction)), display_name=display_name
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Explain this transaction to me."},
    ]
    try:
        final = llm_client.chat_completion(messages)
        return final.content or _fallback_explanation(transaction)
    except Exception:
        logger.exception("Chat completion (transaction explanation) failed")
        return _fallback_explanation(transaction)


def explain_transactions(transactions: list[Transaction], original_question: str, display_name: str) -> str:
    """Same idea as explain_transaction, generalized to several already-authorized,
    already-fetched records at once (e.g. "my last 3 transactions, which failed and
    why, with payment method for each") - one grounded answer covering all of them,
    never inventing a field not present in the JSON."""
    records_json = json.dumps([_transaction_record(t) for t in transactions])
    system_prompt = prompts.render(
        "transactions_summary.j2",
        records_json=records_json,
        original_question=original_question,
        display_name=display_name,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": original_question},
    ]
    try:
        final = llm_client.chat_completion(messages)
        return final.content or _fallback_summary(transactions)
    except Exception:
        logger.exception("Chat completion (transaction summary) failed")
        return _fallback_summary(transactions)


def _fallback_explanation(transaction: Transaction) -> str:
    text = f"Your {transaction.type} of {transaction.product} for {transaction.amount} is {transaction.status}."
    if transaction.failure_reason:
        text += f" Reason: {transaction.failure_reason}."
    return text


def _fallback_summary(transactions: list[Transaction]) -> str:
    return " ".join(_fallback_explanation(t) for t in transactions)
