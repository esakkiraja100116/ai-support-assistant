import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.redemptions import RedemptionOrderOut


class AdminUserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    transaction_count: int
    redemption_order_count: int
    conversation_count: int


class AdminTransactionOut(BaseModel):
    # A standalone model (not extending TransactionDetailOut) because this
    # view spans every type including REDEMPTION, whose amount/payment_method
    # don't apply and whose awb/product_type/metal_type/quantity fields
    # TransactionDetailOut doesn't have at all.
    id: str
    type: str
    product: str
    amount: float | None = None
    status: str
    failure_reason: str | None = None
    payment_method: str | None = None
    awb_number: str | None = None
    product_type: str | None = None
    metal_type: str | None = None
    quantity: float | None = None
    created_at: datetime
    updated_at: datetime
    user_id: uuid.UUID
    username: str
    display_name: str


class AdminRedemptionOrderOut(RedemptionOrderOut):
    user_id: uuid.UUID
    username: str
    display_name: str


class FaqArticleCreate(BaseModel):
    question: str
    answer: str
    category: str | None = None
    tags: list[str] | None = None


class AdminFaqArticleOut(BaseModel):
    id: int
    question: str
    answer: str
    category: str | None = None
    tags: list[str] | None = None

    model_config = {"from_attributes": True}


class CostByModel(BaseModel):
    model: str
    cost_usd: float
    calls: int


class CostByCategory(BaseModel):
    category: str
    cost_usd: float
    turns: int


class TopConversation(BaseModel):
    conversation_id: uuid.UUID
    title: str
    username: str
    cost_usd: float


class AdminCostSummary(BaseModel):
    total_cost_usd: float
    by_model: list[CostByModel]
    by_category: list[CostByCategory]
    top_conversations: list[TopConversation]
