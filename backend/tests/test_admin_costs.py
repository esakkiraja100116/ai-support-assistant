import pytest


def test_admin_costs_summary(client, make_user, make_conversation, make_message, auth_headers, db_session):
    admin = make_user("admin", "Admin", role="ADMINISTRATOR")
    alice = make_user("alice", "Alice", role="USER")
    bob = make_user("bob", "Bob", role="USER")

    conv_a = make_conversation(alice, title="Alice A")
    conv_b = make_conversation(bob, title="Bob B")

    make_message(conv_a, "user", "hi")
    make_message(
        conv_a, "assistant", "General answer", response_type="TEXT_ANSWER", model_used="gpt-4o-mini", cost_usd=0.01
    )
    make_message(conv_a, "user", "why did it fail?")
    make_message(
        conv_a,
        "assistant",
        "Explanation",
        response_type="TRANSACTION_EXPLANATION",
        model_used="gpt-5.6-sol",
        cost_usd=0.05,
    )

    make_message(conv_b, "user", "hi")
    make_message(
        conv_b, "assistant", "General answer", response_type="TEXT_ANSWER", model_used="gpt-4o-mini", cost_usd=0.02
    )

    # The Conversation-level rollup would normally be kept in sync by
    # conversation_service.add_assistant_message; these fixtures insert raw
    # Message rows directly, so the rollup is set explicitly here for the
    # top_conversations part of the summary.
    conv_a.total_cost_usd = 0.06
    conv_b.total_cost_usd = 0.02
    db_session.commit()

    resp = client.get("/admin/costs", headers=auth_headers(admin))
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_cost_usd"] == pytest.approx(0.08)

    by_model = {row["model"]: row for row in body["by_model"]}
    assert by_model["gpt-4o-mini"]["cost_usd"] == pytest.approx(0.03)
    assert by_model["gpt-4o-mini"]["calls"] == 2
    assert by_model["gpt-5.6-sol"]["cost_usd"] == pytest.approx(0.05)
    assert by_model["gpt-5.6-sol"]["calls"] == 1

    by_category = {row["category"]: row for row in body["by_category"]}
    assert by_category["general"]["cost_usd"] == pytest.approx(0.03)
    assert by_category["transaction"]["cost_usd"] == pytest.approx(0.05)

    top = body["top_conversations"]
    assert top[0]["title"] == "Alice A"
    assert top[0]["cost_usd"] == pytest.approx(0.06)
    assert top[1]["title"] == "Bob B"


def test_non_admin_cannot_view_costs(client, make_user, auth_headers):
    alice = make_user("alice", "Alice", role="USER")
    resp = client.get("/admin/costs", headers=auth_headers(alice))
    assert resp.status_code == 403
