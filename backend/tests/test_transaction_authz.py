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
