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
    redemption_orders: Mapped[list["RedemptionOrder"]] = relationship(back_populates="user")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[TxnType] = mapped_column(String(32))
    product: Mapped[str] = mapped_column(String(32))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[TxnStatus] = mapped_column(String(16))
    failure_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="transactions")


class RedemptionOrder(Base):
    __tablename__ = "redemption_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    txn_id: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(128))
    product_type: Mapped[str] = mapped_column(String(32))
    metal_type: Mapped[str] = mapped_column(String(32))
    quantity_purchased: Mapped[float] = mapped_column(Numeric(12, 4))
    txn_status: Mapped[RedemptionStatus] = mapped_column(String(32))
    awb_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="redemption_orders")


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
