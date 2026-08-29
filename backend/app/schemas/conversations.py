import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    response_type: str | None = None
    response_data: dict[str, Any] | None = None
    model_used: str | None = None
    cost_usd: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    total_cost_usd: float
    models_used: str | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class ConversationWithUserOut(ConversationOut):
    user_id: uuid.UUID
    username: str
    display_name: str
