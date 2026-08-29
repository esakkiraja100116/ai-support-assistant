import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.models import Transaction, User
from app.schemas.chat import ChatMessage, ChatResponse
from app.schemas.transactions import TransactionOut
from app.services import kb_service, llm_client, prompts, session_log, transaction_service
from app.services.tools_schema import (
    ALL_TOOLS,
    ANSWER_FROM_KB,
    INSUFFICIENT_KB_INFO,
    NO_SINGLE_MATCH,
    RESOLVE_TRANSACTION,
)

logger = logging.getLogger(__name__)

NO_INFO_MESSAGE = (
    "I don't have enough information in our knowledge base to answer that. "
    "Could you rephrase, or ask about something else?"
)

SELECTION_MESSAGES = {
    "list_requested": "Here are your recent transactions:",
    "ambiguous": "Which transaction are you referring to?",
}


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
            resolve_messages, tools=[RESOLVE_TRANSACTION, NO_SINGLE_MATCH], tool_choice="required"
        )
        for call in getattr(resolved, "tool_calls", None) or []:
            args = json.loads(call.function.arguments or "{}")
            if call.function.name == "resolve_transaction":
                chosen = txn_by_id.get(args.get("transaction_id"))
                if chosen is not None:
                    explanation = explain_transaction(chosen, user.display_name)
                    return ChatResponse.transaction_explanation(explanation, chosen)
            elif call.function.name == "no_single_match":
                selection_message = SELECTION_MESSAGES.get(args.get("reason"), SELECTION_MESSAGES["ambiguous"])
    except Exception:
        logger.exception("Transaction resolution call failed; falling back to selection list")

    return ChatResponse.transaction_selection(selection_message, txn_out)


def explain_transaction(transaction: Transaction, display_name: str) -> str:
    """Turns one already-authorized, already-fetched transaction record into a
    friendly explanation. Deliberately not routed through intent classification:
    the user's card click is already an unambiguous, explicit action."""
    record = {
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
    system_prompt = prompts.render("transaction_explain.j2", record_json=json.dumps(record), display_name=display_name)
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


def _fallback_explanation(transaction: Transaction) -> str:
    text = f"Your {transaction.type} of {transaction.product} for {transaction.amount} is {transaction.status}."
    if transaction.failure_reason:
        text += f" Reason: {transaction.failure_reason}."
    return text
