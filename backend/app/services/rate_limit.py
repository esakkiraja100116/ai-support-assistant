"""Fixed-window rate limiter, scoped per authenticated user per action.

Exists specifically to bound abusive repeated tracking requests without
punishing legitimate use: a customer re-checking the same order a few times
is cheap regardless (get_tracking()/get_transactions() are already
cache-first, so a legitimate retry rarely even reaches the DB or upstream
API) - this only needs to catch raw request-*volume* abuse at the action
boundary itself, independent of whether any given request would have been a
cache hit.

Redis INCR + EXPIRE-if-new is the whole mechanism: cheap, atomic per key, and
consistent with every other Redis usage in this app. Fails open (never
blocks a request) if Redis itself is unavailable, same policy as every other
cache in this app - a rate-limiter outage must never become a customer-facing
outage.
"""
import logging

import redis

from app.services.cache import get_redis

logger = logging.getLogger(__name__)


def _rate_limit_key(user_id: str, action: str) -> str:
    return f"support:ratelimit:v1:{action}:{user_id}"


def is_allowed(user_id: str, action: str, limit: int, window_seconds: int) -> bool:
    """True if this request should proceed, False if `user_id` has already
    made `limit` or more `action` requests within the current window."""
    key = _rate_limit_key(user_id, action)
    try:
        client = get_redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        return count <= limit
    except redis.RedisError:
        logger.warning("Redis unavailable checking rate limit for %s; allowing request", key)
        return True
