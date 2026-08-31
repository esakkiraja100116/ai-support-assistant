from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, model_validator

from app.schemas.redemptions import RedemptionOrderOut, RedemptionTrackingOut
from app.schemas.transactions import TransactionDetailOut, TransactionOut


class ChatResponseType(str, Enum):
    TEXT_ANSWER = "TEXT_ANSWER"
    TRANSACTION_SELECTION = "TRANSACTION_SELECTION"
    TRANSACTION_EXPLANATION = "TRANSACTION_EXPLANATION"
    TRANSACTION_SUMMARY = "TRANSACTION_SUMMARY"
    REDEMPTION_SELECTION = "REDEMPTION_SELECTION"
    REDEMPTION_TRACKING = "REDEMPTION_TRACKING"
    REDEMPTION_SUMMARY = "REDEMPTION_SUMMARY"
    ORDERS_OVERVIEW = "ORDERS_OVERVIEW"
    ESCALATE = "ESCALATE"
    ERROR = "ERROR"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    conversation_id: str | None = None


class TextAnswerData(BaseModel):
    grounded: bool
    sources: list[int] = []


class TransactionSelectionData(BaseModel):
    transactions: list[TransactionOut]


class TransactionExplanationData(BaseModel):
    transaction: TransactionDetailOut


class TransactionSummaryData(BaseModel):
    transactions: list[TransactionDetailOut]


class RedemptionSelectionData(BaseModel):
    orders: list[RedemptionOrderOut]


class RedemptionTrackingData(BaseModel):
    tracking: RedemptionTrackingOut


class RedemptionSummaryData(BaseModel):
    orders: list[RedemptionOrderOut]


class OrderCardOut(BaseModel):
    kind: Literal["transaction", "redemption"]
    transaction: TransactionOut | None = None
    redemption: RedemptionOrderOut | None = None

    @model_validator(mode="after")
    def _one_side_populated(self) -> "OrderCardOut":
        if self.kind == "transaction" and self.transaction is None:
            raise ValueError("transaction must be set when kind='transaction'")
        if self.kind == "redemption" and self.redemption is None:
            raise ValueError("redemption must be set when kind='redemption'")
        return self


class OrdersOverviewData(BaseModel):
    orders: list[OrderCardOut]


class EscalateData(BaseModel):
    contact_email: str


class ErrorData(BaseModel):
    code: str
    detail: str


class ChatResponse(BaseModel):
    type: ChatResponseType
    message: str
    data: dict[str, Any] | None = None

    @classmethod
    def text_answer(cls, message: str, grounded: bool, sources: list[int] | None = None) -> "ChatResponse":
        return cls(
            type=ChatResponseType.TEXT_ANSWER,
            message=message,
            data=TextAnswerData(grounded=grounded, sources=sources or []).model_dump(),
        )

    @classmethod
    def transaction_selection(cls, message: str, transactions: list[TransactionOut]) -> "ChatResponse":
        return cls(
            type=ChatResponseType.TRANSACTION_SELECTION,
            message=message,
            data=TransactionSelectionData(transactions=transactions).model_dump(mode="json"),
        )

    @classmethod
    def transaction_explanation(cls, message: str, transaction: TransactionDetailOut) -> "ChatResponse":
        return cls(
            type=ChatResponseType.TRANSACTION_EXPLANATION,
            message=message,
            data=TransactionExplanationData(transaction=transaction).model_dump(mode="json"),
        )

    @classmethod
    def transaction_summary(cls, message: str, transactions: list[TransactionDetailOut]) -> "ChatResponse":
        return cls(
            type=ChatResponseType.TRANSACTION_SUMMARY,
            message=message,
            data=TransactionSummaryData(transactions=transactions).model_dump(mode="json"),
        )

    @classmethod
    def redemption_selection(cls, message: str, orders: list[RedemptionOrderOut]) -> "ChatResponse":
        return cls(
            type=ChatResponseType.REDEMPTION_SELECTION,
            message=message,
            data=RedemptionSelectionData(orders=orders).model_dump(mode="json"),
        )

    @classmethod
    def redemption_tracking(cls, message: str, tracking: RedemptionTrackingOut) -> "ChatResponse":
        return cls(
            type=ChatResponseType.REDEMPTION_TRACKING,
            message=message,
            data=RedemptionTrackingData(tracking=tracking).model_dump(mode="json"),
        )

    @classmethod
    def redemption_summary(cls, message: str, orders: list[RedemptionOrderOut]) -> "ChatResponse":
        return cls(
            type=ChatResponseType.REDEMPTION_SUMMARY,
            message=message,
            data=RedemptionSummaryData(orders=orders).model_dump(mode="json"),
        )

    @classmethod
    def orders_overview(cls, message: str, orders: list[OrderCardOut]) -> "ChatResponse":
        return cls(
            type=ChatResponseType.ORDERS_OVERVIEW,
            message=message,
            data=OrdersOverviewData(orders=orders).model_dump(mode="json"),
        )

    @classmethod
    def escalate(cls, message: str, contact_email: str) -> "ChatResponse":
        return cls(
            type=ChatResponseType.ESCALATE,
            message=message,
            data=EscalateData(contact_email=contact_email).model_dump(),
        )

    @classmethod
    def error(cls, code: str, detail: str) -> "ChatResponse":
        return cls(
            type=ChatResponseType.ERROR,
            message=detail,
            data=ErrorData(code=code, detail=detail).model_dump(),
        )
