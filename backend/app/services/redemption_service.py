import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import RedemptionOrder, TRACKABLE_REDEMPTION_STATUSES, User, is_trackable_redemption
from app.schemas.redemptions import RedemptionOrderOut
from app.services.cache import get_redis

logger = logging.getLogger(__name__)


@dataclass
class RedemptionOrderRecord:
    """Cache-safe, dependency-free representation of a RedemptionOrder row -
    returned by both the DB path and the Redis-cache path so callers never
    need to know which one served a given call."""

    id: str
    txn_id: str
    product_name: str
    product_type: str
    metal_type: str
    quantity_purchased: float
    txn_status: str
    awb_number: str | None
    created_at: str  # ISO 8601, kept as a string end-to-end for trivial JSON round-tripping

    @classmethod
    def from_model(cls, order: RedemptionOrder) -> "RedemptionOrderRecord":
        return cls(
            id=str(order.id),
            txn_id=order.txn_id,
            product_name=order.product_name,
            product_type=order.product_type,
            metal_type=order.metal_type,
            quantity_purchased=float(order.quantity_purchased),
            txn_status=order.txn_status,
            awb_number=order.awb_number,
            created_at=order.created_at.isoformat(),
        )


def to_order_out(order: RedemptionOrderRecord) -> RedemptionOrderOut:
    return RedemptionOrderOut(
        order_ref=order.id,
        product_name=order.product_name,
        product_type=order.product_type,
        metal_type=order.metal_type,
        quantity=order.quantity_purchased,
        status=order.txn_status,
        created_at=order.created_at,
    )


def _ongoing_cache_key(user_id: uuid.UUID) -> str:
    return f"support:ongoing_redemptions:v1:{user_id}"


def _query_ongoing(db: Session, user_id: uuid.UUID) -> list[RedemptionOrderRecord]:
    stmt = (
        select(RedemptionOrder)
        .where(
            RedemptionOrder.user_id == user_id,
            RedemptionOrder.txn_status.in_([s.value for s in TRACKABLE_REDEMPTION_STATUSES]),
        )
        .order_by(RedemptionOrder.created_at.desc())
        .limit(10)
    )
    return [RedemptionOrderRecord.from_model(o) for o in db.scalars(stmt)]


def get_ongoing_redemptions(db: Session, user: User) -> list[RedemptionOrderRecord]:
    """Cache-first (support:ongoing_redemptions:v1:{user_id}) - a non-empty
    result is cached for ongoing_redemptions_cache_ttl_seconds, an empty
    result is cached (as a negative cache, absorbing repeated chat retries
    without re-querying) for the shorter
    ongoing_redemptions_negative_cache_ttl_seconds. Any Redis error is
    treated as a cache miss, never surfaced to the caller."""
    key = _ongoing_cache_key(user.id)
    try:
        cached = get_redis().get(key)
        if cached is not None:
            return [RedemptionOrderRecord(**row) for row in json.loads(cached)]
    except redis.RedisError:
        logger.warning("Redis unavailable reading %s; falling back to DB", key)

    records = _query_ongoing(db, user.id)

    try:
        ttl = (
            settings.ongoing_redemptions_cache_ttl_seconds
            if records
            else settings.ongoing_redemptions_negative_cache_ttl_seconds
        )
        get_redis().set(key, json.dumps([asdict(r) for r in records]), ex=ttl)
    except redis.RedisError:
        logger.warning("Redis unavailable writing %s; result not cached", key)

    return records


def get_ongoing_redemption_by_ref(db: Session, user: User, order_ref: str) -> RedemptionOrderRecord | None:
    """Always hits Postgres directly - deliberately bypasses the ongoing-orders
    cache entirely. This is the "re-validate ownership immediately before
    use" requirement: a cached list served a moment ago is fine for display,
    but the actual tracking action re-checks ownership AND current
    trackable-status against a live read. Returns None (never another user's
    row, never a since-completed/failed order) - callers map that to a
    generic 404/"not found", exactly like transaction_service.get_transaction_details."""
    try:
        order_id = uuid.UUID(order_ref)
    except ValueError:
        return None

    stmt = select(RedemptionOrder).where(RedemptionOrder.id == order_id, RedemptionOrder.user_id == user.id)
    order = db.scalars(stmt).first()
    if order is None or not is_trackable_redemption(order.txn_status):
        return None
    return RedemptionOrderRecord.from_model(order)
