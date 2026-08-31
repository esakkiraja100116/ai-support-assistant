import uuid

from sqlalchemy import text

from app.models import Conversation, is_trackable_redemption


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None


def test_user_can_fetch_own_redemption_order(client, make_user, make_redemption_order, auth_headers):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_alice_1")

    resp = client.get(f"/redemptions/{order.id}", headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["order_ref"] == str(order.id)


def test_user_cannot_fetch_other_users_redemption_order(client, make_user, make_redemption_order, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    order = make_redemption_order(bob, "txn_bob_1")

    resp = client.get(f"/redemptions/{order.id}", headers=auth_headers(alice))

    assert resp.status_code == 404


def test_ongoing_redemptions_scoped_to_authenticated_user(client, make_user, make_redemption_order, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    make_redemption_order(alice, "txn_a1", awb_number="PRO_A1")
    make_redemption_order(bob, "txn_b1", awb_number="PRO_B1")

    resp = client.get("/redemptions/ongoing", headers=auth_headers(alice))

    assert resp.status_code == 200
    refs = [o["order_ref"] for o in resp.json()]
    assert len(refs) == 1


def test_track_endpoint_rejects_other_users_order(client, make_user, make_redemption_order, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    order = make_redemption_order(bob, "txn_bob_2")

    resp = client.post(f"/redemptions/{order.id}/track", headers=auth_headers(alice))

    assert resp.status_code == 404


def test_ongoing_redemptions_excludes_terminal_and_completed_statuses(
    client, make_user, make_redemption_order, auth_headers
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_ongoing", status="IN_TRANSIT", awb_number="PRO_ONGOING")
    make_redemption_order(alice, "txn_delivered", status="DELIVERED", awb_number="PRO_DELIVERED")
    make_redemption_order(alice, "txn_cancelled", status="CANCELLED", awb_number=None)

    resp = client.get("/redemptions/ongoing", headers=auth_headers(alice))

    assert resp.status_code == 200
    txn_ids = {o["order_ref"] for o in resp.json()}
    assert len(txn_ids) == 1


def test_unknown_status_fails_closed():
    """A status this app doesn't recognize at all (not just a known excluded
    one) must never be treated as trackable - the eligibility rule fails
    closed, per the spec's explicit requirement."""
    assert is_trackable_redemption("SOME_BRAND_NEW_STATUS") is False
    assert is_trackable_redemption("DELIVERED") is False
    assert is_trackable_redemption("CANCELLED") is False
    assert is_trackable_redemption("IN_TRANSIT") is True


def test_ongoing_redemptions_excludes_genuinely_unrecognized_status(
    client, make_user, make_redemption_order, auth_headers, db_session
):
    """Same as the fail-closed unit test above, but end-to-end against a row
    with a status that bypassed the ORM enum entirely (raw SQL, simulating a
    status vocabulary drift from an upstream system) - the query-level filter
    must also exclude it, not just the pure function."""
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_weird", status="IN_TRANSIT", awb_number="PRO_WEIRD")
    db_session.execute(
        text("UPDATE transactions SET status = 'BRAND_NEW_STATUS' WHERE id = :id"),
        {"id": order.id},
    )
    db_session.commit()

    resp = client.get("/redemptions/ongoing", headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json() == []


def test_track_endpoint_persists_turn_when_conversation_id_given(
    client, make_user, make_redemption_order, auth_headers, monkeypatch, db_session
):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_track", status="PROCESSING", awb_number=None)

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *args, **kwargs: _FakeMessage("Your order is still being prepared."),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        f"/redemptions/{order.id}/track",
        json={"conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    conversation = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert conversation is not None
    assert conversation.message_count == 2
