import enum
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TxnType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    RECURRING_BUY = "RECURRING_BUY"
    REDEMPTION = "REDEMPTION"


class TxnStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Role(str, enum.Enum):
    ADMINISTRATOR = "ADMINISTRATOR"
    USER = "USER"


class RedemptionStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    ATTEMPTED = "ATTEMPTED"
    DELIVERED = "DELIVERED"
    SUCCESS = "SUCCESS"
    ORDER_SUCCESSFULL = "ORDER_SUCCESSFULL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    REFUNDED = "REFUNDED"


# Ongoing/trackable statuses only - completed (DELIVERED/SUCCESS/ORDER_SUCCESSFULL) and
# terminal-failure (FAILED/CANCELLED/REJECTED/REFUNDED) statuses are excluded by
# construction (simply not listed here), not by a separate exclusion check - so a
# status this app doesn't yet recognize can never accidentally end up "trackable".
TRACKABLE_REDEMPTION_STATUSES: frozenset[RedemptionStatus] = frozenset(
    {
        RedemptionStatus.PROCESSING,
        RedemptionStatus.ORDER_CONFIRMED,
        RedemptionStatus.PACKED,
        RedemptionStatus.SHIPPED,
        RedemptionStatus.IN_TRANSIT,
        RedemptionStatus.OUT_FOR_DELIVERY,
        RedemptionStatus.ATTEMPTED,
    }
)


def is_trackable_redemption(status: str) -> bool:
    """Fail closed: a genuinely unrecognized status (not just an excluded known
    one) returns False, never True - centralizing this as one function rather
    than an inline string comparison is a spec requirement, since status
    vocabularies commonly drift between systems."""
    try:
        return RedemptionStatus(status) in TRACKABLE_REDEMPTION_STATUSES
    except ValueError:
        return False


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(String(16), default=Role.USER)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")


class Transaction(Base):
    """A BUY/SELL/RECURRING_BUY trading transaction, or a REDEMPTION (physical
    gold delivery order). `status`'s valid-value set depends on `type`:
    TxnStatus for the trading types, RedemptionStatus for REDEMPTION - both
    were always just Python-side hints over a plain VARCHAR column, not a DB
    enum, so this dual vocabulary is continuity, not a new looseness.

    `amount`/`payment_method` are nullable because neither applies to a
    REDEMPTION row (the money already moved at BUY time; redemption is a
    physical delivery action, not a new payment) - forcing a synthetic value
    there would be exactly the kind of not-meaningful data this model design
    avoids. `awb_number`/`product_type`/`metal_type`/`quantity` are nullable
    because they only apply to REDEMPTION rows. `related_transaction_id`
    links a REDEMPTION row back to the BUY it redeems - nullable because
    legacy/backfilled rows may not have one on file."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[TxnType] = mapped_column(String(32))
    product: Mapped[str] = mapped_column(String(64))
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    failure_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    awb_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metal_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    related_transaction_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("transactions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="transactions")


class SupportArticle(Base):
    __tablename__ = "support_articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(512))
    answer: Mapped[str] = mapped_column(String(4096))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    total_cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    models_used: Mapped[str | None] = mapped_column(String(256), nullable=True)
    message_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String(4096))
    response_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    response_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
