from app.services import rate_limit


def test_rate_limit_allows_up_to_the_limit_then_blocks(flush_redis):
    user_id = "user-a"
    results = [rate_limit.is_allowed(user_id, "redemption_track", limit=3, window_seconds=60) for _ in range(5)]
    assert results == [True, True, True, False, False]


def test_rate_limit_is_scoped_per_user(flush_redis):
    assert all(rate_limit.is_allowed("user-b", "redemption_track", limit=2, window_seconds=60) for _ in range(2))
    # A different user has their own independent counter, unaffected by user-b's usage.
    assert rate_limit.is_allowed("user-c", "redemption_track", limit=2, window_seconds=60) is True


def test_rate_limit_is_scoped_per_action(flush_redis):
    user_id = "user-d"
    assert all(rate_limit.is_allowed(user_id, "redemption_track", limit=2, window_seconds=60) for _ in range(2))
    # A different action for the same user has its own independent counter.
    assert rate_limit.is_allowed(user_id, "some_other_action", limit=2, window_seconds=60) is True


def test_rate_limit_fails_open_when_redis_unavailable(monkeypatch):
    """A rate-limiter outage must never become a customer-facing outage -
    same fail-open policy as every other Redis-backed cache in this app."""
    import redis as redis_module

    def broken_get_redis():
        raise redis_module.RedisError("connection refused")

    monkeypatch.setattr(rate_limit, "get_redis", broken_get_redis)

    assert rate_limit.is_allowed("user-e", "redemption_track", limit=1, window_seconds=60) is True


def test_track_endpoint_returns_429_after_exceeding_limit(
    client, make_user, make_redemption_order, auth_headers, monkeypatch, flush_redis
):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_rate", status="PROCESSING", awb_number=None)
    monkeypatch.setattr("app.routers.redemptions.settings.redemption_track_rate_limit", 2)

    for _ in range(2):
        resp = client.post(f"/redemptions/{order.id}/track", headers=auth_headers(alice))
        assert resp.status_code == 200

    resp = client.post(f"/redemptions/{order.id}/track", headers=auth_headers(alice))
    assert resp.status_code == 429


def test_track_endpoint_stays_under_limit_for_normal_use(
    client, make_user, make_redemption_order, auth_headers, flush_redis
):
    """A customer clicking through a handful of orders in one session must
    never be rate-limited - the default limit is generous specifically so
    normal use is unaffected."""
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_normal", status="PROCESSING", awb_number=None)

    for _ in range(5):
        resp = client.post(f"/redemptions/{order.id}/track", headers=auth_headers(alice))
        assert resp.status_code == 200
