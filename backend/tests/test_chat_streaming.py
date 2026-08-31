import json
import uuid

from app.models import Conversation


class _FakeStreamedCompletion:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks
        self.content = ""
        self.usage = None

    def __iter__(self):
        for chunk in self._chunks:
            self.content += chunk
            yield chunk


class _FakeFunction:
    def __init__(self, name: str, arguments: str = "{}"):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name: str, arguments: str = "{}"):
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls
        self.content = content


def _tool_names(tools):
    return [t["function"]["name"] for t in (tools or [])]


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        events.append((event, data))
    return events


def test_chat_stream_small_talk_streams_deltas_and_persists(client, make_user, auth_headers, monkeypatch, db_session):
    alice = make_user("alice", "Alice")

    def fake_route(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None, metrics=None):
        if not tools:
            return _FakeMessage(content="Greeting")  # title-gen call, no tools
        return _FakeMessage(tool_calls=[_FakeToolCall("respond_directly")])

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_route)
    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["Hi ", "Alice", "!"]),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        "/chat/stream", json={"message": "hi", "conversation_id": conversation_id}, headers=auth_headers(alice)
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    deltas = [d["text"] for e, d in events if e == "delta"]
    # Each event carries the full text-so-far (accumulated server-side), not
    # an incremental piece - the frontend renders whatever it receives directly.
    assert deltas == ["Hi ", "Hi Alice", "Hi Alice!"]

    done_events = [d for e, d in events if e == "done"]
    assert len(done_events) == 1
    assert done_events[0]["type"] == "TEXT_ANSWER"
    assert done_events[0]["message"] == "Hi Alice!"

    conversation = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert conversation is not None
    assert conversation.message_count == 2
    assert conversation.messages[-1].content == "Hi Alice!"
    assert conversation.messages[-1].response_type == "TEXT_ANSWER"


def test_chat_stream_transaction_explanation_streams_and_persists(
    client, make_user, make_transaction, auth_headers, monkeypatch, db_session
):
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_stream_1", status="FAILED", failure_reason="Card declined")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None, metrics=None):
        names = _tool_names(tools)
        if not tools:
            return _FakeMessage(content="Transaction question")  # title-gen call, no tools
        if "get_orders" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "BUY"}')])
        if "resolve_transactions" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_transactions", f'{{"transaction_ids": ["{txn.id}"]}}')]
            )
        raise AssertionError(f"unexpected chat_completion call with tools={names}")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["Your purchase ", "failed because ", "the card was declined."]),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        "/chat/stream",
        json={"message": "why did my last purchase fail?", "conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    deltas = [d["text"] for e, d in events if e == "delta"]
    # Last event's text is the full cumulative message, not a join of pieces.
    assert deltas[-1] == "Your purchase failed because the card was declined."

    done_events = [d for e, d in events if e == "done"]
    assert done_events[0]["type"] == "TRANSACTION_EXPLANATION"
    assert done_events[0]["data"]["transaction"]["id"] == txn.id

    conversation = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert conversation.messages[-1].response_type == "TRANSACTION_EXPLANATION"


def test_chat_stream_merges_multiple_kb_articles_for_compound_question(
    client, make_user, auth_headers, monkeypatch, db_session
):
    """Streaming counterpart of test_kb_grounding.py's compound-question regression
    test: the judge call can issue multiple separate answer_from_kb calls (ids-only in
    the streaming schema) instead of one citing every relevant article - both must be
    merged into the cited set the final streamed answer is generated from."""
    from app.models import SupportArticle

    seeded_embedding = [1.0] + [0.0] * 1535
    buy = SupportArticle(question="How do I buy gold?", answer="Go to Buy...", embedding=seeded_embedding)
    sell = SupportArticle(question="How do I sell my gold?", answer="Go to Sell...", embedding=seeded_embedding)
    db_session.add_all([buy, sell])
    db_session.commit()
    db_session.refresh(buy)
    db_session.refresh(sell)

    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: seeded_embedding)

    def fake_route(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None, metrics=None):
        names = _tool_names(tools)
        if not tools:
            return _FakeMessage(content="Buy and sell question")  # title-gen call, no tools
        if "search_knowledge_base" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("search_knowledge_base")])
        if "answer_from_kb" in names:
            return _FakeMessage(
                tool_calls=[
                    _FakeToolCall("answer_from_kb", f'{{"source_article_ids": [{buy.id}]}}'),
                    _FakeToolCall("answer_from_kb", f'{{"source_article_ids": [{sell.id}]}}'),
                ]
            )
        raise AssertionError(f"unexpected chat_completion call with tools={names}")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_route)
    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["To buy, go to Buy. ", "To sell, go to Sell."]),
    )

    alice = make_user("alice", "Alice")
    conversation_id = str(uuid.uuid4())
    resp = client.post(
        "/chat/stream",
        json={"message": "how to buy and sell gold", "conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done_events = [d for e, d in events if e == "done"]
    assert done_events[0]["type"] == "TEXT_ANSWER"
    assert set(done_events[0]["data"]["sources"]) == {buy.id, sell.id}
    assert done_events[0]["message"] == "To buy, go to Buy. To sell, go to Sell."


def test_chat_stream_merges_transaction_and_kb_when_router_calls_both_tools(
    client, make_user, make_transaction, auth_headers, db_session, monkeypatch
):
    """Streaming counterpart of test_chat_routing.py's compound transaction+KB
    regression test: the router can correctly issue both get_orders
    and search_knowledge_base in one response - both must be run and merged,
    with the cumulative streamed text growing across the boundary between them."""
    from app.models import SupportArticle

    alice = make_user("alice", "Alice")
    make_transaction(alice, "txn_a1")

    seeded_embedding = [1.0] + [0.0] * 1535
    article = SupportArticle(
        question="What fees do you charge?", answer="We charge a small spread.", embedding=seeded_embedding
    )
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)

    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: seeded_embedding)

    def fake_route(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None, metrics=None):
        names = _tool_names(tools)
        if not tools:
            return _FakeMessage(content="Transactions and fees question")  # title-gen call
        if "get_orders" in names and "search_knowledge_base" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("get_orders", '{"type": "BUY"}'), _FakeToolCall("search_knowledge_base")]
            )
        if "resolve_transactions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("no_single_match", '{"reason": "list_requested"}')])
        if "answer_from_kb" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("answer_from_kb", f'{{"source_article_ids": [{article.id}]}}')])
        raise AssertionError(f"unexpected chat_completion call with tools={names}")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_route)
    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["We charge ", "a small spread."]),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        "/chat/stream",
        json={"message": "Can you check my transactions and also tell me the fees you charge?", "conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    deltas = [d["text"] for e, d in events if e == "delta"]
    # The transaction-list message (a single fixed-string "delta") arrives
    # first, then the KB answer streams in on top of it - cumulative text
    # keeps growing across that boundary rather than resetting.
    assert deltas[0] == "Here are your recent transactions:"
    assert deltas[-1] == "Here are your recent transactions:\n\nWe charge a small spread."

    done_events = [d for e, d in events if e == "done"]
    assert done_events[0]["type"] == "TRANSACTION_SELECTION"
    assert done_events[0]["message"] == "Here are your recent transactions:\n\nWe charge a small spread."
    assert [t["id"] for t in done_events[0]["data"]["transactions"]] == ["txn_a1"]
