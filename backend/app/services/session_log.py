"""Per-session JSONL logging: every LLM call, tool call, and final result gets
appended to `logs/<session_id>.jsonl` (one JSON object per line), plus a running
cost total for that session.

Uses a contextvar rather than threading a logger through every function
signature - `llm_client.py` can log the calls it makes without every caller
between the router and it needing to pass a logger object down. This is the
one piece of in-process state in an otherwise stateless backend (the running
per-session cost total); it's purely additive observability, never read for
any authorization or business decision, and safe to lose on restart.

Logging failures are always non-fatal - a full disk or a permissions issue
here must never break an actual chat response.
"""

import contextvars
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

_current: contextvars.ContextVar["SessionRecorder | None"] = contextvars.ContextVar(
    "_current_session", default=None
)
_session_totals: dict[str, float] = {}


class SessionRecorder:
    def __init__(self, session_id: str):
        self.session_id = session_id

    def log(self, kind: str, **fields) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "kind": kind,
            **fields,
        }
        _append_event(self.session_id, event)

    def add_cost(self, amount: float) -> float:
        total = _session_totals.get(self.session_id, 0.0) + amount
        _session_totals[self.session_id] = total
        return total

    @property
    def total_cost_usd(self) -> float:
        return _session_totals.get(self.session_id, 0.0)


def _safe_filename(session_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id) or "session"


def _append_event(session_id: str, event: dict) -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = LOGS_DIR / f"{_safe_filename(session_id)}.jsonl"
        with path.open("a") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        logger.exception("Failed to write session log event (non-fatal)")


@contextmanager
def session_scope(session_id: str) -> Iterator[SessionRecorder]:
    recorder = SessionRecorder(session_id)
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


def get_current_session() -> "SessionRecorder | None":
    return _current.get()
