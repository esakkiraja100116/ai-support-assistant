import uuid

from app.models import Conversation


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


def _make_stub(routing_content="Sure, I can help with that.", title_content="Selling gold question"):
    """Distinguishes the intent-routing call (always passes non-empty `tools`)
    from the title-generation call (never passes tools) the same way the
    existing test suite distinguishes tool-routed calls by name - see
    test_chat_routing.py's `_tool_names` helper. Also records into
    turn_metrics directly, standing in for what the real llm_client._record_call
    would do, since the mock bypasses that entirely."""
    from app.services import turn_metrics

    calls = {"routing_message_counts": []}

    def stub(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        turn_metrics.record(model or "gpt-4o-mini", 10, 5, 0.001)
        if tools:
            calls["routing_message_counts"].append(len(messages))
            return _FakeMessage(content=routing_content)
        return _FakeMessage(content=title_content)

    return stub, calls


def test_conversation_persists_and_titles_first_turn(client, make_user, auth_headers, monkeypatch):
    alice = make_user("alice", "Alice")
    stub, calls = _make_stub()
    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", stub)

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        "/chat",
        json={"message": "How do I sell my gold?", "conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    assert resp.json()["type"] == "TEXT_ANSWER"

    conv = client.get("/conversations", headers=auth_headers(alice)).json()
    assert len(conv) == 1
    assert conv[0]["id"] == conversation_id
    assert conv[0]["title"] == "Selling gold question"  # from the mocked title-gen call, not raw truncation
    assert conv[0]["message_count"] == 2
    # Turn 1's assistant message folds in both the title-gen call's cost and the
    # routing call's cost (0.001 each from the stub) - not tracked separately.
    assert conv[0]["total_cost_usd"] == 0.002
    assert conv[0]["models_used"] == "gpt-4o-mini"


def test_second_turn_uses_db_history_over_client_supplied_history(client, make_user, auth_headers, monkeypatch):
    alice = make_user("alice", "Alice")
    stub, calls = _make_stub()
    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", stub)

    conversation_id = str(uuid.uuid4())
    client.post(
        "/chat", json={"message": "How do I sell my gold?", "conversation_id": conversation_id}, headers=auth_headers(alice)
    )
    # Deliberately send an empty (wrong) client history on turn 2 - if the server
    # used it instead of the DB, the routing call would only see 2 messages
    # (system + new user message) rather than 4 (system + 2 persisted turn-1
    # messages + new user message).
    resp = client.post(
        "/chat",
        json={"message": "What about buying?", "history": [], "conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    assert calls["routing_message_counts"] == [2, 4]

    detail = client.get(f"/conversations/{conversation_id}", headers=auth_headers(alice)).json()
    assert detail["message_count"] == 4
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    # Turn 2 is not a newly-created conversation, so no title-gen cost is folded
    # into its assistant message - just the one routing call's cost.
    assert detail["messages"][-1]["cost_usd"] == 0.001


def test_conversation_404_for_a_different_owner(client, make_user, auth_headers, make_conversation):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    bobs_conversation = make_conversation(bob, title="Bob's conversation")

    resp = client.post(
        "/chat",
        json={"message": "hi", "conversation_id": str(bobs_conversation.id)},
        headers=auth_headers(alice),
    )
    assert resp.status_code == 404

    resp = client.get(f"/conversations/{bobs_conversation.id}", headers=auth_headers(alice))
    assert resp.status_code == 404


def test_conversation_id_is_client_supplied(client, make_user, auth_headers, monkeypatch, db_session):
    """The frontend mints the conversation id itself (into `?c=<uuid>`) before
    the first message is ever sent - the backend must accept and use that id
    rather than minting its own."""
    alice = make_user("alice", "Alice")
    stub, _ = _make_stub()
    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", stub)

    conversation_id = str(uuid.uuid4())
    client.post("/chat", json={"message": "hi", "conversation_id": conversation_id}, headers=auth_headers(alice))

    stored = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert stored is not None
    assert stored.user_id == alice.id
