from app.models import SupportArticle
from app.services import kb_service, orchestrator


class _FakeFunction:
    def __init__(self, name: str, arguments: str = "{}"):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name: str, arguments: str = "{}"):
        self.function = _FakeFunction(name, arguments)


class _FakeMessage:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls
        self.content = content


def _make_article(db_session, question, answer, embedding):
    article = SupportArticle(question=question, answer=answer, category="test", tags=["test"], embedding=embedding)
    db_session.add(article)
    db_session.commit()
    db_session.refresh(article)
    return article


def test_kb_search_returns_nothing_below_min_similarity(db_session, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    orthogonal_query_embedding = [0.0, 1.0] + [0.0] * 1534
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: orthogonal_query_embedding)

    result = kb_service.search_knowledge_base(db_session, "something unrelated")

    assert result.articles == []


def test_kb_search_returns_matching_article(db_session, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    article = _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: seeded_embedding)

    result = kb_service.search_knowledge_base(db_session, "How do I buy gold?")

    assert result.articles[0].id == article.id


def test_orchestrator_skips_llm_call_when_no_candidates_at_all(db_session, make_user, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    orthogonal_query_embedding = [0.0, 1.0] + [0.0] * 1534
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: orthogonal_query_embedding)

    def _unexpected_call(*args, **kwargs):
        raise AssertionError("LLM must not be called when there are no retrieval candidates at all")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", _unexpected_call)

    alice = make_user("alice", "Alice")
    result = orchestrator._handle_knowledge_base(db_session, alice, "something unrelated")

    assert result.type.value == "TEXT_ANSWER"
    assert result.data["grounded"] is False


def test_orchestrator_picks_correct_article_even_when_not_top_ranked(db_session, make_user, monkeypatch):
    """Regression test for a real bug: "do I need to pay extra if I purchase gold?" scored
    higher against an unrelated article than the one that actually answers it, because
    "purchase gold" dominated the embedding over the weaker "pay extra" signal. The fix is
    retrieving a wider candidate pool and letting the model pick the real answer out of it -
    this test simulates exactly that: the correct article is NOT the top similarity match,
    but the (mocked) model still finds it in the provided candidate list."""
    seeded_embedding_a = [1.0] + [0.0] * 1535
    buy_gold = _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding_a)

    seeded_embedding_b = [0.9] + [0.436] + [0.0] * 1534  # close, but not the top match
    fees = _make_article(db_session, "What fees do you charge?", "We charge a small spread.", seeded_embedding_b)

    # Query embedding closest to buy_gold (top match), fees is 2nd - but fees is the
    # article that actually answers the question.
    query_embedding = [1.0] + [0.05] + [0.0] * 1534
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: query_embedding)

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        return _FakeMessage(
            tool_calls=[
                _FakeToolCall(
                    "answer_from_kb",
                    f'{{"answer": "We charge a small spread.", "source_article_ids": [{fees.id}]}}',
                )
            ]
        )

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    alice = make_user("alice", "Alice")
    result = orchestrator._handle_knowledge_base(db_session, alice, "do I need to pay extra if I purchase gold?")

    assert result.data["grounded"] is True
    assert result.data["sources"] == [fees.id]
    assert buy_gold.id not in result.data["sources"]


def test_orchestrator_declines_when_candidates_exist_but_none_relevant(db_session, make_user, monkeypatch):
    seeded_embedding = [1.0] + [0.0] * 1535
    _make_article(db_session, "How do I buy gold?", "Go to Buy...", seeded_embedding)

    # Similar enough to pass the loose pre-filter, but not actually relevant.
    query_embedding = [0.6, 0.8] + [0.0] * 1534
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: query_embedding)

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *a, **kw: _FakeMessage(tool_calls=[_FakeToolCall("insufficient_kb_info")]),
    )

    alice = make_user("alice", "Alice")
    result = orchestrator._handle_knowledge_base(db_session, alice, "something tangential")

    assert result.data["grounded"] is False
