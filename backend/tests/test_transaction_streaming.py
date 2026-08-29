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


def test_explain_stream_streams_deltas_and_persists(client, make_user, make_transaction, auth_headers, monkeypatch, db_session):
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_explain_stream", status="FAILED", failure_reason="Card declined")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["Your purchase ", "failed because ", "the card was declined."]),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        f"/transactions/{txn.id}/explain/stream",
        json={"conversation_id": conversation_id},
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
    assert conversation is not None
    assert conversation.messages[0].content == f"What can you tell me about transaction {txn.id}?"
    assert conversation.messages[-1].content == "Your purchase failed because the card was declined."


def test_explain_stream_404_for_other_users_transaction(client, make_user, make_transaction, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    txn = make_transaction(bob, "txn_bob_stream")

    resp = client.post(f"/transactions/{txn.id}/explain/stream", headers=auth_headers(alice))
    assert resp.status_code == 404


def test_explain_stream_works_without_conversation_id(client, make_user, make_transaction, auth_headers, monkeypatch):
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_no_conv_stream", status="SUCCESS")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["All good, ", "this one succeeded."]),
    )

    resp = client.post(f"/transactions/{txn.id}/explain/stream", headers=auth_headers(alice))
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done_events = [d for e, d in events if e == "done"]
    assert done_events[0]["message"] == "All good, this one succeeded."
