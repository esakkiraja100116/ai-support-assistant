from app.services import tracking_service


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


def _fake_tracking_lookup():
    return tracking_service.TrackingLookup(
        current_location="Bengaluru - South",
        latest_event=tracking_service.TrackingEvent(
            type="InTransit", remarks="Arrived at hub", area="Bengaluru - South", event_time="2026-08-29T08:07:00+00:00"
        ),
        history=[
            tracking_service.TrackingEvent(
                type="InTransit", remarks="Despatched", area="Chennai", event_time="2026-08-28T10:15:00+00:00"
            ),
        ],
    )


def test_chat_auto_selects_single_ongoing_order(client, make_user, make_redemption_order, auth_headers, monkeypatch):
    """One ongoing order should go straight to tracking - the resolve call
    must never even happen, mirroring how a single recent transaction
    doesn't need a resolve step for the (nonexistent, single-item) case."""
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_only", status="IN_TRANSIT", awb_number="PRO19460772")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_orders" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}')])
        if "resolve_redemption_orders" in names:
            raise AssertionError("resolve call should never happen for a single ongoing order")
        return _FakeMessage(content="Your Gold Coin order is currently in transit.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.orchestrator.tracking_service.get_tracking", lambda awb: _fake_tracking_lookup())

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_TRACKING"
    assert body["data"]["tracking"]["order_ref"] == str(order.id)


def test_chat_shows_selection_list_for_multiple_ongoing_orders(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    order_a = make_redemption_order(alice, "txn_a", status="IN_TRANSIT", awb_number="PRO_A")
    order_b = make_redemption_order(alice, "txn_b", status="OUT_FOR_DELIVERY", awb_number="PRO_B")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_orders" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}')])
        if "resolve_redemption_orders" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("no_single_redemption_match")])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("tracking should not be called for a selection list")),
    )

    resp = client.post("/chat", json={"message": "where are my orders?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_SELECTION"
    refs = {o["order_ref"] for o in body["data"]["orders"]}
    assert refs == {str(order_a.id), str(order_b.id)}


def test_chat_resolves_specific_order_from_selection(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_bar", status="IN_TRANSIT", product_name="Gold Bar", awb_number="PRO_BAR")
    coin = make_redemption_order(alice, "txn_coin", status="OUT_FOR_DELIVERY", product_name="Gold Coin", awb_number="PRO_COIN")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_orders" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}')])
        if "resolve_redemption_orders" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_redemption_orders", f'{{"order_refs": ["{coin.id}"]}}')]
            )
        return _FakeMessage(content="Your Gold Coin order is out for delivery.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.orchestrator.tracking_service.get_tracking", lambda awb: _fake_tracking_lookup())

    resp = client.post("/chat", json={"message": "track my gold coin"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_TRACKING"
    assert body["data"]["tracking"]["order_ref"] == str(coin.id)


def test_chat_falls_back_to_selection_if_resolved_ref_not_in_users_list(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    """Same defense as resolve_transactions: a hallucinated or injected
    order_ref not in this user's own fetched list must never be trusted -
    fall through to the safe selection list instead."""
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_a", status="IN_TRANSIT", awb_number="PRO_A")
    make_redemption_order(alice, "txn_b", status="OUT_FOR_DELIVERY", awb_number="PRO_B")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_orders" in names:
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}')])
        if "resolve_redemption_orders" in names:
            return _FakeMessage(
                tool_calls=[_FakeToolCall("resolve_redemption_orders", '{"order_refs": ["not-a-real-uuid"]}')]
            )
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("tracking should not be called")),
    )

    resp = client.post("/chat", json={"message": "track my order"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    assert resp.json()["type"] == "REDEMPTION_SELECTION"


def test_chat_no_ongoing_orders_returns_fixed_message_with_zero_tracking_calls(
    client, make_user, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_orders" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}')])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("tracking should not be called with zero orders")),
    )

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "TEXT_ANSWER"
    assert "don't have any ongoing redemption orders" in body["message"]


def test_chat_dedupes_duplicate_get_orders_tool_calls(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    """Regression test for the same class of bug already hit and fixed once
    for search_knowledge_base: if the router issues get_orders
    twice in one response, it must be deduped to a single call - otherwise
    the redemption-tracking handler would run twice and its message would be
    duplicated in the merged response."""
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_only", status="IN_TRANSIT", awb_number="PRO19460772")

    call_count = {"redemptions": 0}

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        names = _tool_names(tools)
        if "get_orders" in names:
            call_count["redemptions"] += 1
            return _FakeMessage(
                tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}'), _FakeToolCall("get_orders", '{"type": "REDEMPTION"}')]
            )
        return _FakeMessage(content="Your order is currently in transit.")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr("app.services.orchestrator.tracking_service.get_tracking", lambda awb: _fake_tracking_lookup())

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    # The response message must not contain the explanation text twice.
    assert body["message"].count("Your order is currently in transit.") == 1


def test_chat_null_awb_order_says_not_available_without_calling_tracking_api(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    make_redemption_order(alice, "txn_processing", status="PROCESSING", awb_number=None)

    def fake_chat_completion(messages, tools=None, tool_choice="auto", model=None, reasoning_effort=None):
        if "get_orders" in _tool_names(tools):
            return _FakeMessage(tool_calls=[_FakeToolCall("get_orders", '{"type": "REDEMPTION"}')])
        return _FakeMessage(content="")

    monkeypatch.setattr("app.services.orchestrator.llm_client.chat_completion", fake_chat_completion)
    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("tracking API must not be called without an AWB")),
    )

    resp = client.post("/chat", json={"message": "where is my order?"}, headers=auth_headers(alice))

    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "REDEMPTION_TRACKING"
    assert body["data"]["tracking"]["awb_available"] is False
    assert "doesn't have tracking information yet" in body["message"]
