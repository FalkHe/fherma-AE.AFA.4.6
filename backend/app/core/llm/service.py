"""The seam between this app and OpenRouter chat models.

`chat_model()` hands back a configured `ChatOpenRouter` (a LangChain
`BaseChatModel`); `usage_of()` reads token counts and USD cost off a reply.
`chat()`/`chat_stream()` wrap `.invoke()`/`.stream()`, turning provider
exceptions into this app's `LlmError` subclasses via `classify()` and
turning a silent mid-stream failure/refusal (`finish_reason` on the reply)
into the matching `LlmError` via `raise_for_finish_reason()`. Callers use the
module reference (`from app.core.llm import service as llm_service`), never
a name import - tests monkeypatch `service.ChatOpenRouter` and
`service.build_sdk_client`.

`build_sdk_client()` hands `ChatOpenRouter` a pre-built `openrouter.OpenRouter`
with the SDK's own retry switched off (`retry_config=None`): left at its
default, the SDK retries 5XX itself with a near-unbounded backoff, which
would make this sprint's own 5XX handling hang for minutes. Sprint 03 owns
retry deliberately, on top of this seam - not invisibly underneath it.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import openrouter
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_openrouter import ChatOpenRouter

from app.core.llm.errors import LlmConfigurationError, classify, raise_for_finish_reason
from app.core.settings import get_settings

DEFAULT_TEMPERATURE = 0.7
REQUEST_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None


def build_sdk_client(api_key: str) -> openrouter.OpenRouter:
    """Build the raw OpenRouter SDK client `ChatOpenRouter` wraps.

    `retry_config=None` switches off the SDK's own retry on 5XX responses -
    left at its default, a 502 hangs for minutes before surfacing. This is
    the whole point of this function and is not optional; do not drop it.

    Module-level so tests can monkeypatch `service.build_sdk_client` to
    return one wired to `httpx.MockTransport` - the injection seam for every
    provider failure class.
    """
    return openrouter.OpenRouter(
        api_key=api_key,
        retry_config=None,
        timeout_ms=REQUEST_TIMEOUT_MS,
    )


def chat_model(*, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
    """Return a configured OpenRouter chat model.

    `model`/`temperature` fall back to `get_settings().chat_model` and
    `DEFAULT_TEMPERATURE` respectively when omitted. Raises
    `LlmConfigurationError` when `OPENROUTER_API_KEY` is blank, before
    `ChatOpenRouter` is constructed at all - its own
    `validate_environment` would otherwise raise a bare `ValueError` at
    construction time.

    `stream_usage` is left at `ChatOpenRouter`'s own default (`True`), so a
    streaming caller's final chunk still carries `usage_metadata` for
    `usage_of()` to read.
    """
    settings = get_settings()
    if not settings.openrouter_api_key.strip():
        raise LlmConfigurationError()

    return ChatOpenRouter(
        model=model if model is not None else settings.chat_model,
        temperature=temperature if temperature is not None else DEFAULT_TEMPERATURE,
        api_key=settings.openrouter_api_key,
        client=build_sdk_client(settings.openrouter_api_key),
    )


def chat(
    prompt: LanguageModelInput, *, model: str | None = None, temperature: float | None = None
) -> AIMessage:
    """Send `prompt` and return the reply, translating provider failures.

    A provider exception is classified via `classify()`: this app's own
    `LlmError` subclass replaces it when recognised, otherwise the original
    exception re-raises unchanged - foreign errors are never swallowed.
    `raise_for_finish_reason()` then turns a silent refusal / mid-stream
    failure recorded on the reply into the matching `LlmError`.
    """
    try:
        message = chat_model(model=model, temperature=temperature).invoke(prompt)
    except Exception as exc:
        if (err := classify(exc)) is not None:
            raise err from exc
        raise

    raise_for_finish_reason(message)
    return message


def chat_stream(
    prompt: LanguageModelInput, *, model: str | None = None, temperature: float | None = None
) -> Iterator[AIMessageChunk]:
    """Stream the reply chunk by chunk, translating provider failures.

    Same exception translation as `chat()`. `raise_for_finish_reason()` runs
    per yielded chunk, *after* that chunk's text has been emitted: a
    mid-stream failure arrives as a silent chunk (`finish_reason == "error"`)
    following partial output already on screen, so the generic failure line
    lands after it, on stderr, exit 1 - not before it.
    """
    stream = chat_model(model=model, temperature=temperature).stream(prompt)
    while True:
        try:
            chunk = next(stream)
        except StopIteration:
            return
        except Exception as exc:
            if (err := classify(exc)) is not None:
                raise err from exc
            raise

        yield chunk
        raise_for_finish_reason(chunk)


def usage_of(message: BaseMessage) -> Usage:
    """Read token counts and USD cost off a chat reply.

    Counts come from `message.usage_metadata`
    (`input_tokens`/`output_tokens`/`total_tokens`); cost from
    `message.response_metadata["cost"]`. Either absent degrades to zeros /
    `None` rather than raising - not every message (or every provider reply)
    carries usage.
    """
    usage_metadata = getattr(message, "usage_metadata", None) or {}
    cost = message.response_metadata.get("cost")

    return Usage(
        prompt_tokens=usage_metadata.get("input_tokens", 0),
        completion_tokens=usage_metadata.get("output_tokens", 0),
        total_tokens=usage_metadata.get("total_tokens", 0),
        cost_usd=cost,
    )
