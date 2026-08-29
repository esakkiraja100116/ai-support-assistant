from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.chat import ChatResponse
from app.schemas.transactions import TransactionDetailOut, TransactionOut
from app.services import transaction_service
from app.services.orchestrator import explain_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("/recent", response_model=list[TransactionOut])
def recent_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionOut]:
    return transaction_service.get_recent_transactions(db, current_user)


@router.get("/{transaction_id}", response_model=TransactionDetailOut)
def transaction_detail(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionDetailOut:
    transaction = transaction_service.get_transaction_details(db, current_user, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


@router.post("/{transaction_id}/explain", response_model=ChatResponse)
def explain(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    transaction = transaction_service.get_transaction_details(db, current_user, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    message = explain_transaction(transaction, current_user.display_name)
    return ChatResponse.transaction_explanation(message, transaction)
