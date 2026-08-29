"""Thin wrapper around the OpenAI SDK.

This is the single seam the rest of the app talks to for any LLM call. Tests
monkeypatch the functions in this module directly instead of mocking the
OpenAI SDK, so call sites never need to know the SDK's request/response shape.

It's also the single place token usage and cost get logged (see
`session_log.py`) - every call, from every caller, gets recorded here once,
rather than each call site needing to remember to do it.
"""
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings
from app.services import pricing, session_log

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _record_call(kind: str, model: str, usage: Any, message: ChatCompletionMessage | None = None) -> None:
    session = session_log.get_current_session()
    if session is None:
        return

    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    cost = pricing.estimate_cost_usd(model, prompt_tokens, completion_tokens)
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
) -> ChatCompletionMessage:
    """Runs one chat completion call and returns the assistant message
    (which may contain `.tool_calls` and/or `.content`).

    `model` and `reasoning_effort` default to unset/`settings.chat_model` - both
    overrides exist for controlled experiments (e.g. comparing judgment quality
    across models on a fixed question set), not for any app code path to pick
    per request. `reasoning_effort` is only meaningful for reasoning-family
    models, some of which reject tool-calling unless it's explicitly set."""
    used_model = model or settings.chat_model
    kwargs: dict[str, Any] = {"model": used_model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    response = _get_client().chat.completions.create(**kwargs)
    message = response.choices[0].message
    _record_call("chat_completion", used_model, response.usage, message)
    return message


def embed(text: str) -> list[float]:
    response = _get_client().embeddings.create(model=settings.embedding_model, input=text)
    _record_call("embed", settings.embedding_model, response.usage)
    return response.data[0].embedding
