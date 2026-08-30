import json
import uuid

from app.models import Conversation
from app.services import tracking_service


class _FakeStreamedCompletion:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks
        self.content = ""
        self.usage = None

    def __iter__(self):
        for chunk in self._chunks:
            self.content += chunk
            yield chunk


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        events.append((event, data))
    return events


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


def test_track_stream_streams_deltas_and_persists(client, make_user, make_redemption_order, auth_headers, monkeypatch, db_session):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_track_stream", status="IN_TRANSIT", awb_number="PRO19460772")

    monkeypatch.setattr("app.services.orchestrator.tracking_service.get_tracking", lambda awb: _fake_tracking_lookup())
    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: _FakeStreamedCompletion(["Your order ", "is in transit, ", "last seen in Bengaluru."]),
    )

    conversation_id = str(uuid.uuid4())
    resp = client.post(
        f"/redemptions/{order.id}/track/stream",
        json={"conversation_id": conversation_id},
        headers=auth_headers(alice),
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    deltas = [d["text"] for e, d in events if e == "delta"]
    assert deltas[-1] == "Your order is in transit, last seen in Bengaluru."

    done_events = [d for e, d in events if e == "done"]
    assert done_events[0]["type"] == "REDEMPTION_TRACKING"
    assert done_events[0]["data"]["tracking"]["order_ref"] == str(order.id)

    conversation = db_session.get(Conversation, uuid.UUID(conversation_id))
    assert conversation is not None
    assert conversation.messages[-1].content == "Your order is in transit, last seen in Bengaluru."


def test_track_stream_null_awb_sends_single_message_without_llm_call(
    client, make_user, make_redemption_order, auth_headers, monkeypatch
):
    alice = make_user("alice", "Alice")
    order = make_redemption_order(alice, "txn_processing_stream", status="PROCESSING", awb_number=None)

    monkeypatch.setattr(
        "app.services.orchestrator.tracking_service.get_tracking",
        lambda awb: (_ for _ in ()).throw(AssertionError("tracking API must not be called without an AWB")),
    )
    monkeypatch.setattr(
        "app.services.orchestrator.llm_client.stream_chat_completion",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no LLM explanation call when there's no AWB")),
    )

    resp = client.post(f"/redemptions/{order.id}/track/stream", headers=auth_headers(alice))

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done_events = [d for e, d in events if e == "done"]
    assert done_events[0]["type"] == "REDEMPTION_TRACKING"
    assert done_events[0]["data"]["tracking"]["awb_available"] is False


def test_track_stream_404_for_other_users_order(client, make_user, make_redemption_order, auth_headers):
    alice = make_user("alice", "Alice")
    bob = make_user("bob", "Bob")
    order = make_redemption_order(bob, "txn_bob_stream")

    resp = client.post(f"/redemptions/{order.id}/track/stream", headers=auth_headers(alice))
    assert resp.status_code == 404
