"""Single shared Redis seam - same "one choke point" idea as llm_client.py
for LLM calls. Every caller wraps Redis access in try/except and treats any
failure as a cache miss - Redis being down must only make the redemption
tracking feature slower/less cached, never break it.
"""
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def acquire_lock(key: str, ttl_seconds: int) -> bool:
    """Best-effort request-coalescing lock via SET NX EX. Returns False (never
    raises) on any Redis error, treated by callers as "couldn't get the lock,
    proceed without it" rather than "block forever"."""
    try:
        return bool(get_redis().set(key, "1", nx=True, ex=ttl_seconds))
    except redis.RedisError:
        logger.warning("Redis unavailable acquiring lock %s; proceeding without it", key)
        return False


def release_lock(key: str) -> None:
    try:
        get_redis().delete(key)
    except redis.RedisError:
        logger.warning("Redis unavailable releasing lock %s", key)
