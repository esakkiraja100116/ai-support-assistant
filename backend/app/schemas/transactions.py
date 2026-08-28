from datetime import datetime

from pydantic import BaseModel


class TransactionOut(BaseModel):
    id: str
    type: str
    product: str
    amount: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionDetailOut(TransactionOut):
    failure_reason: str | None = None
    payment_method: str
    updated_at: datetime
