from app.models import SupportArticle


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


def _tool_names(tools):
    return [t["function"]["name"] for t in (tools or [])]


def test_chat_shows_selection_cards_only_when_ambiguous(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    make_transaction(alice, "txn_a1")
    make_transaction(bob, "txn_b1")

    def fake_chat_completion(messages, tools=None, tool_choice="auto"):
        if "get_recent_transactions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transaction" in _tool_names(tools):
            # The model can't resolve one specific transaction from an explicit list request.
            return _FakeMessage(
                tool_calls=[_FakeToolCall("no_single_match", '{"reason": "list_requested"}')]
            )
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    resp = client.post("/chat", json={"message": "show me my transactions"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TRANSACTION_SELECTION"
    assert body["message"] == "Here are your recent transactions:"
    ids = [t["id"] for t in body["data"]["transactions"]]
    assert ids == ["txn_a1"]


def test_chat_resolves_specific_transaction_without_showing_cards(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_transaction(alice, "txn_old", status="SUCCESS")
    failed_txn = make_transaction(alice, "txn_failed", status="FAILED", failure_reason="Card declined")

    def fake_chat_completion(messages, tools=None, tool_choice="auto"):
        names = _tool_names(tools)
        if "get_recent_transactions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transaction" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_transaction", f'{{"transaction_id": "{failed_txn.id}"}}')]
            )
        return _FakeMessage(content="Your purchase failed because the card was declined.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    resp = client.post("/chat", json={"message": "why did my last purchase fail?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TRANSACTION_EXPLANATION"
    assert body["data"]["transaction"]["id"] == "txn_failed"


def test_chat_falls_back_to_selection_if_resolved_id_not_in_users_list(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    """Even if the model hallucinates or is prompt-injected into naming an id that
    isn't in the authenticated user's own fetched list, we must never look it up -
    we fall back to the safe selection list instead of trusting the model's id."""
    alice = make_user("alice", "Alice")
    make_transaction(alice, "txn_a1")

    def fake_chat_completion(messages, tools=None, tool_choice="auto"):
        names = _tool_names(tools)
        if "get_recent_transactions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transaction" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_transaction", '{"transaction_id": "txn_someone_elses"}')]
            )
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    resp = client.post("/chat", json={"message": "why did it fail?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TRANSACTION_SELECTION"


def test_chat_routes_general_question_to_knowledge_base_tool(client, make_user, auth_headers, db_session, monkeypatch):
    alice = make_user("alice", "Alice")

    seeded_embedding = [1.0] + [0.0] * 1535
    article = SupportArticle(
        question="How do I sell my gold?",
        answer="Go to Sell, choose a quantity, and confirm.",
        category="trading",
        tags=["trading"],
        embedding=seeded_embedding,
    )
    db_session.add(article)
    db_session.commit()

    def fake_chat_completion(messages, tools=None, tool_choice="auto"):
        if tools:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("search_knowledge_base", '{"query": "How do I sell my gold?"}')]
            )
        return _FakeMessage(content="You can sell your gold from the Sell screen.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: seeded_embedding)

    resp = client.post("/chat", json={"message": "How do I sell my gold?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TEXT_ANSWER"
    assert body["data"]["grounded"] is True


def test_chat_returns_error_response_when_llm_unavailable(client, make_user, auth_headers, monkeypatch):
    alice = make_user("alice", "Alice")

    def _raise(*args, **kwargs):
        raise RuntimeError("provider outage")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", _raise)

    resp = client.post("/chat", json={"message": "hello"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "ERROR"
