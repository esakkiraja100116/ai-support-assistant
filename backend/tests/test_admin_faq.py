from app.models import SupportArticle


def test_admin_can_create_faq_article(client, make_user, auth_headers, monkeypatch):
    admin = make_user("admin", "Admin", role="ADMINISTRATOR")

    embed_calls = []

    def fake_embed(text):
        embed_calls.append(text)
        return [0.1] * 1536

    monkeypatch.setattr("app.routers.admin.llm_client.embed", fake_embed)

    payload = {
        "question": "Do you support international wire transfers?",
        "answer": "Not currently - only UPI, card, and net banking are supported.",
        "category": "payments",
    }
    resp = client.post("/admin/faq", json=payload, headers=auth_headers(admin))

    assert resp.status_code == 201
    body = resp.json()
    assert body["question"] == payload["question"]

    # Embeds the question alone, matching scripts/seed.py's already-fixed
    # dilution bug - never question+answer combined.
    assert embed_calls == [payload["question"]]

    faq_resp = client.get("/faq")
    assert any(a["question"] == payload["question"] for a in faq_resp.json())


def test_non_admin_cannot_create_faq_article(client, make_user, auth_headers):
    alice = make_user("alice", "Alice", role="USER")
    resp = client.post(
        "/admin/faq",
        json={"question": "Q?", "answer": "A."},
        headers=auth_headers(alice),
    )
    assert resp.status_code == 403
