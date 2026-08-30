import httpx
import pytest

from app.services import tracking_service
from app.services.tracking_fixtures import TRACKING_FIXTURES


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """The circuit breaker is module-level state - reset it before and after
    every test so one test's failures can't leak into another's."""
    tracking_service._consecutive_failures = 0
    tracking_service._breaker_open_until = 0.0
    yield
    tracking_service._consecutive_failures = 0
    tracking_service._breaker_open_until = 0.0


@pytest.mark.parametrize("awb", ["PRO19460772", "PRO19460773", "PRO19460774"])
def test_get_tracking_normalizes_response_for_each_fixture_awb(awb, monkeypatch, flush_redis):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, TRACKING_FIXTURES[awb]))

    lookup = tracking_service.get_tracking(awb)

    expected_history = TRACKING_FIXTURES[awb]["data"]["tracking"]["history"]
    assert len(lookup.history) == len(expected_history)
    assert lookup.latest_event.area == expected_history[-1]["area"]
    assert lookup.current_location == expected_history[-1]["area"]
    assert lookup.stale is False


def test_get_tracking_can_look_up_delivered_awb_directly(monkeypatch, flush_redis):
    """The DELIVERED order is excluded from active chat discovery, but the
    tracking service itself should still be able to track it directly, per
    the spec's own note."""
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, TRACKING_FIXTURES["PRO19460771"]))

    lookup = tracking_service.get_tracking("PRO19460771")

    assert lookup.current_location == "Udayagiri"


def test_get_tracking_retries_on_timeout_then_succeeds(monkeypatch, flush_redis):
    calls = {"count": 0}

    def fake_get(*a, **k):
        calls["count"] += 1
        if calls["count"] < 2:
            raise httpx.TimeoutException("timed out")
        return _FakeResponse(200, TRACKING_FIXTURES["PRO19460772"])

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(tracking_service.settings, "tracking_retry_backoff_seconds", 0.0)

    lookup = tracking_service.get_tracking("PRO19460772")

    assert calls["count"] == 2
    assert lookup.current_location is not None


def test_get_tracking_never_retries_on_404(monkeypatch, flush_redis):
    calls = {"count": 0}

    def fake_get(*a, **k):
        calls["count"] += 1
        return _FakeResponse(404)

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(tracking_service.TrackingNotFoundError):
        tracking_service.get_tracking("UNKNOWN_AWB")

    assert calls["count"] == 1


def test_get_tracking_caches_result_avoiding_second_upstream_call(monkeypatch, flush_redis):
    calls = {"count": 0}

    def fake_get(*a, **k):
        calls["count"] += 1
        return _FakeResponse(200, TRACKING_FIXTURES["PRO19460773"])

    monkeypatch.setattr(httpx, "get", fake_get)

    tracking_service.get_tracking("PRO19460773")
    tracking_service.get_tracking("PRO19460773")

    assert calls["count"] == 1


def test_get_tracking_circuit_breaker_short_circuits_after_threshold(monkeypatch, flush_redis):
    calls = {"count": 0}

    def fake_get(*a, **k):
        calls["count"] += 1
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(tracking_service.settings, "tracking_retry_backoff_seconds", 0.0)
    monkeypatch.setattr(tracking_service.settings, "tracking_max_retries", 0)
    monkeypatch.setattr(tracking_service.settings, "tracking_circuit_breaker_threshold", 2)
    monkeypatch.setattr(tracking_service.settings, "tracking_circuit_breaker_cooldown_seconds", 30.0)

    with pytest.raises(tracking_service.TrackingUnavailableError):
        tracking_service.get_tracking("PRO_BREAKER_1")
    with pytest.raises(tracking_service.TrackingUnavailableError):
        tracking_service.get_tracking("PRO_BREAKER_2")

    calls_before_breaker_opens = calls["count"]
    assert calls_before_breaker_opens == 2

    # Breaker should now be open - a third call must not even attempt httpx.get.
    with pytest.raises(tracking_service.TrackingUnavailableError):
        tracking_service.get_tracking("PRO_BREAKER_3")
    assert calls["count"] == calls_before_breaker_opens


def test_get_tracking_falls_back_to_stale_cache_on_upstream_failure(monkeypatch, flush_redis):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, TRACKING_FIXTURES["PRO19460774"]))
    tracking_service.get_tracking("PRO19460774")  # populates both the primary and stale-shadow cache keys

    def fake_get_failing(*a, **k):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", fake_get_failing)
    monkeypatch.setattr(tracking_service.settings, "tracking_retry_backoff_seconds", 0.0)
    # Clear only the primary cache key so the stale-shadow fallback path is
    # actually exercised, not the ordinary cache-hit path.
    tracking_service.cache_service.get_redis().delete(tracking_service._tracking_cache_key("PRO19460774"))

    lookup = tracking_service.get_tracking("PRO19460774")

    assert lookup.stale is True
    assert lookup.current_location is not None
