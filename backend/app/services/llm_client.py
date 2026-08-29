"""Thin wrapper around the OpenAI SDK.

This is the single seam the rest of the app talks to for any LLM call. Tests
monkeypatch the functions in this module directly instead of mocking the
OpenAI SDK, so call sites never need to know the SDK's request/response shape.

It's also the single place token usage and cost get logged (see
`session_log.py`) - every call, from every caller, gets recorded here once,
rather than each call site needing to remember to do it.
"""
from typing import Any, Iterator

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings
from app.services import pricing, session_log, turn_metrics
from app.services.turn_metrics import TurnMetrics

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _record_call(
    kind: str,
    model: str,
    usage: Any,
    message: ChatCompletionMessage | None = None,
    metrics: TurnMetrics | None = None,
) -> None:
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    cost = pricing.estimate_cost_usd(model, prompt_tokens, completion_tokens)
    # `metrics`, when given, is recorded into directly instead of the
    # contextvar-based turn_metrics module - contextvars don't survive being
    # set/reset across the different worker-pool threads a sync generator
    # driven by Starlette's StreamingResponse can run on (ContextVar.reset()
    # raises "created in a different Context"), so the streaming path
    # (orchestrator.StreamedChatTurn) passes its own plain TurnMetrics
    # instance explicitly instead of relying on turn_scope().
    if metrics is not None:
        metrics.record(model, prompt_tokens, completion_tokens, cost)
    else:
        turn_metrics.record(model, prompt_tokens, completion_tokens, cost)

    session = session_log.get_current_session()
    if session is None:
        return

    total = session.add_cost(cost)

    event: dict[str, Any] = {
        "call": kind,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": round(cost, 6),
        "session_total_cost_usd": round(total, 6),
    }
    if message is not None:
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            event["tool_calls"] = [
                {"name": c.function.name, "arguments": c.function.arguments} for c in tool_calls
            ]
        if message.content:
            event["content"] = message.content
    session.log("llm_call", **event)


def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
    model: str | None = None,
    reasoning_effort: str | None = None,
    metrics: TurnMetrics | None = None,
) -> ChatCompletionMessage:
    """Runs one chat completion call and returns the assistant message
    (which may contain `.tool_calls` and/or `.content`).

    `model` and `reasoning_effort` default to unset/`settings.chat_model` - both
    overrides exist for controlled experiments (e.g. comparing judgment quality
    across models on a fixed question set), not for any app code path to pick
    per request. `reasoning_effort` is only meaningful for reasoning-family
    models, some of which reject tool-calling unless it's explicitly set.
    `metrics` - see _record_call's docstring note - only the streaming
    orchestrator path passes this."""
    used_model = model or settings.chat_model
    kwargs: dict[str, Any] = {"model": used_model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    response = _get_client().chat.completions.create(**kwargs)
    message = response.choices[0].message
    _record_call("chat_completion", used_model, response.usage, message, metrics=metrics)
    return message


class StreamedCompletion:
    """Wraps an OpenAI streaming response. Iterating yields each content
    delta string as it arrives; `.content` accumulates the full text and
    `.usage` is populated once the stream ends (from the final chunk, via
    stream_options={"include_usage": True}). Cost/token recording happens
    exactly once, when the iterator is exhausted - the same single
    _record_call choke point chat_completion() already uses, so turn_metrics/
    session_log work identically for streamed calls with no changes to
    either module."""

    def __init__(self, raw_stream: Any, kind: str, model: str, metrics: TurnMetrics | None = None):
        self._raw_stream = raw_stream
        self._kind = kind
        self._model = model
        self._metrics = metrics
        self.content = ""
        self.usage: Any = None

    def __iter__(self) -> Iterator[str]:
        for chunk in self._raw_stream:
            if chunk.usage is not None:
                self.usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                self.content += delta
                yield delta
        _record_call(self._kind, self._model, self.usage, metrics=self._metrics)


def stream_chat_completion(
    messages: list[dict[str, Any]],
    model: str | None = None,
    reasoning_effort: str | None = None,
    metrics: TurnMetrics | None = None,
) -> StreamedCompletion:
    """Plain content-generation call (no tools) streamed token-by-token -
    used for the final free-text generation step (transaction explanations,
    KB answers, small talk replies), never for a tool-routed decision call.
    `metrics` - see _record_call's docstring note - the streaming orchestrator
    path always passes its own TurnMetrics here rather than relying on the
    contextvar-based turn_scope()."""
    used_model = model or settings.chat_model
    kwargs: dict[str, Any] = {
        "model": used_model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    raw_stream = _get_client().chat.completions.create(**kwargs)
    return StreamedCompletion(raw_stream, "chat_completion_stream", used_model, metrics=metrics)


def embed(text: str) -> list[float]:
    response = _get_client().embeddings.create(model=settings.embedding_model, input=text)
    _record_call("embed", settings.embedding_model, response.usage)
    return response.data[0].embedding
