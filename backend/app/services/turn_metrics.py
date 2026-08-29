"""Aggregates per-call model/token/cost data across a single request so it can
be persisted onto the `Message` row that request produces.

This is deliberately separate from `session_log.py`'s JSONL logging (which
exists purely for observability and is untouched by this module) - here the
aggregated result is actually read back and written to the database. Uses the
same contextvar idiom as `session_log.py` so `llm_client.py` can record into
it without every caller between the router and it needing to pass anything
down explicitly.
"""

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class _Call:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


@dataclass
class TurnMetrics:
    calls: list[_Call] = field(default_factory=list)

    def record(self, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
        self.calls.append(_Call(model, prompt_tokens, completion_tokens, cost_usd))

    @property
    def model_used(self) -> str | None:
        if not self.calls:
            return None
        seen = sorted({c.model for c in self.calls})
        return ", ".join(seen)

    @property
    def prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.calls)

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)


_current: contextvars.ContextVar["TurnMetrics | None"] = contextvars.ContextVar(
    "_current_turn_metrics", default=None
)


@contextmanager
def turn_scope() -> Iterator[TurnMetrics]:
    metrics = TurnMetrics()
    token = _current.set(metrics)
    try:
        yield metrics
    finally:
        _current.reset(token)


def record(model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float) -> None:
    metrics = _current.get()
    if metrics is not None:
        metrics.record(model, prompt_tokens, completion_tokens, cost_usd)
