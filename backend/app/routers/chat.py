import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.orchestrator import chat_turn

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    logger.info("chat_turn conversation_id=%s user_id=%s", payload.conversation_id, current_user.id)
    return chat_turn(db, current_user, payload.message, payload.history, payload.conversation_id)
