"""Tiny shared helpers for the SSE streaming endpoints (routers/chat.py,
routers/transactions.py) - just the event-framing format and the artificial
per-delta pacing delay, so both routers stay in sync without duplicating
either."""

import json

# Small artificial pacing delay per delta so the typewriter effect is visibly
# perceptible in the frontend - OpenAI's own streaming can otherwise deliver
# a short reply's chunks over localhost fast enough to look like a single pop-in.
STREAM_DELTA_DELAY_SECONDS = 0.02


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
