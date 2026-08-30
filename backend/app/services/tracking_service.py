"""Wraps the internal mock tracking API (app/routers/internal_tracking.py)
with validation, a bounded timeout/retry policy, a lightweight in-process
circuit breaker, Redis caching (with a stale-fallback shadow key for graceful
degradation), and a request-coalescing lock so concurrent lookups for the
same AWB don't fan out into duplicate upstream calls.
"""
import json
import logging
import time
from dataclasses import dataclass

import httpx
import redis

from app.config import settings
from app.schemas.redemptions import TrackingEvent
from app.services import cache as cache_service

logger = logging.getLogger(__name__)


class TrackingError(Exception):
    """Base for every tracking failure this module raises - callers can
    catch this broadly and degrade gracefully without needing to distinguish
    "not found" from "unavailable" for the customer-facing response."""


class TrackingNotFoundError(TrackingError):
    pass


class TrackingUnavailableError(TrackingError):
    pass


class TrackingMalformedError(TrackingError):
    pass


@dataclass
class TrackingLookup:
    current_location: str | None
    latest_event: TrackingEvent | None
    history: list[TrackingEvent]
    stale: bool = False


# Module-level, per-process circuit breaker state. Scoped down from a full
# stateful breaker library since this is a single backend process - the
# request-coalescing lock already protects against upstream overload from
# concurrent requests, this just stops a clearly-down upstream from being
# hammered by sequential requests for a cooldown window.
_consecutive_failures = 0
_breaker_open_until: float = 0.0


def _breaker_is_open() -> bool:
    return time.monotonic() < _breaker_open_until


def _record_failure() -> None:
    global _consecutive_failures, _breaker_open_until
    _consecutive_failures += 1
    if _consecutive_failures >= settings.tracking_circuit_breaker_threshold:
        _breaker_open_until = time.monotonic() + settings.tracking_circuit_breaker_cooldown_seconds


def _record_success() -> None:
    global _consecutive_failures
    _consecutive_failures = 0


def _tracking_cache_key(awb: str) -> str:
    return f"support:tracking:v1:{awb}"


def _tracking_stale_key(awb: str) -> str:
    return f"support:tracking:stale:v1:{awb}"


def _lock_key(awb: str) -> str:
    return f"support:tracking_lock:v1:{awb}"


def _fetch_from_internal_api(awb: str) -> dict:
    if _breaker_is_open():
        raise TrackingUnavailableError(f"circuit open for {awb}")

    url = f"{settings.internal_tracking_base_url}/internal/tracking/{awb}"
    last_exc: Exception | None = None
    for attempt in range(settings.tracking_max_retries + 1):
        try:
            resp = httpx.get(url, timeout=settings.tracking_timeout_seconds)
            if resp.status_code == 404:
                # A definitive "not found" is not an upstream health problem -
                # never retried, and doesn't count against the circuit breaker.
                raise TrackingNotFoundError(awb)
            resp.raise_for_status()
            _record_success()
            return resp.json()
        except TrackingNotFoundError:
            raise
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < settings.tracking_max_retries:
                time.sleep(settings.tracking_retry_backoff_seconds * (attempt + 1))

    _record_failure()
    raise TrackingUnavailableError(awb) from last_exc


def _normalize(raw: dict) -> TrackingLookup:
    try:
        history_raw = raw["data"]["tracking"]["history"]
        history = [
            TrackingEvent(type=h["type"], remarks=h["remarks"], area=h["area"], event_time=h["event_time"])
            for h in history_raw
        ]
    except (KeyError, TypeError) as exc:
        raise TrackingMalformedError(str(exc)) from exc

    latest = history[-1] if history else None
    return TrackingLookup(current_location=latest.area if latest else None, latest_event=latest, history=history)


def _serialize(lookup: TrackingLookup) -> str:
    return json.dumps(
        {
            "current_location": lookup.current_location,
            "latest_event": lookup.latest_event.model_dump(mode="json") if lookup.latest_event else None,
            "history": [e.model_dump(mode="json") for e in lookup.history],
        }
    )


def _deserialize(raw: str, stale: bool) -> TrackingLookup:
    payload = json.loads(raw)
    latest = TrackingEvent(**payload["latest_event"]) if payload["latest_event"] else None
    history = [TrackingEvent(**e) for e in payload["history"]]
    return TrackingLookup(current_location=payload["current_location"], latest_event=latest, history=history, stale=stale)


def _cache_write(awb: str, lookup: TrackingLookup) -> None:
    payload = _serialize(lookup)
    try:
        client = cache_service.get_redis()
        client.set(_tracking_cache_key(awb), payload, ex=settings.tracking_cache_ttl_seconds)
        client.set(_tracking_stale_key(awb), payload, ex=settings.tracking_stale_cache_ttl_seconds)
    except redis.RedisError:
        logger.warning("Redis unavailable caching tracking result for %s", awb)


def _stale_fallback(awb: str) -> TrackingLookup | None:
    try:
        raw = cache_service.get_redis().get(_tracking_stale_key(awb))
    except redis.RedisError:
        return None
    return _deserialize(raw, stale=True) if raw is not None else None


def get_tracking(awb: str) -> TrackingLookup:
    """Cache-first. On a cache miss, acquires a short request-coalescing lock
    before calling upstream; if the lock is already held (another concurrent
    request for the same AWB is fetching), polls the cache briefly instead of
    firing a redundant call, falling through to its own fetch if the wait
    times out rather than blocking indefinitely on someone else's lock. On
    any upstream failure, falls back to a longer-lived stale cache entry
    (stale=True) rather than a hard error, if one exists."""
    cache_key = _tracking_cache_key(awb)
    try:
        cached = cache_service.get_redis().get(cache_key)
        if cached is not None:
            return _deserialize(cached, stale=False)
    except redis.RedisError:
        logger.warning("Redis unavailable reading %s; proceeding to upstream", cache_key)

    lock_key = _lock_key(awb)
    got_lock = cache_service.acquire_lock(lock_key, settings.tracking_lock_ttl_seconds)
    if not got_lock:
        for _ in range(4):
            time.sleep(0.5)
            try:
                cached = cache_service.get_redis().get(cache_key)
            except redis.RedisError:
                cached = None
            if cached is not None:
                return _deserialize(cached, stale=False)
        # Still nothing after a short wait - proceed with our own fetch
        # rather than blocking indefinitely on someone else's lock.

    try:
        lookup = _normalize(_fetch_from_internal_api(awb))
        _cache_write(awb, lookup)
        return lookup
    except TrackingError:
        stale = _stale_fallback(awb)
        if stale is not None:
            return stale
        raise
    finally:
        if got_lock:
            cache_service.release_lock(lock_key)
