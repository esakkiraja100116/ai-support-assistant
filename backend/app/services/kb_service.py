from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SupportArticle
from app.services import llm_client


@dataclass
class KBSearchResult:
    articles: list[SupportArticle]
    best_similarity: float
    grounded: bool


def search_knowledge_base(db: Session, query: str, top_k: int = 3) -> KBSearchResult:
    query_embedding = llm_client.embed(query)

    distance_col = SupportArticle.embedding.cosine_distance(query_embedding)
    stmt = select(SupportArticle, distance_col.label("distance")).order_by(distance_col).limit(top_k)
    rows = db.execute(stmt).all()

    if not rows:
        return KBSearchResult(articles=[], best_similarity=0.0, grounded=False)

    articles = [row[0] for row in rows]
    best_similarity = 1 - float(rows[0][1])
    grounded = best_similarity >= settings.kb_similarity_threshold
    return KBSearchResult(articles=articles, best_similarity=best_similarity, grounded=grounded)
