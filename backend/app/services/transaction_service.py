import json
import logging
import uuid
from dataclasses import asdict, dataclass

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TRACKABLE_REDEMPTION_STATUSES, Transaction, TxnType, User, is_trackable_redemption
from app.schemas.redemptions import RedemptionOrderOut
from app.services.cache import get_redis

logger = logging.getLogger(__name__)

_NON_REDEMPTION_TYPES = (TxnType.BUY.value, TxnType.SELL.value, TxnType.RECURRING_BUY.value)


@dataclass
class TransactionRecord:
    """Cache-safe, dependency-free projection of a REDEMPTION-type Transaction
    row - returned by both the DB path and the Redis-cache path so callers
    never need to know which one served a given call. Only ever used for the
    cached REDEMPTION path; BUY/SELL/RECURRING_BUY rows are returned as live
    ORM Transaction objects (uncached, matching this app's original
    get_recent_transactions behavior)."""

    id: str
    product: str
    product_type: str | None
    metal_type: str | None
    quantity: float | None
    status: str
    awb_number: str | None
    created_at: str  # ISO 8601, kept as a string end-to-end for trivial JSON round-tripping

    @classmethod
    def from_model(cls, txn: Transaction) -> "TransactionRecord":
        return cls(
            id=txn.id,
            product=txn.product,
            product_type=txn.product_type,
            metal_type=txn.metal_type,
            quantity=float(txn.quantity) if txn.quantity is not None else None,
            status=txn.status,
            awb_number=txn.awb_number,
            created_at=txn.created_at.isoformat(),
        )


def to_redemption_out(record: TransactionRecord) -> RedemptionOrderOut:
    return RedemptionOrderOut(
        order_ref=record.id,
        product_name=record.product,
        product_type=record.product_type or "",
        metal_type=record.metal_type or "",
        quantity=record.quantity or 0.0,
        status=record.status,
        created_at=record.created_at,
    )


def _ongoing_cache_key(user_id: uuid.UUID, limit: int) -> str:
    # v2: bumped from the pre-merge redemption_service's v1 key so a stale
    # cache entry shaped like the old RedemptionOrderRecord is never
    # deserialized into today's TransactionRecord fields. `limit` is part of
    # the key (not just an argument to the query behind it) because a cache
    # entry populated for a smaller limit must never be served back for a
    # larger one - it would silently truncate the larger request's results
    # to whatever the earlier, smaller fetch happened to cache.
    return f"support:ongoing_redemptions:v2:{user_id}:{limit}"


def _query_by_type(db: Session, user_id: uuid.UUID, types: tuple[str, ...], limit: int) -> list[Transaction]:
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id, Transaction.type.in_(types))
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def _query_ongoing_redemptions(db: Session, user_id: uuid.UUID, limit: int) -> list[TransactionRecord]:
    stmt = (
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.type == TxnType.REDEMPTION,
            Transaction.status.in_([s.value for s in TRACKABLE_REDEMPTION_STATUSES]),
        )
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )
    return [TransactionRecord.from_model(t) for t in db.scalars(stmt)]


def _get_ongoing_redemptions_cached(db: Session, user: User, limit: int) -> list[TransactionRecord]:
    """Cache-first (support:ongoing_redemptions:v2:{user_id}:{limit}) - a non-empty
    result is cached for ongoing_redemptions_cache_ttl_seconds, an empty
    result is cached (as a negative cache, absorbing repeated chat retries
    without re-querying) for the shorter
    ongoing_redemptions_negative_cache_ttl_seconds. Any Redis error is
    treated as a cache miss, never surfaced to the caller."""
    key = _ongoing_cache_key(user.id, limit)
    try:
        cached = get_redis().get(key)
        if cached is not None:
            return [TransactionRecord(**row) for row in json.loads(cached)]
    except redis.RedisError:
        logger.warning("Redis unavailable reading %s; falling back to DB", key)

    records = _query_ongoing_redemptions(db, user.id, limit)

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


def get_transactions(
    db: Session, user: User, type: str | None = None, limit: int = 10
) -> tuple[list[Transaction], list[TransactionRecord]]:
    """Unified fetch replacing the old get_recent_transactions +
    redemption_service.get_ongoing_redemptions. Returns (transactions,
    redemptions) - always both lists, one of them empty depending on `type`:

    - type in {BUY, SELL, RECURRING_BUY}: transactions=that one type's full
      history (uncached, unfiltered by status), redemptions=[].
    - type == "TRANSACTION": transactions=all three trading types combined
      (uncached, unfiltered by status - matches this app's original
      get_recent_transactions semantics exactly), redemptions=[]. This is
      the meta-value for a general transaction question naming no specific
      BUY/SELL/RECURRING_BUY activity (e.g. "my last transaction", "my
      transaction status") - distinct from `type is None` below, which also
      pulls in redemptions; a "transaction" question was never asking about
      physical delivery orders.
    - type == REDEMPTION: transactions=[], redemptions=cached, filtered to
      TRACKABLE_REDEMPTION_STATUSES only (matches the original
      get_ongoing_redemptions semantics exactly).
    - type is None: both - BUY/SELL/RECURRING_BUY history (uncached, capped
      at `limit`) and ongoing REDEMPTION orders (cached). Only for a truly
      generic "list ALL my orders" naming no type at all.

    `limit` only ever bounds transaction *history* (BUY/SELL/RECURRING_BUY/
    TRANSACTION) - a customer can realistically have hundreds of past
    transactions, so that needs pagination-style capping. Ongoing REDEMPTION
    orders never respect `limit`: by construction (the TRACKABLE_REDEMPTION_STATUSES
    filter) that set is already only currently-active deliveries, which is
    inherently small for any real customer - nobody has "100 packages in
    transit" - so capping it below settings.orders_list_all_limit only risks
    silently excluding a genuinely active order from tracking/resolve, for
    no real benefit. This was a real, observed bug: a customer's "track the
    in-transit order" failed with "couldn't find that" purely because that
    order fell outside a 3-item cap, even though it was a real, active order.
    """
    if type == TxnType.REDEMPTION.value:
        return [], _get_ongoing_redemptions_cached(db, user, settings.orders_list_all_limit)
    if type in _NON_REDEMPTION_TYPES:
        return _query_by_type(db, user.id, (type,), limit), []
    if type == "TRANSACTION":
        return _query_by_type(db, user.id, _NON_REDEMPTION_TYPES, limit), []
    return (
        _query_by_type(db, user.id, _NON_REDEMPTION_TYPES, limit),
        _get_ongoing_redemptions_cached(db, user, settings.orders_list_all_limit),
    )


def get_transaction_details(db: Session, user: User, transaction_id: str) -> Transaction | None:
    """Returns None (never another user's row) if the transaction doesn't
    exist or doesn't belong to `user`. Callers should map that to a 404,
    not a 403, so we don't confirm the id exists for someone else."""
    stmt = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.user_id == user.id,
    )
    return db.scalars(stmt).first()


def get_redemption_order_by_ref(db: Session, user: User, order_ref: str) -> Transaction | None:
    """Ownership + type scoped only - deliberately does NOT filter by
    trackable status, unlike get_ongoing_transaction_by_ref below. Always
    hits Postgres directly, bypassing the ongoing-orders cache. Used when the
    caller needs to distinguish "this order doesn't exist/isn't yours" from
    "it exists but its status has changed since it was last shown as
    ongoing" (e.g. it was just delivered) - those need different customer-
    facing responses, not the same generic 404."""
    txn = get_transaction_details(db, user, order_ref)
    if txn is None or txn.type != TxnType.REDEMPTION:
        return None
    return txn


def get_ongoing_transaction_by_ref(db: Session, user: User, order_ref: str) -> Transaction | None:
    """Always hits Postgres directly - deliberately bypasses the ongoing-
    orders cache entirely. This is the "re-validate ownership immediately
    before use" requirement: a cached list served a moment ago is fine for
    display, but the actual tracking action re-checks ownership AND current
    trackable status against a live read. Returns None (never another
    user's row, never a since-completed/failed order, never a non-REDEMPTION
    transaction) - callers map that to a generic 404/"not found"."""
    txn = get_redemption_order_by_ref(db, user, order_ref)
    if txn is None or not is_trackable_redemption(txn.status):
        return None
    return txn


def invalidate_ongoing_redemptions_cache(user_id: uuid.UUID) -> None:
    """Clears the cached ongoing-redemptions list for a user - called when a
    live re-check discovers an order's status has moved out of the
    trackable set since it was cached (e.g. just delivered), so a
    subsequent "where is my order" listing doesn't keep showing it as
    active until the cache's own TTL happens to expire. Both limit
    variants are cleared since either could be the one currently cached
    (see _ongoing_cache_key's docstring on why limit is part of the key)."""
    try:
        client = get_redis()
        client.delete(_ongoing_cache_key(user_id, settings.orders_default_limit))
        client.delete(_ongoing_cache_key(user_id, settings.orders_list_all_limit))
    except redis.RedisError:
        logger.warning("Redis unavailable invalidating ongoing-redemptions cache for %s", user_id)
