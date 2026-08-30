import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_admin
from app.db import get_db
from app.models import Conversation, Message, RedemptionOrder, SupportArticle, Transaction, User
from app.schemas.admin import (
    AdminCostSummary,
    AdminFaqArticleOut,
    AdminRedemptionOrderOut,
    AdminTransactionOut,
    AdminUserOut,
    CostByCategory,
    CostByModel,
    FaqArticleCreate,
    TopConversation,
)
from app.schemas.chat import ChatResponseType
from app.schemas.conversations import ConversationDetailOut, ConversationWithUserOut
from app.services import llm_client

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)) -> list[AdminUserOut]:
    txn_counts = dict(db.execute(select(Transaction.user_id, func.count()).group_by(Transaction.user_id)).all())
    redemption_counts = dict(
        db.execute(select(RedemptionOrder.user_id, func.count()).group_by(RedemptionOrder.user_id)).all()
    )
    convo_counts = dict(db.execute(select(Conversation.user_id, func.count()).group_by(Conversation.user_id)).all())
    users = list(db.scalars(select(User).order_by(User.username)))
    return [
        AdminUserOut(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            role=u.role,
            transaction_count=txn_counts.get(u.id, 0),
            redemption_order_count=redemption_counts.get(u.id, 0),
            conversation_count=convo_counts.get(u.id, 0),
        )
        for u in users
    ]


@router.get("/transactions", response_model=list[AdminTransactionOut])
def list_transactions(db: Session = Depends(get_db)) -> list[AdminTransactionOut]:
    # The one intentionally-unscoped query in the app: every other transaction
    # endpoint (routers/transactions.py) filters by current_user.id, but this
    # one is guarded by get_current_admin instead, not by ownership.
    stmt = (
        select(Transaction, User)
        .join(User, Transaction.user_id == User.id)
        .order_by(Transaction.created_at.desc())
    )
    rows = db.execute(stmt).all()
    return [
        AdminTransactionOut(
            id=t.id,
            type=t.type,
            product=t.product,
            amount=float(t.amount),
            status=t.status,
            failure_reason=t.failure_reason,
            payment_method=t.payment_method,
            created_at=t.created_at,
            updated_at=t.updated_at,
            user_id=u.id,
            username=u.username,
            display_name=u.display_name,
        )
        for t, u in rows
    ]


@router.get("/redemptions", response_model=list[AdminRedemptionOrderOut])
def list_redemption_orders(db: Session = Depends(get_db)) -> list[AdminRedemptionOrderOut]:
    # Same intentionally-unscoped-by-ownership pattern as list_transactions -
    # guarded by get_current_admin instead, shows every user's orders, not
    # just the calling admin's own.
    stmt = (
        select(RedemptionOrder, User)
        .join(User, RedemptionOrder.user_id == User.id)
        .order_by(RedemptionOrder.created_at.desc())
    )
    rows = db.execute(stmt).all()
    return [
        AdminRedemptionOrderOut(
            order_ref=str(o.id),
            product_name=o.product_name,
            product_type=o.product_type,
            metal_type=o.metal_type,
            quantity=float(o.quantity_purchased),
            status=o.txn_status,
            created_at=o.created_at,
            user_id=u.id,
            username=u.username,
            display_name=u.display_name,
        )
        for o, u in rows
    ]


@router.get("/conversations", response_model=list[ConversationWithUserOut])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationWithUserOut]:
    stmt = (
        select(Conversation, User)
        .join(User, Conversation.user_id == User.id)
        .order_by(Conversation.updated_at.desc())
    )
    rows = db.execute(stmt).all()
    return [
        ConversationWithUserOut(
            id=c.id,
            title=c.title,
            total_cost_usd=float(c.total_cost_usd or 0),
            models_used=c.models_used,
            message_count=c.message_count,
            created_at=c.created_at,
            updated_at=c.updated_at,
            user_id=u.id,
            username=u.username,
            display_name=u.display_name,
        )
        for c, u in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> Conversation:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    conversation = db.get(Conversation, cid)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.post("/faq", response_model=AdminFaqArticleOut, status_code=status.HTTP_201_CREATED)
def create_faq_article(payload: FaqArticleCreate, db: Session = Depends(get_db)) -> SupportArticle:
    # Embed the question only, matching scripts/seed.py's already-fixed dilution
    # bug: incoming customer queries are phrased as questions, so
    # question-to-question similarity is a much cleaner retrieval signal than
    # diluting the vector with answer text.
    embedding = llm_client.embed(payload.question)
    article = SupportArticle(
        question=payload.question,
        answer=payload.answer,
        category=payload.category,
        tags=payload.tags or ([payload.category] if payload.category else None),
        embedding=embedding,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@router.delete("/faq/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq_article(article_id: int, db: Session = Depends(get_db)) -> None:
    article = db.get(SupportArticle, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    # Deleting the row removes its embedding too, so the knowledge-base search
    # can no longer retrieve it - the assistant simply won't have this article
    # to draw an answer from on the next query.
    db.delete(article)
    db.commit()


_CATEGORY_BUCKETS = {
    ChatResponseType.TRANSACTION_SELECTION.value: "transaction",
    ChatResponseType.TRANSACTION_EXPLANATION.value: "transaction",
    ChatResponseType.TRANSACTION_SUMMARY.value: "transaction",
    ChatResponseType.REDEMPTION_SELECTION.value: "redemption",
    ChatResponseType.REDEMPTION_TRACKING.value: "redemption",
    ChatResponseType.TEXT_ANSWER.value: "general",
    ChatResponseType.ESCALATE.value: "escalation",
    ChatResponseType.ERROR.value: "error",
}


@router.get("/costs", response_model=AdminCostSummary)
def get_costs(db: Session = Depends(get_db)) -> AdminCostSummary:
    messages = list(db.scalars(select(Message).where(Message.role == "assistant")))

    total_cost = sum(float(m.cost_usd or 0) for m in messages)

    by_model: dict[str, dict[str, float]] = defaultdict(lambda: {"cost_usd": 0.0, "calls": 0})
    by_category: dict[str, dict[str, float]] = defaultdict(lambda: {"cost_usd": 0.0, "turns": 0})
    for m in messages:
        model_key = m.model_used or "unknown"
        by_model[model_key]["cost_usd"] += float(m.cost_usd or 0)
        by_model[model_key]["calls"] += 1

        category = _CATEGORY_BUCKETS.get(m.response_type or "", "other")
        by_category[category]["cost_usd"] += float(m.cost_usd or 0)
        by_category[category]["turns"] += 1

    top_stmt = (
        select(Conversation, User)
        .join(User, Conversation.user_id == User.id)
        .order_by(Conversation.total_cost_usd.desc())
        .limit(10)
    )
    top_rows = db.execute(top_stmt).all()

    return AdminCostSummary(
        total_cost_usd=total_cost,
        by_model=[
            CostByModel(model=k, cost_usd=v["cost_usd"], calls=int(v["calls"]))
            for k, v in sorted(by_model.items())
        ],
        by_category=[
            CostByCategory(category=k, cost_usd=v["cost_usd"], turns=int(v["turns"]))
            for k, v in sorted(by_category.items())
        ],
        top_conversations=[
            TopConversation(
                conversation_id=c.id, title=c.title, username=u.username, cost_usd=float(c.total_cost_usd or 0)
            )
            for c, u in top_rows
        ],
    )
