from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.transactions import TransactionDetailOut, TransactionOut


class ChatResponseType(str, Enum):
    TEXT_ANSWER = "TEXT_ANSWER"
    TRANSACTION_SELECTION = "TRANSACTION_SELECTION"
    TRANSACTION_EXPLANATION = "TRANSACTION_EXPLANATION"
    TRANSACTION_SUMMARY = "TRANSACTION_SUMMARY"
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
