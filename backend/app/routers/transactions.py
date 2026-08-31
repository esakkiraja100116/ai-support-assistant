import logging
import queue
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db import SessionLocal, get_db
from app.models import TxnType, User, is_trackable_redemption
from app.schemas.chat import ChatResponse
from app.schemas.redemptions import RedemptionOrderOut, TrackRequest
from app.schemas.transactions import ExplainRequest, TransactionDetailOut, TransactionOut
from app.services import conversation_service, rate_limit, transaction_service
from app.services.orchestrator import (
    explain_transaction,
    explain_transaction_stream,
    fallback_explanation,
    redemption_status_changed_response,
    track_redemption_order,
    track_redemption_order_stream,
)
from app.services.sse import STREAM_DELTA_DELAY_SECONDS, sse_event
from app.services.turn_metrics import TurnMetrics, turn_scope

router = APIRouter(prefix="/transactions", tags=["transactions"])
redemptions_router = APIRouter(prefix="/redemptions", tags=["redemptions"])
logger = logging.getLogger(__name__)


@router.get("/recent", response_model=list[TransactionOut])
def recent_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionOut]:
    transactions, _ = transaction_service.get_transactions(db, current_user)
    return transactions


@router.get("/{transaction_id}", response_model=TransactionDetailOut)
def transaction_detail(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TransactionDetailOut:
    transaction = transaction_service.get_transaction_details(db, current_user, transaction_id)
    if transaction is None or transaction.type == TxnType.REDEMPTION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


@router.post("/{transaction_id}/explain", response_model=ChatResponse)
def explain(
    transaction_id: str,
    payload: ExplainRequest = ExplainRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    transaction = transaction_service.get_transaction_details(db, current_user, transaction_id)
    if transaction is None or transaction.type == TxnType.REDEMPTION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # Clicking a transaction card is persisted as a real turn in the
    # conversation (when a conversation_id is given) so a later follow-up
    # question ("why is it pending?") has this transaction in its history,
    # exactly as if the customer had typed the question themselves.
    user_message_text = f"What can you tell me about transaction {transaction.id}?"

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
        message = explain_transaction(transaction, current_user.display_name, user_message_text)
    response = ChatResponse.transaction_explanation(message, transaction)

    if conversation is not None:
        conversation_service.add_assistant_message(db, conversation, response, metrics, title_metrics)
        db.commit()

    return response


@router.post("/{transaction_id}/explain/stream")
def explain_stream(
    transaction_id: str,
    payload: ExplainRequest = ExplainRequest(),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    # Same worker-owns-its-own-session pattern as routers/chat.py's
    # /chat/stream - see that endpoint's comment for why the get_db()
    # dependency isn't used here at all.
    chunks: queue.Queue = queue.Queue()
    ready: queue.Queue = queue.Queue(maxsize=1)
    done = object()

    def worker():
        db = SessionLocal()
        try:
            transaction = transaction_service.get_transaction_details(db, current_user, transaction_id)
            if transaction is None or transaction.type == TxnType.REDEMPTION:
                ready.put(False)
                return
            ready.put(True)

            user_message_text = f"What can you tell me about transaction {transaction.id}?"
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
                streamed = explain_transaction_stream(transaction, current_user.display_name, user_message_text, metrics=metrics)
                # Each event carries the full text-so-far (streamed.content is
                # already cumulative), not an incremental piece - the frontend
                # renders whatever it receives directly, no client-side concatenation.
                for _ in streamed:
                    chunks.put(sse_event("delta", {"text": streamed.content}))
                    time.sleep(STREAM_DELTA_DELAY_SECONDS)
                text = streamed.content or fallback_explanation(transaction)
            except Exception:
                logger.exception("Chat completion (transaction explanation stream) failed")
                text = fallback_explanation(transaction)

            response = ChatResponse.transaction_explanation(text, transaction)
            if conversation is not None:
                conversation_service.add_assistant_message(db, conversation, response, metrics, title_metrics)
                db.commit()
            chunks.put(sse_event("done", response.model_dump(mode="json")))
        finally:
            chunks.put(done)
            db.close()

    threading.Thread(target=worker, daemon=True).start()

    if not ready.get():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    def event_source():
        while True:
            chunk = chunks.get()
            if chunk is done:
                break
            yield chunk

    return StreamingResponse(event_source(), media_type="text/event-stream")


@redemptions_router.get("/ongoing", response_model=list[RedemptionOrderOut])
def ongoing_redemptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RedemptionOrderOut]:
    _, redemptions = transaction_service.get_transactions(db, current_user, type=TxnType.REDEMPTION.value)
    return [transaction_service.to_redemption_out(r) for r in redemptions]


@redemptions_router.get("/{order_ref}", response_model=RedemptionOrderOut)
def redemption_detail(
    order_ref: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RedemptionOrderOut:
    order = transaction_service.get_ongoing_transaction_by_ref(db, current_user, order_ref)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redemption order not found")
    return transaction_service.to_redemption_out(transaction_service.TransactionRecord.from_model(order))


@redemptions_router.post("/{order_ref}/track", response_model=ChatResponse)
def track(
    order_ref: str,
    payload: TrackRequest = TrackRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    if not rate_limit.is_allowed(
        str(current_user.id),
        "redemption_track",
        settings.redemption_track_rate_limit,
        settings.redemption_track_rate_limit_window_seconds,
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many tracking requests - please try again shortly.")

    # Fetched without the trackable-status filter first so a status change
    # since this order was shown as ongoing (e.g. delivered in the meantime)
    # can be reported accurately, rather than a generic 404 that would
    # wrongly imply the order never existed at all.
    order = transaction_service.get_redemption_order_by_ref(db, current_user, order_ref)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redemption order not found")

    # Clicking an order card is persisted as a real turn in the conversation
    # (when a conversation_id is given), exactly like a transaction card
    # click, so a later follow-up question has this order in its history.
    user_message_text = f"Where is my {order.product} order?"

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

    if not is_trackable_redemption(order.status):
        transaction_service.invalidate_ongoing_redemptions_cache(current_user.id)
        response = redemption_status_changed_response(order)
        metrics = TurnMetrics()
    else:
        with turn_scope() as metrics:
            response = track_redemption_order(
                transaction_service.TransactionRecord.from_model(order), current_user.display_name, user_message_text
            )

    if conversation is not None:
        conversation_service.add_assistant_message(db, conversation, response, metrics, title_metrics)
        db.commit()

    return response


@redemptions_router.post("/{order_ref}/track/stream")
def track_stream(
    order_ref: str,
    payload: TrackRequest = TrackRequest(),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    if not rate_limit.is_allowed(
        str(current_user.id),
        "redemption_track",
        settings.redemption_track_rate_limit,
        settings.redemption_track_rate_limit_window_seconds,
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many tracking requests - please try again shortly.")

    # Same worker-owns-its-own-session pattern as /explain/stream above.
    chunks: queue.Queue = queue.Queue()
    ready: queue.Queue = queue.Queue(maxsize=1)
    done = object()

    def worker():
        db = SessionLocal()
        try:
            # Fetched without the trackable-status filter first, same
            # reasoning as the non-streaming /track endpoint above.
            order = transaction_service.get_redemption_order_by_ref(db, current_user, order_ref)
            if order is None:
                ready.put(False)
                return
            ready.put(True)
            order_record = transaction_service.TransactionRecord.from_model(order)

            user_message_text = f"Where is my {order.product} order?"
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

            if not is_trackable_redemption(order.status):
                transaction_service.invalidate_ongoing_redemptions_cache(current_user.id)
                response = redemption_status_changed_response(order)
                metrics = TurnMetrics()
                chunks.put(sse_event("delta", {"text": response.message}))
            else:
                metrics = TurnMetrics()
                try:
                    streamed = track_redemption_order_stream(
                        order_record, current_user.display_name, user_message_text, metrics=metrics
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
