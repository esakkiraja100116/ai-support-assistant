def test_login_returns_token_for_known_user(client, make_user):
    make_user(username="alice", display_name="Alice")

    resp = client.post("/auth/login", json={"username": "alice"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["display_name"] == "Alice"


def test_login_rejects_unknown_user(client):
    resp = client.post("/auth/login", json={"username": "nobody"})
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    resp = client.get("/transactions/recent")
    assert resp.status_code == 401


def test_protected_route_rejects_invalid_token(client):
    resp = client.get("/transactions/recent", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
