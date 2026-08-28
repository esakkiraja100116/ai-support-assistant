"""Thin wrapper around the OpenAI SDK.

This is the single seam the rest of the app talks to for any LLM call. Tests
monkeypatch the functions in this module directly instead of mocking the
OpenAI SDK, so call sites never need to know the SDK's request/response shape.
"""
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from app.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str = "auto",
) -> ChatCompletionMessage:
    """Runs one chat completion call and returns the assistant message
    (which may contain `.tool_calls` and/or `.content`)."""
    kwargs: dict[str, Any] = {"model": settings.chat_model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    response = _get_client().chat.completions.create(**kwargs)
    return response.choices[0].message


def embed(text: str) -> list[float]:
    response = _get_client().embeddings.create(model=settings.embedding_model, input=text)
    return response.data[0].embedding
