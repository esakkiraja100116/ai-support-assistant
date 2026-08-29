"""Owns all reads/writes of `Conversation`/`Message` rows.

The backend is the sole owner of conversation state: every turn (the user's
message and the assistant's response) is appended here, synchronously, before
the HTTP response is returned. Nothing about "what was said so far" is ever
reconstructed from anything the client sends - `routers/chat.py` only falls
back to client-supplied history for the pre-existing eval scripts/tests that
call `/chat` without ever creating persisted conversation state.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Conversation, Message, User
from app.schemas.chat import ChatMessage, ChatResponse
from app.services import llm_client, prompts
from app.services.turn_metrics import TurnMetrics, turn_scope

logger = logging.getLogger(__name__)

HISTORY_MESSAGE_LIMIT = 20
TITLE_MAX_LENGTH = 80


def get_conversation(db: Session, user: User, conversation_id: str) -> Conversation | None:
    """Returns None (never another user's row) if it doesn't exist or doesn't
    belong to `user` - mirrors transaction_service.get_transaction_details so
    callers map that to a 404, not a 403."""
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        return None
    stmt = select(Conversation).where(Conversation.id == cid, Conversation.user_id == user.id)
    return db.scalars(stmt).first()


def generate_title(first_message: str) -> tuple[str, TurnMetrics]:
    """One plain content-generation call (no tools), run in its own metrics
    scope so its cost/model can be folded into the first turn's Message
    (see add_assistant_message) rather than tracked as a separate line item."""
    with turn_scope() as metrics:
        title = first_message.strip()
        try:
            prompt = prompts.render("conversation_title.j2", message=first_message)
            result = llm_client.chat_completion([{"role": "system", "content": prompt}], model=settings.title_model)
            if result.content:
                title = result.content.strip()
        except Exception:
            logger.exception("Chat completion (title generation) failed; using raw message as title")
    title = " ".join(title.split())[:TITLE_MAX_LENGTH]
    return title or "New conversation", metrics


def get_or_create_conversation(
    db: Session, user: User, conversation_id: str | None, first_message: str
) -> tuple[Conversation, TurnMetrics | None]:
    """Returns (conversation, title_metrics). title_metrics is only non-None
    when a brand-new conversation was just created (its cost still needs to be
    folded into turn 1's assistant Message by the caller)."""
    cid: uuid.UUID | None = None
    if conversation_id:
        try:
            cid = uuid.UUID(conversation_id)
        except ValueError:
            cid = None
        if cid is not None:
            existing = db.get(Conversation, cid)
            if existing is not None:
                if existing.user_id != user.id:
                    raise PermissionError("Conversation does not belong to this user")
                return existing, None

    title, title_metrics = generate_title(first_message)
    conversation = Conversation(id=cid or uuid.uuid4(), user_id=user.id, title=title)
    db.add(conversation)
    db.flush()
    return conversation, title_metrics


def load_history(db: Session, conversation: Conversation, limit: int = HISTORY_MESSAGE_LIMIT) -> list[ChatMessage]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(list(db.scalars(stmt))))
    return [ChatMessage(role=row.role, content=row.content) for row in rows]


def add_user_message(db: Session, conversation: Conversation, content: str) -> Message:
    message = Message(conversation_id=conversation.id, role="user", content=content)
    db.add(message)
    conversation.message_count += 1
    db.flush()
    return message


def _merge_models(*model_strings: str | None) -> str | None:
    seen: set[str] = set()
    for value in model_strings:
        if value:
            seen.update(m.strip() for m in value.split(",") if m.strip())
    return ", ".join(sorted(seen)) if seen else None


def add_assistant_message(
    db: Session,
    conversation: Conversation,
    response: ChatResponse,
    metrics: TurnMetrics,
    title_metrics: TurnMetrics | None = None,
) -> Message:
    cost = metrics.cost_usd + (title_metrics.cost_usd if title_metrics else 0.0)
    prompt_tokens = metrics.prompt_tokens + (title_metrics.prompt_tokens if title_metrics else 0)
    completion_tokens = metrics.completion_tokens + (title_metrics.completion_tokens if title_metrics else 0)
    model_used = _merge_models(metrics.model_used, title_metrics.model_used if title_metrics else None)

    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=response.message,
        response_type=response.type.value,
        response_data=response.data,
        model_used=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
    )
    db.add(message)
    conversation.message_count += 1
    conversation.total_cost_usd = float(conversation.total_cost_usd or 0) + cost
    conversation.models_used = _merge_models(conversation.models_used, model_used)
    db.flush()
    return message
