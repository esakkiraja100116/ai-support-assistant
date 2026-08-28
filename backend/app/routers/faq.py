from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SupportArticle
from app.schemas.faq import FaqArticleOut

router = APIRouter(prefix="/faq", tags=["faq"])


@router.get("", response_model=list[FaqArticleOut])
def list_faq_articles(db: Session = Depends(get_db)) -> list[SupportArticle]:
    """Public: the approved knowledge base is not customer-specific or sensitive,
    unlike transactions, so this intentionally doesn't require authentication."""
    stmt = select(SupportArticle).order_by(SupportArticle.category, SupportArticle.id)
    return list(db.scalars(stmt))
