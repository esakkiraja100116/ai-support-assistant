import json
import logging

from sqlalchemy.orm import Session

from app.models import Transaction, User
from app.schemas.chat import ChatMessage, ChatResponse
from app.schemas.transactions import TransactionOut
from app.services import kb_service, llm_client, transaction_service
from app.services.tools_schema import ALL_TOOLS, NO_SINGLE_MATCH, RESOLVE_TRANSACTION, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

NO_INFO_MESSAGE = (
    "I don't have enough information in our knowledge base to answer that. "
    "Could you rephrase, or ask about something else?"
)

SELECTION_MESSAGES = {
    "list_requested": "Here are your recent transactions:",
    "ambiguous": "Which transaction are you referring to?",
}


def chat_turn(db: Session, user: User, message: str, history: list[ChatMessage]) -> ChatResponse:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        return _handle_knowledge_base(db, call, message)

    if tool_name == "get_recent_transactions":
        return _handle_recent_transactions(db, user, message, history)

    logger.error("Model requested unsupported tool: %s", tool_name)
    return ChatResponse.error("unsupported_tool", "The assistant tried to use an unsupported action.")


def _handle_knowledge_base(db: Session, call, fallback_query: str) -> ChatResponse:
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        args = {}
    query = args.get("query") or fallback_query

    try:
        result = kb_service.search_knowledge_base(db, query)
    except Exception:
        logger.exception("Knowledge base search failed")
        return ChatResponse.error("kb_unavailable", "Search is temporarily unavailable. Please try again.")

    if not result.grounded:
        return ChatResponse.text_answer(NO_INFO_MESSAGE, grounded=False)

    context = "\n\n".join(f"Q: {a.question}\nA: {a.answer}" for a in result.articles)
    grounded_messages = [
        {
            "role": "system",
            "content": (
                "Answer the customer's question using ONLY the following approved support "
                "content. Do not add information that is not present here. Be concise and "
                "friendly.\n\n" + context
            ),
        },
        {"role": "user", "content": query},
    ]
    try:
        final = llm_client.chat_completion(grounded_messages)
    except Exception:
        logger.exception("Chat completion (grounded answer) failed")
        return ChatResponse.error("llm_unavailable", "The assistant is temporarily unavailable. Please try again.")

    return ChatResponse.text_answer(
        final.content or NO_INFO_MESSAGE,
        grounded=True,
        sources=[a.id for a in result.articles],
    )


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
    resolve_messages = [
        {
            "role": "system",
            "content": (
                "Here is the customer's recent transaction history as JSON, ordered most "
                "recent first (this is the order it would be shown to them):\n"
                + json.dumps([t.model_dump(mode="json") for t in txn_out])
                + "\n\nIf the customer's message clearly identifies exactly one of these "
                "transactions, call resolve_transaction with its id. Otherwise call "
                "no_single_match. You must call exactly one of these two tools - never answer "
                "in plain text, and never describe, list, or summarize the transactions yourself."
            ),
        },
    ]
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
                    explanation = explain_transaction(chosen)
                    return ChatResponse.transaction_explanation(explanation, chosen)
            elif call.function.name == "no_single_match":
                selection_message = SELECTION_MESSAGES.get(args.get("reason"), SELECTION_MESSAGES["ambiguous"])
    except Exception:
        logger.exception("Transaction resolution call failed; falling back to selection list")

    return ChatResponse.transaction_selection(selection_message, txn_out)


def explain_transaction(transaction: Transaction) -> str:
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
    messages = [
        {
            "role": "system",
            "content": (
                "Using ONLY the following JSON transaction record, write a short, friendly "
                "explanation for the customer. Do not invent a status, amount, reason, or date "
                "that is not present in the JSON.\n\n" + json.dumps(record)
            ),
        },
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
