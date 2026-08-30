import pytest

ADMIN_GET_ROUTES = ["/admin/users", "/admin/transactions", "/admin/redemptions", "/admin/conversations", "/admin/costs"]


@pytest.mark.parametrize("route", ADMIN_GET_ROUTES)
def test_non_admin_gets_403(client, make_user, auth_headers, route):
    alice = make_user("alice", "Alice", role="USER")
    resp = client.get(route, headers=auth_headers(alice))
    assert resp.status_code == 403


@pytest.mark.parametrize("route", ADMIN_GET_ROUTES)
def test_unauthenticated_gets_401(client, route):
    resp = client.get(route)
    assert resp.status_code == 401


def test_admin_sees_data_across_multiple_users(
    client, make_user, make_transaction, make_redemption_order, make_conversation, auth_headers
):
    admin = make_user("admin", "Admin", role="ADMINISTRATOR")
    alice = make_user("alice", "Alice", role="USER")
    bob = make_user("bob", "Bob", role="USER")
    make_transaction(alice, "txn_a1")
    make_transaction(bob, "txn_b1")
    make_redemption_order(alice, "txn_r_a1", awb_number="PRO_A1")
    make_redemption_order(bob, "txn_r_b1", awb_number="PRO_B1")
    make_conversation(alice, title="Alice's chat")
    make_conversation(bob, title="Bob's chat")

    users_resp = client.get("/admin/users", headers=auth_headers(admin))
    assert users_resp.status_code == 200
    usernames = {u["username"] for u in users_resp.json()}
    assert {"admin", "alice", "bob"} <= usernames
    redemption_counts = {u["username"]: u["redemption_order_count"] for u in users_resp.json()}
    assert redemption_counts["alice"] == 1
    assert redemption_counts["bob"] == 1

    txn_resp = client.get("/admin/transactions", headers=auth_headers(admin))
    assert txn_resp.status_code == 200
    txn_users = {t["username"] for t in txn_resp.json()}
    assert txn_users == {"alice", "bob"}

    redemptions_resp = client.get("/admin/redemptions", headers=auth_headers(admin))
    assert redemptions_resp.status_code == 200
    redemption_users = {o["username"] for o in redemptions_resp.json()}
    assert redemption_users == {"alice", "bob"}

    convo_resp = client.get("/admin/conversations", headers=auth_headers(admin))
    assert convo_resp.status_code == 200
    convo_users = {c["username"] for c in convo_resp.json()}
    assert convo_users == {"alice", "bob"}


def test_admin_can_view_any_conversation_transcript(client, make_user, make_conversation, make_message, auth_headers):
    admin = make_user("admin", "Admin", role="ADMINISTRATOR")
    alice = make_user("alice", "Alice", role="USER")
    conversation = make_conversation(alice, title="Alice's chat")
    make_message(conversation, "user", "hello")
    make_message(conversation, "assistant", "hi there")

    resp = client.get(f"/admin/conversations/{conversation.id}", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 2


def test_admin_conversation_transcript_404_for_nonexistent_id(client, make_user, auth_headers):
    admin = make_user("admin", "Admin", role="ADMINISTRATOR")
    resp = client.get("/admin/conversations/00000000-0000-0000-0000-000000000000", headers=auth_headers(admin))
    assert resp.status_code == 404
