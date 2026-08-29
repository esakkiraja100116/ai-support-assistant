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

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_recent_transactions" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transactions" in _tool_names(tools):
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

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_recent_transactions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transactions" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_transactions", f'{{"transaction_ids": ["{failed_txn.id}"]}}')]
            )
        return _FakeMessage(content="Your purchase failed because the card was declined.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    resp = client.post("/chat", json={"message": "why did my last purchase fail?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TRANSACTION_EXPLANATION"
    assert body["data"]["transaction"]["id"] == "txn_failed"


def test_chat_summarizes_multiple_resolved_transactions(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    t1 = make_transaction(alice, "txn_1", status="FAILED", failure_reason="Card declined")
    t2 = make_transaction(alice, "txn_2", status="SUCCESS")
    t3 = make_transaction(alice, "txn_3", status="PENDING")
    # A transaction belonging to someone else - must never leak into the summary
    # even if the model somehow named it.
    bob = make_user("bob", "Bob")
    make_transaction(bob, "txn_bob_1")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_recent_transactions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transactions" in names:
            ids = [t1.id, t2.id, t3.id, "txn_bob_1"]
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_transactions", f'{{"transaction_ids": {ids}}}'.replace("'", '"'))]
            )
        return _FakeMessage(content="1 of your last 3 failed due to a declined card; the others succeeded or are pending.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)

    resp = client.post(
        "/chat",
        json={"message": "show me my last 3 transactions and tell me which failed and why"},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TRANSACTION_SUMMARY"
    returned_ids = [t["id"] for t in body["data"]["transactions"]]
    assert set(returned_ids) == {t1.id, t2.id, t3.id}
    assert "txn_bob_1" not in returned_ids


def test_chat_falls_back_to_selection_if_resolved_id_not_in_users_list(
    client, make_user, make_transaction, auth_headers, monkeypatch
):
    """Even if the model hallucinates or is prompt-injected into naming an id that
    isn't in the authenticated user's own fetched list, we must never look it up -
    we fall back to the safe selection list instead of trusting the model's id."""
    alice = make_user("alice", "Alice")
    make_transaction(alice, "txn_a1")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_recent_transactions" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_recent_transactions")])
        if "resolve_transactions" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_transactions", '{"transaction_ids": ["txn_someone_elses"]}')]
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

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "search_knowledge_base" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("search_knowledge_base")])
        if "answer_from_kb" in names:
            return _FakeMessage(
                tool_calls=[
                    _FakeToolCall(
                        "answer_from_kb",
                        f'{{"answer": "You can sell your gold from the Sell screen.", "source_article_ids": [{article.id}]}}',
                    )
                ]
            )
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.kb_service.llm_client.embed", lambda text: seeded_embedding)

    resp = client.post("/chat", json={"message": "How do I sell my gold?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TEXT_ANSWER"
    assert body["data"]["grounded"] is True
    assert body["data"]["sources"] == [article.id]


def test_chat_returns_error_response_when_llm_unavailable(client, make_user, auth_headers, monkeypatch):
    alice = make_user("alice", "Alice")

    def _raise(*args, **kwargs):
        raise RuntimeError("provider outage")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", _raise)

    resp = client.post("/chat", json={"message": "hello"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "ERROR"


def test_chat_escalates_on_explicit_human_request(client, make_user, auth_headers, monkeypatch):
    """The customer doesn't need to have hit any decline at all - a direct
    "I need a human" / "this isn't helping" should escalate immediately,
    even for a first message with empty history."""
    alice = make_user("alice", "Alice")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *a, **kw: _FakeMessage(tool_calls=[_FakeToolCall("request_human_agent")]),
    )

    resp = client.post("/chat", json={"message": "This isn't helping, I need a real person.", "history": []}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "ESCALATE"
    assert body["data"]["contact_email"]


def test_chat_escalates_after_two_consecutive_kb_declines(client, make_user, auth_headers, monkeypatch):
    from app.services.orchestrator import NO_INFO_MESSAGE

    alice = make_user("alice", "Alice")

    def _unexpected_call(*args, **kwargs):
        raise AssertionError("Escalation must be decided before any LLM call, to save cost on this turn")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", _unexpected_call)

    history = [
        {"role": "user", "content": "Do you support international wire transfers?"},
        {"role": "assistant", "content": NO_INFO_MESSAGE},
        {"role": "user", "content": "What about the fees for a wire transfer?"},
        {"role": "assistant", "content": NO_INFO_MESSAGE},
    ]

    resp = client.post("/chat", json={"message": "This isn't helping.", "history": history}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "ESCALATE"
    assert body["data"]["contact_email"]


def test_chat_does_not_escalate_after_only_one_decline(client, make_user, auth_headers, monkeypatch):
    from app.services.orchestrator import NO_INFO_MESSAGE

    alice = make_user("alice", "Alice")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *a, **kw: _FakeMessage(content="Sure, happy to help with that."),
    )

    history = [
        {"role": "user", "content": "Do you support international wire transfers?"},
        {"role": "assistant", "content": NO_INFO_MESSAGE},
    ]

    resp = client.post("/chat", json={"message": "Never mind, how do I sell gold?", "history": history}, headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["type"] != "ESCALATE"


def test_chat_escalation_resets_after_a_real_answer(client, make_user, auth_headers, monkeypatch):
    from app.services.orchestrator import NO_INFO_MESSAGE

    alice = make_user("alice", "Alice")

    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.chat_completion",
        lambda *a, **kw: _FakeMessage(content="Sure, happy to help with that."),
    )

    # Two declines, but a real answer happened after them - the trailing streak is 0.
    history = [
        {"role": "assistant", "content": NO_INFO_MESSAGE},
        {"role": "assistant", "content": NO_INFO_MESSAGE},
        {"role": "user", "content": "How do I sell gold?"},
        {"role": "assistant", "content": "Open the app, go to Portfolio > Sell..."},
    ]

    resp = client.post("/chat", json={"message": "thanks, one more question", "history": history}, headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["type"] != "ESCALATE"
