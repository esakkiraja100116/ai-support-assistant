from datetime import datetime

from pydantic import BaseModel


class RedemptionOrderOut(BaseModel):
    # `order_ref` is `RedemptionOrder.id` (a UUID) exposed as a plain string.
    # This is NOT the app's authorization boundary - ownership is enforced by
    # the `.where(user_id == ...)` clause baked into every query that resolves
    # a ref, exactly like `Transaction.id` already being exposed today. A
    # non-guessable UUID is a reasonable identifier to hand to the model/UI,
    # not a substitute for server-side ownership checks.
    order_ref: str
    product_name: str
    product_type: str
    metal_type: str
    quantity: float
    status: str
    created_at: datetime


class TrackingEvent(BaseModel):
    type: str
    remarks: str
    area: str
    event_time: datetime


class RedemptionTrackingOut(BaseModel):
    order_ref: str
    product_name: str
    quantity: float
    status: str
    awb_available: bool
    current_location: str | None = None
    latest_event: TrackingEvent | None = None
    history: list[TrackingEvent] = []
    stale: bool = False


class TrackRequest(BaseModel):
    conversation_id: str | None = None
