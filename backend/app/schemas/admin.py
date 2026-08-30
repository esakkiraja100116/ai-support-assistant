import uuid

from pydantic import BaseModel

from app.schemas.redemptions import RedemptionOrderOut
from app.schemas.transactions import TransactionDetailOut


class AdminUserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    transaction_count: int
    redemption_order_count: int
    conversation_count: int


class AdminTransactionOut(TransactionDetailOut):
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
