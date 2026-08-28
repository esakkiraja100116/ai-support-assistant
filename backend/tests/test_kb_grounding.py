from app.models import SupportArticle
from app.services import kb_service, orchestrator


class _FakeToolCall:
    def __init__(self, arguments: str):
        class _Function:
            name = "search_knowledge_base"

        self.function = _Function()
        self.function.arguments = arguments


def _make_article(db_session, question, answer, embedding):
    article = SupportArticle(question=question, answer=answer, category="test", tags=["test"], embedding=embedding)
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    return article


def test_kb_search_below_threshold_is_not_grounded(db_session, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    orthogonal_query_embedding = [0.0, 1.0] + [0.0] * 1534
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: orthogonal_query_embedding)

    result = kb_service.search_knowledge_base(db_session, "something unrelated")

    assert result.grounded is False


def test_kb_search_above_threshold_is_grounded(db_session, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    article = _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: seeded_embedding)

    result = kb_service.search_knowledge_base(db_session, "How do I buy gold?")

    assert result.grounded is True
    assert result.articles[0].id == article.id


def test_orchestrator_skips_second_llm_call_when_not_grounded(db_session, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    orthogonal_query_embedding = [0.0, 1.0] + [0.0] * 1534
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: orthogonal_query_embedding)

    def _unexpected_call(*args, **kwargs):
        raise AssertionError("Second LLM call must not happen when KB search is not grounded")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", _unexpected_call)

    tool_call = _FakeToolCall('{"query": "something unrelated"}')
    result = orchestrator._handle_knowledge_base(db_session, tool_call, "something unrelated")

    assert result.type.value == "TEXT_ANSWER"
    assert result.data["grounded"] is False
