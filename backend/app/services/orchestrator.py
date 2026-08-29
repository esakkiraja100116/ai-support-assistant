import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Transaction, User
from app.schemas.chat import ChatMessage, ChatResponse
from app.schemas.transactions import TransactionOut
from app.services import kb_service, llm_client, prompts, session_log, transaction_service
from app.services.turn_metrics import TurnMetrics
from app.services.tools_schema import (
    ALL_TOOLS,
    ALL_TOOLS_STREAM,
    ANSWER_FROM_KB,
    ANSWER_FROM_KB_JUDGE,
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
            responses.append(_handle_knowledge_base(db, user, message, judgment_model, judgment_reasoning_effort))
        elif tool_name == "get_recent_transactions":
            responses.append(_handle_recent_transactions(db, user, message, history))
        elif tool_name == "respond_directly":
            args = json.loads(call.function.arguments or "{}")
            responses.append(ChatResponse.text_answer(args.get("reply") or "How can I help you today?", grounded=True))
        else:
            logger.error("Model requested unsupported tool: %s", tool_name)
            responses.append(ChatResponse.error("unsupported_tool", "The assistant tried to use an unsupported action."))

    return responses[0] if len(responses) == 1 else _merge_responses(responses)


def _dedupe_real_tool_calls(tool_calls) -> list:
    """Filters to search_knowledge_base/get_recent_transactions calls, keeping
    only the FIRST occurrence of each distinct tool name. Both tools take no
    arguments (search_knowledge_base always searches the raw customer message
    verbatim; get_recent_transactions always fetches the same list), so the
    model calling the same one twice is always redundant - and, for KB
    specifically, running it twice independently produces two full,
    overlapping answers that _merge_responses would then concatenate,
    duplicating everything rather than combining two distinct topics."""
    seen: set[str] = set()
    result = []
    for call in tool_calls:
        name = call.function.name
        if name in ("search_knowledge_base", "get_recent_transactions") and name not in seen:
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
    to be seen first."""
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
                    explanation = explain_transaction(chosen, user.display_name, message)
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

    Only three things are genuine free-text generation and actually stream
    token-by-token: transaction explain/summary, KB grounded answers (judged
    via the fast tool-call as before, then written by a separate streamed
    call), and small talk (also judged via tool-call, then written
    separately). Everything else (transaction list, escalation, KB decline,
    errors) is a fixed string or DB lookup with nothing to stream, so it's
    yielded once as a single "delta" for a uniform SSE contract."""

    def __init__(self, db: Session, user: User, message: str, history: list[ChatMessage]):
        self._db = db
        self._user = user
        self._message = message
        self._history = history
        self.response: ChatResponse | None = None
        self.metrics = TurnMetrics()

    def __iter__(self):
        db, user, message, history = self._db, self._user, self._message, self._history

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

        responses: list[ChatResponse] = []
        prefix = ""
        for call in calls_to_run:
            tool_name = call.function.name
            self.response = None
            if tool_name == "search_knowledge_base":
                sub_stream = self._stream_knowledge_base(db, user, message)
            elif tool_name == "get_recent_transactions":
                sub_stream = self._stream_recent_transactions(db, user, message, history)
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
        try:
            streamed = explain_transactions_stream(transactions, original_question, display_name, metrics=self.metrics)
            yield from _yield_cumulative(streamed)
            text = streamed.content or fallback_summary(transactions)
        except Exception:
            logger.exception("Chat completion (transaction summary) failed")
            text = fallback_summary(transactions)
            yield text
        self.response = ChatResponse.transaction_summary(text, transactions)


def chat_turn_stream(db: Session, user: User, message: str, history: list[ChatMessage]) -> StreamedChatTurn:
    """Streaming counterpart to chat_turn(). Iterating yields the full
    text-so-far at each step (not deltas); after exhaustion, `.response`/
    `.metrics` on the returned object hold the final ChatResponse and
    aggregated TurnMetrics - see StreamedChatTurn's
    docstring for why this doesn't use session_log/turn_scope like
    chat_turn() does."""
    return StreamedChatTurn(db, user, message, history)
