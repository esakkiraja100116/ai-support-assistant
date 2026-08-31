"""Verification tests for the 12-row redemption-tracking edge-case spec the
product owner supplied. Each test is labeled with the spec row it checks.
Some intentionally document current (imperfect) behavior rather than assert
the spec's exact wording, where the app's behavior diverges - see the
docstring on those tests and the accompanying gap report.
"""
import httpx
import pytest

from app.models import RedemptionOrder
from app.services import redemption_service, tracking_service


class _FakeFunction:
    def __init__(self, name: str, arguments: str = "{}"):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name: str, arguments: str = "{}"):
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls
        self.content = content


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def _tool_names(tools):
    return [t["function"]["name"] for t in (tools or [])]


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    tracking_service._consecutive_failures = 0
    tracking_service._breaker_open_until = 0.0
    yield
    tracking_service._consecutive_failures = 0
    tracking_service._breaker_open_until = 0.0


# Row 2: only completed/delivered orders exist.
def test_row2_only_delivered_order_returns_no_ongoing_orders_message(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_delivered", status="DELIVERED", awb_number="PRO_DELIVERED")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_ongoing_redemptions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_ongoing_redemptions")])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("must not call tracking API")),
    )

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TEXT_ANSWER"
    assert "don't have any ongoing redemption orders" in body["message"]


# Row 3: only failed/cancelled/rejected orders exist.
def test_row3_only_failed_cancelled_rejected_orders_return_no_ongoing_orders_message(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_failed", status="FAILED", awb_number=None)
    make_redemption_order(alice, "txn_cancelled", status="CANCELLED", awb_number=None)
    make_redemption_order(alice, "txn_rejected", status="REJECTED", awb_number=None)

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_ongoing_redemptions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_ongoing_redemptions")])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("must not call tracking API")),
    )

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TEXT_ANSWER"
    assert "don't have any ongoing redemption orders" in body["message"]


# Row 5 (stronger variant): a resolve call that names ANOTHER real user's
# actual order_ref (not just a hallucinated/malformed UUID) must still be
# rejected and fall back to the safe selection list - proving the
# re-authorization check is by-ownership, not just by-existence.
def test_row5_resolve_cannot_be_tricked_into_another_users_real_order(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    make_redemption_order(alice, "txn_a", status="IN_TRANSIT", awb_number="PRO_A")
    make_redemption_order(alice, "txn_b", status="OUT_FOR_DELIVERY", awb_number="PRO_B")
    bobs_order = make_redemption_order(bob, "txn_bob", status="IN_TRANSIT", awb_number="PRO_BOB")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_ongoing_redemptions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_ongoing_redemptions")])
        if "resolve_redemption_order" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_redemption_order", f'{{"order_ref": "{bobs_order.id}"}}')]
            )
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("tracking must not be called for another user's order")),
    )

    resp = client.post("/chat", json={"message": "track my order"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["type"] == "REDEMPTION_SELECTION"


# Row 6: the tool schema takes no arguments at all - the model can never pass
# a raw AWB (or anything else) as an identifier. Confirms directly at the
# service layer that a real AWB/order belonging to another user, looked up by
# ITS OWNER's own order id, returns None (never another user's row) for a
# non-owner - the same generic "not found", never revealing existence.
def test_row6_awb_lookup_never_reveals_another_users_order(
    db_session, make_user, make_redemption_order
):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    bobs_order = make_redemption_order(bob, "txn_bob2", status="IN_TRANSIT", awb_number="PRO_BOB_2")

    result = redemption_service.get_ongoing_redemption_by_ref(db_session, alice, str(bobs_order.id))

    assert result is None


# Row 7: a 404/unknown AWB from the tracking API. Documents CURRENT behavior:
# the customer-facing message does not currently distinguish "not found" from
# a generic transient failure (see gap report) - this asserts what the app
# does today, not the spec's suggested distinct wording.
def test_row7_404_from_tracking_api_does_not_leak_raw_upstream_error(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_404", status="IN_TRANSIT", awb_number="PRO_404")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_ongoing_redemptions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_ongoing_redemptions")])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(404))

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_TRACKING"
    # No raw exception text, status code, or upstream URL leaks to the customer.
    for leak in ("404", "Traceback", "internal_tracking", "HTTPStatusError"):
        assert leak not in body["message"]


# Row 8: upstream failure with a valid stale cache available - the customer
# still gets a tracking answer, marked stale, instead of a hard failure.
def test_row8_stale_cache_used_and_flagged_when_upstream_fails(
    client, make_user, make_redemption_order, auth_headers, monkeypatch, flush_redis
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_stale", status="IN_TRANSIT", awb_number="PRO_STALE")

    good_payload = {
        "data": {
            "tracking": {
                "history": [
                    {"type": "InTransit", "remarks": "Departed hub", "area": "Chennai", "event_time": "2026-08-29T08:00:00+00:00"}
                ]
            }
        }
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, good_payload))
    tracking_service.get_tracking("PRO_STALE")  # populate primary + stale cache

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_ongoing_redemptions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_ongoing_redemptions")])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.TimeoutException("down")))
    monkeypatch.setattr(tracking_service.settings, "tracking_retry_backoff_seconds", 0.0)
    tracking_service.cache_service.get_redis().delete(tracking_service._tracking_cache_key("PRO_STALE"))

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_TRACKING"
    assert body["data"]["tracking"]["stale"] is True
    assert body["data"]["tracking"]["current_location"] == "Chennai"


# Row 9: a malformed upstream response (missing expected keys) must raise a
# distinct, caught error - never propagate raw/partial data anywhere, and
# never crash the request.
def test_row9_malformed_upstream_response_is_rejected_not_propagated(monkeypatch, flush_redis):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, {"data": {"oops": "no tracking key"}}))

    with pytest.raises(tracking_service.TrackingMalformedError):
        tracking_service.get_tracking("PRO_MALFORMED")


def test_row9_malformed_upstream_response_gives_customer_generic_answer_not_500(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_malformed", status="IN_TRANSIT", awb_number="PRO_MALFORMED_2")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_ongoing_redemptions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_ongoing_redemptions")])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, {"data": {}}))

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_TRACKING"
    assert body["data"]["tracking"]["history"] == []


# Row 11: the order's status changes to DELIVERED between being listed as
# ongoing and the customer actually selecting/tracking it. Documents CURRENT
# behavior - see gap report on whether this matches "return the latest state".
def test_row11_order_delivered_between_listing_and_track_click(
    client, make_user, make_redemption_order, auth_headers, db_session
):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_race", status="IN_TRANSIT", awb_number="PRO_RACE")

    # Simulate the status changing (e.g. courier webhook) after the order was
    # already shown to the customer as "ongoing".
    db_session.execute(
        RedemptionOrder.__table__.update().where(RedemptionOrder.id == order.id).values(txn_status="DELIVERED")
    )
    db_session.commit()

    resp = client.post(f"/redemptions/{order.id}/track", headers=auth_headers(alice))

    assert resp.status_code == 404


# Row 12: an order with a status this app's enum doesn't recognize at all.
# Confirms fail-closed exclusion AND checks whether anything is logged for
# domain-mapping review (see gap report).
def test_row12_unknown_status_excluded_and_check_for_logging(
    client, make_user, make_redemption_order, auth_headers, db_session, caplog
):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_unknown_status", status="IN_TRANSIT", awb_number="PRO_UNKNOWN")
    db_session.execute(
        RedemptionOrder.__table__.update().where(RedemptionOrder.id == order.id).values(txn_status="SOME_NEW_COURIER_STATE")
    )
    db_session.commit()

    with caplog.at_level("WARNING"):
        resp = client.get("/redemptions/ongoing", headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json() == []  # fails closed - not shown as active

    # Gap check: is there any log record at all mentioning the unrecognized
    # status, for a human to review and map it into the known enum? This is
    # expected to FAIL today - see the gap report.
    mentions_unknown_status = any("SOME_NEW_COURIER_STATE" in r.message for r in caplog.records)
    assert mentions_unknown_status, (
        "no log/metric is emitted anywhere for an unrecognized redemption status - "
        "it is silently excluded with no domain-mapping-review signal"
    )
