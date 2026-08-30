import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Transaction, User
from app.schemas.chat import ChatMessage, ChatResponse
from app.schemas.redemptions import RedemptionTrackingOut
from app.schemas.transactions import TransactionOut
from app.services import kb_service, llm_client, prompts, redemption_service, session_log, tracing, tracking_service, transaction_service
from app.services.redemption_service import RedemptionOrderRecord
from app.services.turn_metrics import TurnMetrics
from app.services.tools_schema import (
    ALL_TOOLS,
    ALL_TOOLS_STREAM,
    ANSWER_FROM_KB,
    ANSWER_FROM_KB_JUDGE,
    INSUFFICIENT_KB_INFO,
    NO_SINGLE_MATCH,
    NO_SINGLE_REDEMPTION_MATCH,
    RESOLVE_REDEMPTION_ORDER,
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

REDEMPTION_SELECTION_MESSAGE = "Which order would you like to track?"


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
    with tracing.tracer.start_as_current_span("chat_turn") as root_span:
        root_span.set_attribute("conversation.id", session_id)
        root_span.set_attribute("user.id", str(user.id))
        root_span.set_attribute("user.message", message[:500])
        with session_log.session_scope(session_id) as session:
            session.log("user_message", user_id=str(user.id), content=message)
            response = _chat_turn(db, user, message, history, judgment_model, judgment_reasoning_effort)
            session.log("final_response", type=response.type.value, message=response.message, data=response.data)
        root_span.set_attribute("response.type", response.type.value)
        root_span.set_attribute("response.message", response.message[:500])
        return response


def _route_intent(
    user: User,
    message: str,
    history: list[ChatMessage],
    model: str | None = None,
    reasoning_effort: str | None = None,
    tools: list[dict] | None = None,
    metrics: TurnMetrics | None = None,
):
    """The top-level intent-routing call, isolated as its own function so it
    can be exercised directly (e.g. scripts/eval_routing_model.py) with a
    different model, for controlled experiments - same idea as
    _handle_knowledge_base's judgment_model override, mirrored here since
    this is the other place a wrong LLM call decision has real consequences.
    `model`/`reasoning_effort` are None for every real request path; only
    eval scripts pass them.

    tool_choice="required" (over ALL_TOOLS, which includes respond_directly
    for genuine small talk/capability gaps) rather than "auto" - removing the
    free-form-answer escape hatch entirely, the same defensive pattern
    _handle_knowledge_base/_handle_recent_transactions already use. Measured
    via scripts/eval_routing_model.py: this alone fixed 4/5 known routing
    misses with gpt-4o-mini, where "auto" fixed 0/5."""
    system_prompt = prompts.render("system_prompt.j2", display_name=user.display_name)
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": h.role, "content": h.content} for h in history]
    messages.append({"role": "user", "content": message})
    kwargs: dict = {
        "tools": tools or ALL_TOOLS,
        "tool_choice": "required",
        "model": model,
        "reasoning_effort": reasoning_effort,
    }
    # `metrics` is only ever passed by the streaming path (StreamedChatTurn) -
    # omitted entirely otherwise, so existing test doubles for
    # llm_client.chat_completion (fixed signatures, no `metrics` param) keep
    # working unmodified.
    if metrics is not None:
        kwargs["metrics"] = metrics
    with tracing.tracer.start_as_current_span("route_intent"):
        return llm_client.chat_completion(messages, **kwargs)


def _chat_turn(
    db: Session,
    user: User,
    message: str,
    history: list[ChatMessage],
    judgment_model: str | None = None,
    judgment_reasoning_effort: str | None = None,
    routing_model: str | None = None,
    routing_reasoning_effort: str | None = None,
) -> ChatResponse:
    # Checked before any LLM call: two (settings.escalation_decline_threshold)
    # consecutive KB declines in a row means this conversation has hit a wall -
    # offer a human agent instead of a third generic "I don't know" (also saves
    # the cost of the routing call on this turn). Bonus feature from the
    # assignment's "human-agent escalation when confidence is low" idea.
    if _consecutive_trailing_declines(history) >= settings.escalation_decline_threshold:
        return ChatResponse.escalate(ESCALATION_MESSAGE, settings.support_contact_email)

    try:
        assistant_message = _route_intent(user, message, history, routing_model, routing_reasoning_effort)
    except Exception:
        logger.exception("Chat completion (intent routing) failed")
        return ChatResponse.error("llm_unavailable", "The assistant is temporarily unavailable. Please try again.")

    tool_calls = getattr(assistant_message, "tool_calls", None)
    if not tool_calls:
        # Defensive only - tool_choice="required" means the API should always
        # return a tool call; this is a fallback in case that contract is
        # ever violated, not an expected path.
        return ChatResponse.text_answer(assistant_message.content or "How can I help you today?", grounded=True)

    # A compound question ("check my transaction AND tell me the fees") makes
    # the model correctly issue multiple tool calls in one response - dispatch
    # every one of them and merge the results, rather than acting on only
    # tool_calls[0] and silently dropping the rest (same class of bug as the
    # answer_from_kb merge above, one level up).
    if any(c.function.name == "request_human_agent" for c in tool_calls):
        # Escalation bypasses everything else, per request_human_agent's own
        # tool description ("regardless of whether their underlying question
        # could otherwise be answered") - unaffected by anything else requested.
        return ChatResponse.escalate(ESCALATION_MESSAGE, settings.support_contact_email)

    real_calls = _dedupe_real_tool_calls(tool_calls)
    calls_to_run = real_calls or tool_calls  # falls back to e.g. a lone respond_directly

    responses: list[ChatResponse] = []
    for call in calls_to_run:
        tool_name = call.function.name
        if tool_name == "search_knowledge_base":
            with tracing.tracer.start_as_current_span("kb_search_and_judge"):
                responses.append(_handle_knowledge_base(db, user, message, judgment_model, judgment_reasoning_effort))
        elif tool_name == "get_recent_transactions":
            with tracing.tracer.start_as_current_span("transaction_lookup_and_resolve"):
                responses.append(_handle_recent_transactions(db, user, message, history))
        elif tool_name == "get_ongoing_redemptions":
            with tracing.tracer.start_as_current_span("redemption_lookup_and_resolve"):
                responses.append(_handle_redemption_tracking(db, user, message, history))
        elif tool_name == "respond_directly":
            args = json.loads(call.function.arguments or "{}")
            responses.append(ChatResponse.text_answer(args.get("reply") or "How can I help you today?", grounded=True))
        else:
            logger.error("Model requested unsupported tool: %s", tool_name)
            responses.append(ChatResponse.error("unsupported_tool", "The assistant tried to use an unsupported action."))

    return responses[0] if len(responses) == 1 else _merge_responses(responses)


def _dedupe_real_tool_calls(tool_calls) -> list:
    """Filters to search_knowledge_base/get_recent_transactions/
    get_ongoing_redemptions calls, keeping only the FIRST occurrence of each
    distinct tool name. All three tools take no arguments (each always
    fetches/searches the same thing for a given turn), so the model calling
    the same one twice is always redundant - and, for KB specifically,
    running it twice independently produces two full, overlapping answers
    that _merge_responses would then concatenate, duplicating everything
    rather than combining two distinct topics. get_ongoing_redemptions is
    included here for the same reason - without it, a duplicated call would
    reproduce this exact class of bug for redemption tracking."""
    seen: set[str] = set()
    result = []
    for call in tool_calls:
        name = call.function.name
        if name in ("search_knowledge_base", "get_recent_transactions", "get_ongoing_redemptions") and name not in seen:
            result.append(call)
            seen.add(name)
    return result


def _merge_responses(responses: list[ChatResponse]) -> ChatResponse:
    """Combines multiple tool-call results from one turn into a single
    ChatResponse. Prefers a transaction-shaped response as the base (its
    `type`/`data` is what the frontend needs to render cards/details),
    appending every other response's message text after it - so a compound
    "check my transaction and tell me the fees" question gets one grounded
    answer covering both parts instead of only whichever tool call happened
    to be seen first.

    Known limitation: a REDEMPTION_* response never wins as the base (the
    prefix check below only matches "TRANSACTION"), so a rare compound
    question spanning both get_recent_transactions and
    get_ongoing_redemptions in one turn would show the transaction as the
    rendered card and the redemption tracking info as appended text only,
    not its own card. Same class of accepted tradeoff as this app's other
    single-tool-per-turn limitations - not solved generically here."""
    base = next((r for r in responses if r.type.value.startswith("TRANSACTION")), responses[0])
    others = [r for r in responses if r is not base]
    combined_message = "\n\n".join([base.message] + [r.message for r in others])
    return ChatResponse(type=base.type, message=combined_message, data=base.data)


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
        # A compound question ("how to buy AND sell gold?") can make the model
        # answer it as several separate answer_from_kb calls - one per
        # sub-question - rather than a single call citing every relevant
        # article together, even though the schema already supports citing
        # more than one id per call. Merge across every answer_from_kb call
        # rather than acting on just the first (or last) one, so every part
        # of a multi-part question gets answered, not just whichever call
        # happened to be seen first/last.
        answers: list[str] = []
        cited_ids: list[int] = []
        insufficient = False
        for call in getattr(resolved, "tool_calls", None) or []:
            args = json.loads(call.function.arguments or "{}")
            if call.function.name == "answer_from_kb" and args.get("answer"):
                answers.append(args["answer"])
                for i in args.get("source_article_ids", []):
                    if i in articles_by_id and i not in cited_ids:
                        cited_ids.append(i)
            elif call.function.name == "insufficient_kb_info":
                insufficient = True

        if answers:
            return ChatResponse.text_answer("\n\n".join(answers), grounded=True, sources=cited_ids)
        if insufficient:
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
                    with tracing.tracer.start_as_current_span("generate_final_answer"):
                        explanation = explain_transaction(chosen, user.display_name, message)
                    return ChatResponse.transaction_explanation(explanation, chosen)
                if len(ids) > 1:
                    chosen = [txn_by_id[i] for i in ids]
                    with tracing.tracer.start_as_current_span("generate_final_answer"):
                        explanation = explain_transactions(chosen, message, user.display_name)
                    return ChatResponse.transaction_summary(explanation, chosen)
                # ids empty (every id hallucinated) - fall through to the safe list below
            elif call.function.name == "no_single_match":
                selection_message = SELECTION_MESSAGES.get(args.get("reason"), SELECTION_MESSAGES["ambiguous"])
    except Exception:
        logger.exception("Transaction resolution call failed; falling back to selection list")

    return ChatResponse.transaction_selection(selection_message, txn_out)


def _redemption_tracking_out(
    order: RedemptionOrderRecord, lookup: "tracking_service.TrackingLookup | None"
) -> RedemptionTrackingOut:
    return RedemptionTrackingOut(
        order_ref=order.id,
        product_name=order.product_name,
        status=order.txn_status,
        awb_available=order.awb_number is not None,
        current_location=lookup.current_location if lookup else None,
        latest_event=lookup.latest_event if lookup else None,
        history=lookup.history if lookup else [],
        stale=lookup.stale if lookup else False,
    )


def _build_redemption_tracking(order: RedemptionOrderRecord) -> tuple[RedemptionTrackingOut, bool]:
    """Returns (tracking, ok). `ok` is False only when an AWB exists but the
    tracking lookup itself failed (network/upstream) - not when there's
    simply no AWB yet, which is an expected `awb_available=False` case, not a
    failure. Callers branch on `order.awb_number` first to pick the right
    customer-facing message; this function only ever builds the data."""
    if not order.awb_number:
        return _redemption_tracking_out(order, None), True
    try:
        lookup = tracking_service.get_tracking(order.awb_number)
    except tracking_service.TrackingError:
        logger.exception("Tracking lookup failed for AWB %s", order.awb_number)
        return _redemption_tracking_out(order, None), False
    return _redemption_tracking_out(order, lookup), True


def track_redemption_order(order: RedemptionOrderRecord, display_name: str, original_question: str) -> ChatResponse:
    """Turns one already-authorized, already-fetched ongoing redemption order
    into a tracking response. Mirrors explain_transaction()'s role for a card
    click: the click is already an unambiguous, explicit action, so this
    skips intent routing/resolution and goes straight to building the
    tracking response."""
    tracking, ok = _build_redemption_tracking(order)
    if not order.awb_number:
        text = "Your order is still being processed and doesn't have tracking information yet."
        return ChatResponse.redemption_tracking(text, tracking)
    if not ok:
        text = "Sorry, tracking is temporarily unavailable right now. Please try again shortly."
        return ChatResponse.redemption_tracking(text, tracking)
    with tracing.tracer.start_as_current_span("generate_final_answer"):
        explanation = explain_redemption_tracking(tracking, display_name, original_question)
    return ChatResponse.redemption_tracking(explanation, tracking)


def _track_and_respond(db: Session, user: User, order_record: RedemptionOrderRecord, original_question: str) -> ChatResponse:
    # Re-validates ownership AND current trackable status directly against
    # the DB (bypassing the ongoing-orders cache) immediately before use -
    # the spec's "re-validate ownership immediately before use" requirement,
    # same idea as resolve_transactions' id-membership check one level up,
    # plus a live re-check here since tracking is the more sensitive action.
    fresh = redemption_service.get_ongoing_redemption_by_ref(db, user, order_record.id)
    if fresh is None:
        return ChatResponse.text_answer("Sorry, I couldn't find that order.", grounded=True)
    return track_redemption_order(fresh, user.display_name, original_question)


def _handle_redemption_tracking(db: Session, user: User, message: str, history: list[ChatMessage]) -> ChatResponse:
    try:
        orders = redemption_service.get_ongoing_redemptions(db, user)
    except Exception:
        logger.exception("Fetching ongoing redemption orders failed")
        return ChatResponse.error("db_unavailable", "We couldn't load your orders. Please try again.")

    if not orders:
        return ChatResponse.text_answer("You don't have any ongoing redemption orders right now.", grounded=True)

    order_out = [redemption_service.to_order_out(o) for o in orders]

    if len(orders) == 1:
        return _track_and_respond(db, user, orders[0], message)

    # 2+ orders: second forced-tool-choice resolve call, same pattern as
    # _handle_recent_transactions's resolve_transactions/no_single_match step.
    orders_by_ref = {o.id: o for o in orders}
    resolve_system_prompt = prompts.render(
        "redemption_resolve.j2",
        orders_json=json.dumps([o.model_dump(mode="json") for o in order_out]),
        display_name=user.display_name,
    )
    resolve_messages = [{"role": "system", "content": resolve_system_prompt}]
    resolve_messages += [{"role": h.role, "content": h.content} for h in history]
    resolve_messages.append({"role": "user", "content": message})

    try:
        resolved = llm_client.chat_completion(
            resolve_messages,
            tools=[RESOLVE_REDEMPTION_ORDER, NO_SINGLE_REDEMPTION_MATCH],
            tool_choice="required",
            model=settings.resolve_model,
            reasoning_effort=settings.resolve_reasoning_effort,
        )
        for call in getattr(resolved, "tool_calls", None) or []:
            if call.function.name == "resolve_redemption_order":
                args = json.loads(call.function.arguments or "{}")
                ref = args.get("order_ref")
                if ref in orders_by_ref:
                    return _track_and_respond(db, user, orders_by_ref[ref], message)
                # hallucinated/injected ref not in this user's own fetched list -
                # fall through to the safe selection list, same defense as
                # resolve_transactions.
    except Exception:
        logger.exception("Redemption order resolution call failed; falling back to selection list")

    return ChatResponse.redemption_selection(REDEMPTION_SELECTION_MESSAGE, order_out)


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


def _explain_transaction_messages(transaction: Transaction, display_name: str, original_question: str) -> list[dict]:
    system_prompt = prompts.render(
        "transaction_explain.j2",
        record_json=json.dumps(_transaction_record(transaction)),
        display_name=display_name,
        original_question=original_question,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": original_question},
    ]


def explain_transaction(transaction: Transaction, display_name: str, original_question: str) -> str:
    """Turns one already-authorized, already-fetched transaction record into
    an answer to the customer's actual question (not a generic summary) -
    `original_question` is either what they typed ("why did it fail?", "what
    month was it created?") or, for a card click with no typed text, the
    synthetic question routers/transactions.py builds for that click."""
    try:
        final = llm_client.chat_completion(_explain_transaction_messages(transaction, display_name, original_question))
        return final.content or fallback_explanation(transaction)
    except Exception:
        logger.exception("Chat completion (transaction explanation) failed")
        return fallback_explanation(transaction)


def explain_transaction_stream(
    transaction: Transaction, display_name: str, original_question: str, metrics: TurnMetrics | None = None
):
    """Streaming counterpart to explain_transaction() - returns an
    llm_client.StreamedCompletion: iterate for text deltas, `.content` holds
    the full text once exhausted (empty if the call failed before producing
    any content - callers should fall back to fallback_explanation(), same
    as the non-streaming path)."""
    return llm_client.stream_chat_completion(
        _explain_transaction_messages(transaction, display_name, original_question), metrics=metrics
    )


def _explain_transactions_messages(
    transactions: list[Transaction], original_question: str, display_name: str
) -> list[dict]:
    records_json = json.dumps([_transaction_record(t) for t in transactions])
    system_prompt = prompts.render(
        "transactions_summary.j2",
        records_json=records_json,
        original_question=original_question,
        display_name=display_name,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": original_question},
    ]


def explain_transactions(transactions: list[Transaction], original_question: str, display_name: str) -> str:
    """Same idea as explain_transaction, generalized to several already-authorized,
    already-fetched records at once (e.g. "my last 3 transactions, which failed and
    why, with payment method for each") - one grounded answer covering all of them,
    never inventing a field not present in the JSON."""
    try:
        final = llm_client.chat_completion(_explain_transactions_messages(transactions, original_question, display_name))
        return final.content or fallback_summary(transactions)
    except Exception:
        logger.exception("Chat completion (transaction summary) failed")
        return fallback_summary(transactions)


def explain_transactions_stream(
    transactions: list[Transaction], original_question: str, display_name: str, metrics: TurnMetrics | None = None
):
    """Streaming counterpart to explain_transactions() - see
    explain_transaction_stream's docstring for the contract."""
    return llm_client.stream_chat_completion(
        _explain_transactions_messages(transactions, original_question, display_name), metrics=metrics
    )


def fallback_explanation(transaction: Transaction) -> str:
    text = f"Your {transaction.type} of {transaction.product} for {transaction.amount} is {transaction.status}."
    if transaction.failure_reason:
        text += f" Reason: {transaction.failure_reason}."
    return text


def fallback_summary(transactions: list[Transaction]) -> str:
    return " ".join(fallback_explanation(t) for t in transactions)


def _explain_redemption_tracking_messages(
    tracking: RedemptionTrackingOut, display_name: str, original_question: str
) -> list[dict]:
    system_prompt = prompts.render(
        "redemption_tracking_explain.j2",
        tracking_json=json.dumps(tracking.model_dump(mode="json")),
        display_name=display_name,
        original_question=original_question,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": original_question},
    ]


def explain_redemption_tracking(tracking: RedemptionTrackingOut, display_name: str, original_question: str) -> str:
    """Turns one already-normalized RedemptionTrackingOut into an answer to
    the customer's actual question - same pattern as explain_transaction(),
    grounded ONLY in the tracking JSON so it can never invent a location,
    timestamp, or delivery-day promise the tracking data doesn't contain."""
    try:
        final = llm_client.chat_completion(
            _explain_redemption_tracking_messages(tracking, display_name, original_question)
        )
        return final.content or fallback_redemption_tracking(tracking)
    except Exception:
        logger.exception("Chat completion (redemption tracking explanation) failed")
        return fallback_redemption_tracking(tracking)


def explain_redemption_tracking_stream(
    tracking: RedemptionTrackingOut, display_name: str, original_question: str, metrics: TurnMetrics | None = None
):
    """Streaming counterpart to explain_redemption_tracking() - same contract
    as explain_transaction_stream (see its docstring)."""
    return llm_client.stream_chat_completion(
        _explain_redemption_tracking_messages(tracking, display_name, original_question), metrics=metrics
    )


def fallback_redemption_tracking(tracking: RedemptionTrackingOut) -> str:
    if not tracking.awb_available:
        return f"Your {tracking.product_name} order is still being processed and doesn't have tracking information yet."
    text = f"Your {tracking.product_name} order is currently {tracking.status}."
    if tracking.current_location:
        text += f" Latest update: {tracking.current_location}."
    return text


class _TrackRedemptionOrderStream:
    """Streaming counterpart to track_redemption_order() - see that
    function's docstring for the non-streaming contract. Iterate for
    cumulative text-so-far; after exhaustion, `.tracking`/`.text` hold the
    final RedemptionTrackingOut and full text, for the caller to build the
    final ChatResponse (same "iterate then read an attribute" shape as
    llm_client.StreamedCompletion and StreamedChatTurn)."""

    def __init__(self, order: RedemptionOrderRecord, display_name: str, original_question: str, metrics: TurnMetrics | None = None):
        self._order = order
        self._display_name = display_name
        self._original_question = original_question
        self._metrics = metrics
        self.tracking: RedemptionTrackingOut | None = None
        self.text: str = ""

    def __iter__(self):
        tracking, ok = _build_redemption_tracking(self._order)
        self.tracking = tracking
        if not self._order.awb_number:
            self.text = "Your order is still being processed and doesn't have tracking information yet."
            yield self.text
            return
        if not ok:
            self.text = "Sorry, tracking is temporarily unavailable right now. Please try again shortly."
            yield self.text
            return
        with tracing.tracer.start_as_current_span("generate_final_answer"):
            try:
                streamed = explain_redemption_tracking_stream(
                    tracking, self._display_name, self._original_question, metrics=self._metrics
                )
                yield from _yield_cumulative(streamed)
                self.text = streamed.content or fallback_redemption_tracking(tracking)
            except Exception:
                logger.exception("Chat completion (redemption tracking explanation stream) failed")
                self.text = fallback_redemption_tracking(tracking)
                yield self.text


def track_redemption_order_stream(
    order: RedemptionOrderRecord, display_name: str, original_question: str, metrics: TurnMetrics | None = None
) -> _TrackRedemptionOrderStream:
    return _TrackRedemptionOrderStream(order, display_name, original_question, metrics)


def _yield_cumulative(streamed: "llm_client.StreamedCompletion"):
    """Forwards a StreamedCompletion's progress as the full text-so-far at
    each step, not the incremental delta - accumulation happens once, here
    on the backend (StreamedCompletion.content is already cumulative), so
    the frontend can just render whatever it receives directly instead of
    concatenating deltas itself."""
    for _ in streamed:
        yield streamed.content


class StreamedChatTurn:
    """Streaming counterpart to chat_turn()/_chat_turn() - fully parallel, not
    a replacement: the non-streaming functions above are untouched, still
    used by /chat, both eval scripts, and every existing test.

    Iterating yields the full text-so-far of the turn's final user-facing
    reply at each step (not incremental deltas) - accumulation happens once,
    here (see _yield_cumulative), so callers/the frontend just render
    whatever they receive directly rather than concatenating themselves.
    After exhaustion, `.response` holds the same ChatResponse shape
    chat_turn() returns, and `.metrics` holds this turn's aggregated
    TurnMetrics for the caller to persist. `.metrics` is a plain object held
    directly on this instance and passed explicitly into every LLM call this
    class makes, rather than relying on the contextvar-based turn_scope() the
    non-streaming path uses: contextvars don't survive being set/reset across
    the different worker-pool threads a sync generator driven by Starlette's
    StreamingResponse can run on. For the same reason, this class does not
    wrap itself in session_log.session_scope() either - streamed turns don't
    get a JSONL session log entry (a deliberate, small observability gap;
    correctness/persistence are unaffected, since those go through
    conversation_service, not session_log).

    Four things are genuine free-text generation and actually stream
    token-by-token: transaction explain/summary, KB grounded answers (judged
    via the fast tool-call as before, then written by a separate streamed
    call), small talk (also judged via tool-call, then written separately),
    and redemption tracking explanations (order discovery/resolution and the
    AWB lookup are blocking, same as the transaction path; only the final
    explanation is streamed). Everything else (transaction list, redemption
    selection list, escalation, KB decline, errors) is a fixed string or DB
    lookup with nothing to stream, so it's yielded once as a single "delta"
    for a uniform SSE contract."""

    def __init__(self, db: Session, user: User, message: str, history: list[ChatMessage]):
        self._db = db
        self._user = user
        self._message = message
        self._history = history
        self.response: ChatResponse | None = None
        self.metrics = TurnMetrics()

    def __iter__(self):
        db, user, message, history = self._db, self._user, self._message, self._history

        # Root span for the whole streamed turn - see chat_turn()'s identical
        # root span for the non-streaming path. Safe to use OTel's normal
        # contextvar-based current-span propagation here even though this is
        # a generator: every next() call happens inside the one dedicated
        # worker thread the streaming routers create for the whole request
        # (see routers/chat.py's/routers/redemptions.py's /stream endpoints),
        # never dispatched across threads mid-generator the way Starlette's
        # own outer SSE-forwarding generator is - so the span's context stays
        # valid for this generator's entire lifetime.
        root_span_cm = tracing.tracer.start_as_current_span("chat_turn")
        root_span = root_span_cm.__enter__()
        try:
            # No conversation_id is threaded into StreamedChatTurn today (the
            # streaming routers keep it for their own conversation_service
            # persistence, separately) - user.id + message are still enough
            # to identify and read a trace.
            root_span.set_attribute("user.id", str(user.id))
            root_span.set_attribute("user.message", message[:500])

            if _consecutive_trailing_declines(history) >= settings.escalation_decline_threshold:
                self.response = ChatResponse.escalate(ESCALATION_MESSAGE, settings.support_contact_email)
                yield self.response.message
                return

            try:
                assistant_message = _route_intent(user, message, history, tools=ALL_TOOLS_STREAM, metrics=self.metrics)
            except Exception:
                logger.exception("Chat completion (intent routing) failed")
                self.response = ChatResponse.error(
                    "llm_unavailable", "The assistant is temporarily unavailable. Please try again."
                )
                yield self.response.message
                return

            tool_calls = getattr(assistant_message, "tool_calls", None)
            if not tool_calls:
                text = assistant_message.content or "How can I help you today?"
                self.response = ChatResponse.text_answer(text, grounded=True)
                yield text
                return

            # See _chat_turn's identical comment: a compound question can make the
            # model correctly issue multiple tool calls in one response - dispatch
            # every one of them and merge the results, rather than only
            # tool_calls[0]. Each sub-call streams in turn; the cumulative text
            # shown to the frontend keeps growing across the boundary between them
            # (prefix + this sub-call's own cumulative text).
            if any(c.function.name == "request_human_agent" for c in tool_calls):
                self.response = ChatResponse.escalate(ESCALATION_MESSAGE, settings.support_contact_email)
                yield self.response.message
                return

            real_calls = _dedupe_real_tool_calls(tool_calls)
            calls_to_run = real_calls or tool_calls

            step_span_names = {
                "search_knowledge_base": "kb_search_and_judge",
                "get_recent_transactions": "transaction_lookup_and_resolve",
                "get_ongoing_redemptions": "redemption_lookup_and_resolve",
                "respond_directly": "generate_final_answer",
            }

            responses: list[ChatResponse] = []
            prefix = ""
            for call in calls_to_run:
                tool_name = call.function.name
                self.response = None
                with tracing.tracer.start_as_current_span(step_span_names.get(tool_name, "handle_tool")):
                    if tool_name == "search_knowledge_base":
                        sub_stream = self._stream_knowledge_base(db, user, message)
                    elif tool_name == "get_recent_transactions":
                        sub_stream = self._stream_recent_transactions(db, user, message, history)
                    elif tool_name == "get_ongoing_redemptions":
                        sub_stream = self._stream_redemption_tracking(db, user, message, history)
                    elif tool_name == "respond_directly":
                        sub_stream = self._stream_small_talk(user, message)
                    else:
                        logger.error("Model requested unsupported tool: %s", tool_name)
                        self.response = ChatResponse.error(
                            "unsupported_tool", "The assistant tried to use an unsupported action."
                        )
                        yield prefix + self.response.message
                        responses.append(self.response)
                        continue

                    for text_so_far in sub_stream:
                        yield prefix + text_so_far
                responses.append(self.response)
                prefix = prefix + self.response.message + "\n\n"

            self.response = responses[0] if len(responses) == 1 else _merge_responses(responses)
        finally:
            if self.response is not None:
                root_span.set_attribute("response.type", self.response.type.value)
                root_span.set_attribute("response.message", self.response.message[:500])
            root_span_cm.__exit__(None, None, None)

    def _stream_small_talk(self, user: User, message: str):
        prompt = prompts.render("small_talk_reply.j2", display_name=user.display_name)
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": message}]
        try:
            streamed = llm_client.stream_chat_completion(messages, metrics=self.metrics)
            yield from _yield_cumulative(streamed)
        except Exception:
            logger.exception("Chat completion (small talk reply) failed")
            self.response = ChatResponse.error(
                "llm_unavailable", "The assistant is temporarily unavailable. Please try again."
            )
            yield self.response.message
            return
        text = streamed.content or "How can I help you today?"
        self.response = ChatResponse.text_answer(text, grounded=True)

    def _stream_knowledge_base(self, db: Session, user: User, query: str):
        try:
            result = kb_service.search_knowledge_base(db, query)
        except Exception:
            logger.exception("Knowledge base search failed")
            self.response = ChatResponse.error("kb_unavailable", "Search is temporarily unavailable. Please try again.")
            yield self.response.message
            return

        if not result.articles:
            self.response = ChatResponse.text_answer(NO_INFO_MESSAGE, grounded=False)
            yield NO_INFO_MESSAGE
            return

        articles_by_id = {a.id: a for a in result.articles}
        judge_prompt = prompts.render("kb_judgment.j2", articles=result.articles, display_name=user.display_name)
        judge_messages = [{"role": "system", "content": judge_prompt}, {"role": "user", "content": query}]
        try:
            judged = llm_client.chat_completion(
                judge_messages,
                tools=[ANSWER_FROM_KB_JUDGE, INSUFFICIENT_KB_INFO],
                tool_choice="required",
                metrics=self.metrics,
            )
        except Exception:
            logger.exception("Chat completion (KB judgment) failed")
            self.response = ChatResponse.error(
                "llm_unavailable", "The assistant is temporarily unavailable. Please try again."
            )
            yield self.response.message
            return

        # Merge across every answer_from_kb call rather than keeping only the
        # last one seen - a compound question ("how to buy AND sell gold?")
        # can make the model answer it as several separate answer_from_kb
        # calls instead of one call citing every relevant article together.
        cited_ids: list[int] = []
        for call in getattr(judged, "tool_calls", None) or []:
            if call.function.name == "answer_from_kb":
                args = json.loads(call.function.arguments or "{}")
                for i in args.get("source_article_ids", []):
                    if i in articles_by_id and i not in cited_ids:
                        cited_ids.append(i)

        if not cited_ids:
            self.response = ChatResponse.text_answer(NO_INFO_MESSAGE, grounded=False)
            yield NO_INFO_MESSAGE
            return

        cited_articles = [articles_by_id[i] for i in cited_ids]
        answer_prompt = prompts.render("kb_answer_stream.j2", articles=cited_articles, display_name=user.display_name)
        answer_messages = [{"role": "system", "content": answer_prompt}, {"role": "user", "content": query}]
        try:
            streamed = llm_client.stream_chat_completion(answer_messages, metrics=self.metrics)
            yield from _yield_cumulative(streamed)
        except Exception:
            logger.exception("Chat completion (KB answer) failed")
            self.response = ChatResponse.error(
                "llm_unavailable", "The assistant is temporarily unavailable. Please try again."
            )
            yield self.response.message
            return
        text = streamed.content or NO_INFO_MESSAGE
        self.response = ChatResponse.text_answer(text, grounded=True, sources=cited_ids)

    def _stream_recent_transactions(self, db: Session, user: User, message: str, history: list[ChatMessage]):
        try:
            transactions = transaction_service.get_recent_transactions(db, user)
        except Exception:
            logger.exception("Fetching recent transactions failed")
            self.response = ChatResponse.error("db_unavailable", "We couldn't load your transactions. Please try again.")
            yield self.response.message
            return

        if not transactions:
            text = "You don't have any recent transactions yet."
            self.response = ChatResponse.text_answer(text, grounded=True)
            yield text
            return

        txn_out = [TransactionOut.model_validate(t) for t in transactions]
        txn_by_id = {t.id: t for t in transactions}

        resolve_system_prompt = prompts.render(
            "transaction_resolve.j2",
            transactions_json=json.dumps([t.model_dump(mode="json") for t in txn_out]),
            display_name=user.display_name,
        )
        resolve_messages = [{"role": "system", "content": resolve_system_prompt}]
        resolve_messages += [{"role": h.role, "content": h.content} for h in history]
        resolve_messages.append({"role": "user", "content": message})

        selection_message = SELECTION_MESSAGES["ambiguous"]
        resolved_ids: list[str] = []
        try:
            resolved = llm_client.chat_completion(
                resolve_messages,
                tools=[RESOLVE_TRANSACTIONS, NO_SINGLE_MATCH],
                tool_choice="required",
                model=settings.resolve_model,
                reasoning_effort=settings.resolve_reasoning_effort,
                metrics=self.metrics,
            )
            for call in getattr(resolved, "tool_calls", None) or []:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "resolve_transactions":
                    resolved_ids = [i for i in args.get("transaction_ids", []) if i in txn_by_id]
                elif call.function.name == "no_single_match":
                    selection_message = SELECTION_MESSAGES.get(args.get("reason"), SELECTION_MESSAGES["ambiguous"])
        except Exception:
            logger.exception("Transaction resolution call failed; falling back to selection list")

        if len(resolved_ids) == 1:
            yield from self._stream_explain_transaction(txn_by_id[resolved_ids[0]], user.display_name, message)
            return
        if len(resolved_ids) > 1:
            chosen = [txn_by_id[i] for i in resolved_ids]
            yield from self._stream_explain_transactions(chosen, message, user.display_name)
            return

        self.response = ChatResponse.transaction_selection(selection_message, txn_out)
        yield selection_message

    def _stream_explain_transaction(self, transaction: Transaction, display_name: str, original_question: str):
        with tracing.tracer.start_as_current_span("generate_final_answer"):
            try:
                streamed = explain_transaction_stream(transaction, display_name, original_question, metrics=self.metrics)
                yield from _yield_cumulative(streamed)
                text = streamed.content or fallback_explanation(transaction)
            except Exception:
                logger.exception("Chat completion (transaction explanation) failed")
                text = fallback_explanation(transaction)
                yield text
        self.response = ChatResponse.transaction_explanation(text, transaction)

    def _stream_explain_transactions(self, transactions: list[Transaction], original_question: str, display_name: str):
        with tracing.tracer.start_as_current_span("generate_final_answer"):
            try:
                streamed = explain_transactions_stream(transactions, original_question, display_name, metrics=self.metrics)
                yield from _yield_cumulative(streamed)
                text = streamed.content or fallback_summary(transactions)
            except Exception:
                logger.exception("Chat completion (transaction summary) failed")
                text = fallback_summary(transactions)
                yield text
        self.response = ChatResponse.transaction_summary(text, transactions)

    def _stream_redemption_tracking(self, db: Session, user: User, message: str, history: list[ChatMessage]):
        try:
            orders = redemption_service.get_ongoing_redemptions(db, user)
        except Exception:
            logger.exception("Fetching ongoing redemption orders failed")
            self.response = ChatResponse.error("db_unavailable", "We couldn't load your orders. Please try again.")
            yield self.response.message
            return

        if not orders:
            text = "You don't have any ongoing redemption orders right now."
            self.response = ChatResponse.text_answer(text, grounded=True)
            yield text
            return

        order_out = [redemption_service.to_order_out(o) for o in orders]

        if len(orders) == 1:
            yield from self._stream_track_redemption(db, user, orders[0], message)
            return

        orders_by_ref = {o.id: o for o in orders}
        resolve_system_prompt = prompts.render(
            "redemption_resolve.j2",
            orders_json=json.dumps([o.model_dump(mode="json") for o in order_out]),
            display_name=user.display_name,
        )
        resolve_messages = [{"role": "system", "content": resolve_system_prompt}]
        resolve_messages += [{"role": h.role, "content": h.content} for h in history]
        resolve_messages.append({"role": "user", "content": message})

        resolved_ref: str | None = None
        try:
            resolved = llm_client.chat_completion(
                resolve_messages,
                tools=[RESOLVE_REDEMPTION_ORDER, NO_SINGLE_REDEMPTION_MATCH],
                tool_choice="required",
                model=settings.resolve_model,
                reasoning_effort=settings.resolve_reasoning_effort,
                metrics=self.metrics,
            )
            for call in getattr(resolved, "tool_calls", None) or []:
                if call.function.name == "resolve_redemption_order":
                    args = json.loads(call.function.arguments or "{}")
                    ref = args.get("order_ref")
                    if ref in orders_by_ref:
                        resolved_ref = ref
        except Exception:
            logger.exception("Redemption order resolution call failed; falling back to selection list")

        if resolved_ref is not None:
            yield from self._stream_track_redemption(db, user, orders_by_ref[resolved_ref], message)
            return

        self.response = ChatResponse.redemption_selection(REDEMPTION_SELECTION_MESSAGE, order_out)
        yield REDEMPTION_SELECTION_MESSAGE

    def _stream_track_redemption(self, db: Session, user: User, order_record: RedemptionOrderRecord, original_question: str):
        fresh = redemption_service.get_ongoing_redemption_by_ref(db, user, order_record.id)
        if fresh is None:
            text = "Sorry, I couldn't find that order."
            self.response = ChatResponse.text_answer(text, grounded=True)
            yield text
            return
        streamed = track_redemption_order_stream(fresh, user.display_name, original_question, metrics=self.metrics)
        yield from streamed
        self.response = ChatResponse.redemption_tracking(streamed.text, streamed.tracking)


def chat_turn_stream(db: Session, user: User, message: str, history: list[ChatMessage]) -> StreamedChatTurn:
    """Streaming counterpart to chat_turn(). Iterating yields the full
    text-so-far at each step (not deltas); after exhaustion, `.response`/
    `.metrics` on the returned object hold the final ChatResponse and
    aggregated TurnMetrics - see StreamedChatTurn's
    docstring for why this doesn't use session_log/turn_scope like
    chat_turn() does."""
    return StreamedChatTurn(db, user, message, history)
