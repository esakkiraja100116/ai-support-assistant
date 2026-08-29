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


def search_knowledge_base(db: Session, query: str, top_k: int = 8) -> KBSearchResult:
    """Retrieves a candidate pool of articles for the caller's LLM call to judge relevance
    over, rather than deciding "grounded or not" here from a single cosine number.

    A single-vector similarity score can rank the actually-relevant article outside the
    top few results for a compound question (e.g. "do I need to pay extra if I purchase
    gold?" scores higher against "How do I buy gold?" than "What fees do you charge?",
    since "purchase gold" dominates the embedding over the weaker "pay extra" signal). A
    wider candidate pool plus letting the model read the actual content is far more robust
    to this than tightening one number ever could be - the model can tell "fees" answers
    "pay extra" even when the embedding alone under-ranks it.

    `kb_min_similarity` is a loose pre-filter only, meant to drop true noise (an unrelated
    question shouldn't retrieve anything at all) - not to decide relevance, which is left
    entirely to the model.
    """
    query_embedding = llm_client.embed(query)

    distance_col = SupportArticle.embedding.cosine_distance(query_embedding)
    stmt = select(SupportArticle, distance_col.label("distance")).order_by(distance_col).limit(top_k)
    rows = db.execute(stmt).all()

    matches = [(article, 1 - float(distance)) for article, distance in rows]
    matches = [(article, sim) for article, sim in matches if sim >= settings.kb_min_similarity]

    if not matches:
        return KBSearchResult(articles=[], best_similarity=0.0)

    return KBSearchResult(articles=[a for a, _ in matches], best_similarity=matches[0][1])
