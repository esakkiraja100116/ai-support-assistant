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
from app.schemas.transactions import ExplainRequest, TransactionDetailOut, TransactionOut
from app.services import conversation_service, transaction_service
from app.services.orchestrator import explain_transaction, explain_transaction_stream, fallback_explanation
from app.services.sse import STREAM_DELTA_DELAY_SECONDS, sse_event
from app.services.turn_metrics import TurnMetrics, turn_scope

router = APIRouter(prefix="/transactions", tags=["transactions"])
logger = logging.getLogger(__name__)


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
    payload: ExplainRequest = ExplainRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    transaction = transaction_service.get_transaction_details(db, current_user, transaction_id)
    if transaction is None:
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
            if transaction is None:
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
