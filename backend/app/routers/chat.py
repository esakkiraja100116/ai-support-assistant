import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import get_db
from app.models import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import conversation_service
from app.services.orchestrator import chat_turn
from app.services.turn_metrics import turn_scope

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        conversation, title_metrics = conversation_service.get_or_create_conversation(
            db, current_user, payload.conversation_id, payload.message
        )
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    logger.info("chat_turn conversation_id=%s user_id=%s", conversation.id, current_user.id)

    db_history = conversation_service.load_history(db, conversation)
    # Prefer persisted DB history (the real source of truth); fall back to
    # client-supplied history only when the conversation has no persisted
    # turns yet - this is what keeps the eval scripts and existing tests
    # working unmodified, since they never pass a conversation_id and so
    # always hit this fallback.
    effective_history = db_history if db_history else payload.history

    conversation_service.add_user_message(db, conversation, payload.message)
    with turn_scope() as metrics:
        response = chat_turn(db, current_user, payload.message, effective_history, str(conversation.id))
    conversation_service.add_assistant_message(db, conversation, response, metrics, title_metrics)
    db.commit()
    return response
