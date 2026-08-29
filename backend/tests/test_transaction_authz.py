import uuid

from app.models import Conversation


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None


def test_user_can_fetch_own_transaction(client, make_user, make_transaction, auth_headers):
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_alice_1")

    resp = client.get(f"/transactions/{txn.id}", headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["id"] == "txn_alice_1"


def test_user_cannot_fetch_other_users_transaction(client, make_user, make_transaction, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    txn = make_transaction(bob, "txn_bob_1")

    resp = client.get(f"/transactions/{txn.id}", headers=auth_headers(alice))

    assert resp.status_code == 404


def test_recent_transactions_scoped_to_authenticated_user(client, make_user, make_transaction, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    make_transaction(alice, "txn_a1")
    make_transaction(bob, "txn_b1")

    resp = client.get("/transactions/recent", headers=auth_headers(alice))

    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert ids == ["txn_a1"]


def test_explain_endpoint_rejects_other_users_transaction(client, make_user, make_transaction, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    txn = make_transaction(bob, "txn_bob_2", status="FAILED", failure_reason="Card declined")

    resp = client.post(f"/transactions/{txn.id}/explain", headers=auth_headers(alice))

    assert resp.status_code == 404


def test_explain_transaction_prompt_uses_the_actual_question_asked(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    """Regression test for a real bug: explain_transaction() hardcoded a generic
    "Explain this transaction to me." prompt regardless of what was actually asked
    ("what month was it created?" got a generic failure-reason explanation instead
    of the date). The actual question must be what the LLM call is given."""
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_date", status="FAILED", failure_reason="Card declined")

    captured_messages = []

    def fake_chat_completion(messages, *args, **kwargs):
        captured_messages.append(messages)
        return _FakeMessage("Your most recent transaction was created in August 2026.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    resp = client.post(
        f"/transactions/{txn.id}/explain",
        json={"conversation_id": None},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    assert len(captured_messages) == 1
    # The last message sent to the LLM must be the actual question this
    # endpoint is answering (the synthetic "What can you tell me about
    # transaction X?" for a card click), not a hardcoded generic string.
    assert captured_messages[0][-1]["content"] == f"What can you tell me about transaction {txn.id}?"


def test_explain_endpoint_returns_explanation_for_own_transaction(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_a2", status="FAILED", failure_reason="Card declined")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *args, **kwargs: _FakeMessage("Your purchase failed because the card was declined."),
    )

    resp = client.post(f"/transactions/{txn.id}/explain", headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TRANSACTION_EXPLANATION"
    assert body["data"]["transaction"]["id"] == "txn_a2"


def test_explain_endpoint_persists_turn_when_conversation_id_given(
    client, make_user, make_transaction, auth_headers, monkeypatch, db_session
):
    """Clicking a transaction card should leave a real turn in the
    conversation, so a later chat follow-up has this transaction in its
    history - the same as if the customer had typed the question themselves."""
    alice = make_user("alice", "Alice")
    txn = make_transaction(alice, "txn_a3", status="PENDING")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *args, **kwargs: _FakeMessage("This transaction is still pending."),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        f"/transactions/{txn.id}/explain",
        json={"conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200

    conversation = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert conversation is not None
    assert conversation.message_count == 2
    contents = [m.content for m in conversation.messages]
    assert contents[0] == f"What can you tell me about transaction {txn.id}?"
    assert contents[1] == "This transaction is still pending."


def test_explain_endpoint_404_for_conversation_owned_by_another_user(
    client, make_user, make_transaction, make_conversation, auth_headers
):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    txn = make_transaction(alice, "txn_a4")
    bobs_conversation = make_conversation(bob, title="Bob's conversation")

    resp = client.post(
        f"/transactions/{txn.id}/explain",
        json={"conversation_id": str(bobs_conversation.id)},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 404
