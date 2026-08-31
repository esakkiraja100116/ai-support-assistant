import logging
import queue
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db import SessionLocal, get_db
from app.models import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import conversation_service
from app.services.orchestrator import chat_turn, chat_turn_stream
from app.services.sse import STREAM_DELTA_DELAY_SECONDS, sse_event
from app.services.turn_metrics import TurnMetrics, turn_scope

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


@router.post("/stream")
def chat_stream(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    # Starlette drives a plain sync generator passed to StreamingResponse by
    # dispatching each next() call to a worker-threadpool, with no guarantee
    # two calls land on the same OS thread. SQLAlchemy Sessions (and,
    # separately, contextvars - see StreamedChatTurn's docstring) aren't safe
    # to use that way - even a single clean hand-off of the FastAPI-injected
    # `db` between two threads was enough to break persistence and, in one
    # variant, hang the request entirely. So this endpoint doesn't use the
    # get_db() dependency at all: the worker thread opens its own SessionLocal(),
    # uses it exclusively for its entire lifetime, and closes it itself -
    # no session ever crosses a thread boundary.
    chunks: queue.Queue = queue.Queue()
    ready: queue.Queue = queue.Queue(maxsize=1)
    done = object()

    def worker():
        db = SessionLocal()
        try:
            try:
                conversation, title_metrics = conversation_service.get_or_create_conversation(
                    db, current_user, payload.conversation_id, payload.message
                )
            except PermissionError:
                ready.put(False)
                return

            ready.put(True)
            logger.info("chat_turn_stream conversation_id=%s user_id=%s", conversation.id, current_user.id)

            db_history = conversation_service.load_history(db, conversation)
            effective_history = db_history if db_history else payload.history
            conversation_service.add_user_message(db, conversation, payload.message)

            try:
                turn = chat_turn_stream(db, current_user, payload.message, effective_history)
                # Normally exactly one ChatResponse is ever produced for a turn,
                # persisted below once the generator is exhausted. For the one
                # split case (see StreamedChatTurn's split_orders_listing), the
                # generator also yields a completed ChatResponse mid-stream for
                # every message except the last - persisted and emitted as its
                # own "message" event immediately, rather than being merged into
                # one bubble. `metrics_cursor` slices turn.metrics.calls (a
                # single list accumulated across the whole turn) so each
                # persisted message gets only the calls made since the previous
                # one, instead of every earlier message's cost being double
                # counted into every later one.
                metrics_cursor = 0
                for item in turn:
                    if isinstance(item, ChatResponse):
                        segment = TurnMetrics(calls=turn.metrics.calls[metrics_cursor:])
                        metrics_cursor = len(turn.metrics.calls)
                        conversation_service.add_assistant_message(db, conversation, item, segment, title_metrics)
                        db.commit()
                        title_metrics = None
                        chunks.put(sse_event("message", item.model_dump(mode="json")))
                    else:
                        chunks.put(sse_event("delta", {"text": item}))
                        time.sleep(STREAM_DELTA_DELAY_SECONDS)
                response = turn.response or ChatResponse.error("llm_unavailable", "No response was generated.")
                final_segment = TurnMetrics(calls=turn.metrics.calls[metrics_cursor:])
                conversation_service.add_assistant_message(db, conversation, response, final_segment, title_metrics)
                db.commit()
                chunks.put(sse_event("done", response.model_dump(mode="json")))
            except Exception:
                logger.exception("Streaming chat turn failed")
                error_response = ChatResponse.error("llm_unavailable", "The assistant is temporarily unavailable.")
                chunks.put(sse_event("done", error_response.model_dump(mode="json")))
        finally:
            chunks.put(done)
            db.close()

    threading.Thread(target=worker, daemon=True).start()

    if not ready.get():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    def event_source():
        while True:
            chunk = chunks.get()
            if chunk is done:
                break
            yield chunk

    return StreamingResponse(event_source(), media_type="text/event-stream")
