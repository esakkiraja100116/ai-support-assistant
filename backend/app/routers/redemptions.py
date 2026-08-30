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
from app.schemas.chat import ChatResponse
from app.schemas.redemptions import RedemptionOrderOut, TrackRequest
from app.services import conversation_service, redemption_service
from app.services.orchestrator import track_redemption_order, track_redemption_order_stream
from app.services.sse import STREAM_DELTA_DELAY_SECONDS, sse_event
from app.services.turn_metrics import TurnMetrics, turn_scope

router = APIRouter(prefix="/redemptions", tags=["redemptions"])
logger = logging.getLogger(__name__)


@router.get("/ongoing", response_model=list[RedemptionOrderOut])
def ongoing_redemptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RedemptionOrderOut]:
    orders = redemption_service.get_ongoing_redemptions(db, current_user)
    return [redemption_service.to_order_out(o) for o in orders]


@router.get("/{order_ref}", response_model=RedemptionOrderOut)
def redemption_detail(
    order_ref: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedemptionOrderOut:
    order = redemption_service.get_ongoing_redemption_by_ref(db, current_user, order_ref)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redemption order not found")
    return redemption_service.to_order_out(order)


@router.post("/{order_ref}/track", response_model=ChatResponse)
def track(
    order_ref: str,
    payload: TrackRequest = TrackRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    order = redemption_service.get_ongoing_redemption_by_ref(db, current_user, order_ref)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redemption order not found")

    # Clicking an order card is persisted as a real turn in the conversation
    # (when a conversation_id is given), exactly like a transaction card
    # click, so a later follow-up question has this order in its history.
    user_message_text = f"Where is my {order.product_name} order?"

    conversation = None
    title_metrics = None
    if payload.conversation_id:
        try:
            conversation, title_metrics = conversation_service.get_or_create_conversation(
                db, current_user, payload.conversation_id, user_message_text
            )
        except PermissionError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        conversation_service.add_user_message(db, conversation, user_message_text)

    with turn_scope() as metrics:
        response = track_redemption_order(order, current_user.display_name, user_message_text)

    if conversation is not None:
        conversation_service.add_assistant_message(db, conversation, response, metrics, title_metrics)
        db.commit()

    return response


@router.post("/{order_ref}/track/stream")
def track_stream(
    order_ref: str,
    payload: TrackRequest = TrackRequest(),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    # Same worker-owns-its-own-session pattern as routers/transactions.py's
    # /explain/stream - see that endpoint's comment for why the get_db()
    # dependency isn't used here at all.
    chunks: queue.Queue = queue.Queue()
    ready: queue.Queue = queue.Queue(maxsize=1)
    done = object()

    def worker():
        db = SessionLocal()
        try:
            order = redemption_service.get_ongoing_redemption_by_ref(db, current_user, order_ref)
            if order is None:
                ready.put(False)
                return
            ready.put(True)

            user_message_text = f"Where is my {order.product_name} order?"
            conversation = None
            title_metrics = None
            if payload.conversation_id:
                try:
                    conversation, title_metrics = conversation_service.get_or_create_conversation(
                        db, current_user, payload.conversation_id, user_message_text
                    )
                except PermissionError:
                    conversation = None
                else:
                    conversation_service.add_user_message(db, conversation, user_message_text)

            metrics = TurnMetrics()
            try:
                streamed = track_redemption_order_stream(
                    order, current_user.display_name, user_message_text, metrics=metrics
                )
                for text_so_far in streamed:
                    chunks.put(sse_event("delta", {"text": text_so_far}))
                    time.sleep(STREAM_DELTA_DELAY_SECONDS)
                text = streamed.text
                tracking = streamed.tracking
            except Exception:
                logger.exception("Chat completion (redemption tracking stream) failed")
                # streamed.tracking may be unset if the failure happened before
                # _build_redemption_tracking even ran - fall back to a plain
                # text answer in that unlikely case rather than crashing.
                text = "Sorry, tracking is temporarily unavailable right now. Please try again shortly."
                tracking = None

            response = (
                ChatResponse.redemption_tracking(text, tracking)
                if tracking is not None
                else ChatResponse.text_answer(text, grounded=True)
            )
            if conversation is not None:
                conversation_service.add_assistant_message(db, conversation, response, metrics, title_metrics)
                db.commit()
            chunks.put(sse_event("done", response.model_dump(mode="json")))
        finally:
            chunks.put(done)
            db.close()

    threading.Thread(target=worker, daemon=True).start()

    if not ready.get():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redemption order not found")

    def event_source():
        while True:
            chunk = chunks.get()
            if chunk is done:
                break
            yield chunk

    return StreamingResponse(event_source(), media_type="text/event-stream")
