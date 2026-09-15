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

`embed_texts()` (sprint 04) reuses the same client, built from the same
`build_sdk_client()`, for `client.embeddings.generate(...)` - the SDK
exposes embeddings directly and raises the same `openrouter.errors.*`
types `classify()` already matches on, so no parallel error path exists
here. `dimensions`/`encoding_format` are never passed to `generate()`: the
model's native width is what `EMBEDDING_DIMENSIONS` must be set to match
(← AC5), and a returned vector of the wrong width raises rather than
degrades - see `embed_texts()`'s own docstring.

`generate_image()` (sprint 05) reuses the same client for
`client.images.generate(...)` - images go direct through the OpenRouter
SDK, never through LangChain (← D1): the SDK exposes `/images` directly and
raises the same `openrouter.errors.*` types `classify()` already matches
on. Only `model=`/`prompt=` are ever passed - never `n`, `stream`,
`resolution`, `aspect_ratio` or `output_format`. It never returns a
placeholder: every failure mode raises instead (← AC5) - choosing a
fallback belongs to whatever calls this seam, not to the seam itself.
"""

import base64
import binascii
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import openrouter
import structlog
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_openrouter import ChatOpenRouter
from openrouter.components import ImageGenerationResponse
from openrouter.components import ImageGenerationUsage as SdkImageUsage
from openrouter.operations import CreateEmbeddingsResponseBody, CreateEmbeddingsUsage

from app.core.llm.errors import (
    LlmBadRequestError,
    LlmConfigurationError,
    LlmMalformedError,
    classify,
    raise_for_finish_reason,
)
from app.core.llm.retry import call_with_retry, stream_with_retry
from app.core.settings import get_settings

logger = structlog.get_logger()

DEFAULT_TEMPERATURE = 0.7
REQUEST_TIMEOUT_MS = 60_000


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    usage: Usage


@dataclass(frozen=True)
class ImageResult:
    image_bytes: bytes
    media_type: str
    usage: Usage


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

    `max_retries=0` is passed explicitly even though `client=` already makes
    it dead (`ChatOpenRouter` only reads it in `_build_client()`, which
    `validate_environment` skips whenever `client` is already set): sprint
    01 *was* silently retrying with a ~300 s window before `client=` landed,
    so this is a guard against a later edit dropping `client=` resurrecting
    that. Sprint 03's own retry loop (`app/core/llm/retry.py`) owns retry
    deliberately, on top of this seam.
    """
    settings = get_settings()
    if not settings.openrouter_api_key.strip():
        raise LlmConfigurationError()

    return ChatOpenRouter(
        model=model if model is not None else settings.chat_model,
        temperature=temperature if temperature is not None else DEFAULT_TEMPERATURE,
        api_key=settings.openrouter_api_key,
        client=build_sdk_client(settings.openrouter_api_key),
        max_retries=0,
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

    The whole attempt runs through `call_with_retry()` (sprint 03, ←
    `retry.py`), which retries a retryable `LlmError` quietly, per the
    configured budget, before the caller ever sees anything (← D6).
    `chat_model()` is called again on every attempt, so `LlmConfigurationError`
    still raises on attempt 1 and is never retried.
    """

    def _attempt() -> AIMessage:
        try:
            message = chat_model(model=model, temperature=temperature).invoke(prompt)
        except Exception as exc:
            if (err := classify(exc)) is not None:
                raise err from exc
            raise

        raise_for_finish_reason(message)
        return message

    return call_with_retry(_attempt, label="chat")


def chat_stream(
    prompt: LanguageModelInput, *, model: str | None = None, temperature: float | None = None
) -> Iterator[AIMessageChunk]:
    """Stream the reply chunk by chunk, translating provider failures.

    Same exception translation as `chat()`. `raise_for_finish_reason()` runs
    per yielded chunk, *after* that chunk's text has been emitted: a
    mid-stream failure arrives as a silent chunk (`finish_reason == "error"`)
    following partial output already on screen, so the generic failure line
    lands after it, on stderr, exit 1 - not before it.

    Opening the stream (up to and including its first chunk) runs through
    `stream_with_retry()` (sprint 03, ← `retry.py`), which retries only
    until that first chunk is yielded - see its docstring for why a
    mid-stream failure is never retried. `chat_model()` is rebuilt on every
    retried attempt, so `LlmConfigurationError` still raises on attempt 1.
    """

    def _open() -> Iterator[AIMessageChunk]:
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

    return stream_with_retry(_open, label="chat_stream")


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


def _usage_of_embeddings(usage: CreateEmbeddingsUsage | None) -> Usage:
    """This endpoint returns no completion-token count, hence the 0 - not a
    degraded read like `usage_of()`'s `.get(..., 0)`, since the SDK's own
    `CreateEmbeddingsUsage` model has no such field to be absent."""
    if usage is None:
        return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=None)

    return Usage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=0,
        total_tokens=usage.total_tokens,
        cost_usd=usage.cost,
    )


def _vectors_from_response(
    response: CreateEmbeddingsResponseBody, *, expected_count: int, requested_model: str
) -> list[list[float]]:
    """Validate and unwrap `response.data` into plain vectors, in request
    order.

    A non-`CreateEmbeddingsResponseBody` return (the SSE `str` case, ←
    `embeddings.py`), a `str` where a vector should be (the base64 encoding
    variant, never requested here since `encoding_format` is never passed),
    or a `data` list of the wrong length all mean the response cannot be
    trusted at all - `LlmMalformedError()`, retryable like every other
    malformed reply.

    `data` is re-sorted by `.index` only when *every* item carries one: a
    partial set gives nothing reliable to sort on, so response order is
    kept for that case rather than guessed at.

    Any vector whose length differs from `settings.embedding_dimensions`
    raises `LlmConfigurationError` naming both env vars and the width
    actually received, instead of returning it: a silently wrong-width
    vector would corrupt phase 4/6's `vector(n)` column downstream, and
    retrying a misconfiguration cannot help - this refuses rather than
    degrades, deliberately.
    """
    if not isinstance(response, CreateEmbeddingsResponseBody):
        raise LlmMalformedError()

    data = response.data
    if len(data) != expected_count:
        raise LlmMalformedError()
    if any(isinstance(item.embedding, str) for item in data):
        raise LlmMalformedError()

    if all(item.index is not None for item in data):
        data = sorted(data, key=lambda item: item.index)

    settings = get_settings()
    vectors = [list(item.embedding) for item in data]
    for vector in vectors:
        if len(vector) != settings.embedding_dimensions:
            raise LlmConfigurationError(
                f"EMBEDDING_DIMENSIONS is {settings.embedding_dimensions}, but model "
                f"'{requested_model}' (EMBEDDING_MODEL) returned a vector of length "
                f"{len(vector)}."
            )

    return vectors


def embed_texts(texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult:
    """Embed `texts` and return the vectors, in request order, with tokens
    and USD cost.

    `model` falls back to `get_settings().embedding_model` when omitted.
    Empty `texts` raises `LlmBadRequestError()` before any network call -
    there is nothing to send. Otherwise the whole attempt runs through
    `call_with_retry()` (← sprint 03), structured exactly like `chat()`:
    one `_attempt()` closure, rebuilt per attempt, so a blank
    `OPENROUTER_API_KEY` raises `LlmConfigurationError()` on attempt 1 and
    is never retried; the provider call is wrapped in the same
    `except Exception` / `classify()` / re-raise-unclassified shape `chat()`
    uses, so sprint 02's `classify()` and sprint 03's retry work unchanged
    - no parallel error path.

    `dimensions`/`encoding_format` are never passed to `generate()` (←
    AC5): the model's native width is what `EMBEDDING_DIMENSIONS` must
    match, not a value this seam requests.
    """
    if not texts:
        raise LlmBadRequestError()

    def _attempt() -> EmbeddingResult:
        settings = get_settings()
        if not settings.openrouter_api_key.strip():
            raise LlmConfigurationError()

        requested_model = model if model is not None else settings.embedding_model
        try:
            response = build_sdk_client(settings.openrouter_api_key).embeddings.generate(
                input=list(texts), model=requested_model
            )
        except Exception as exc:
            if (err := classify(exc)) is not None:
                raise err from exc
            raise

        vectors = _vectors_from_response(
            response, expected_count=len(texts), requested_model=requested_model
        )
        usage = _usage_of_embeddings(response.usage)
        return EmbeddingResult(vectors=vectors, usage=usage)

    return call_with_retry(_attempt, label="embed")


def _usage_of_image(usage: SdkImageUsage | None) -> Usage:
    """Read token counts and USD cost off an image generation reply.

    `usage.cost` is `OptionalNullable[float]` on the SDK's own model: when
    absent it reads back as `Unset()`, not `None` (← research trap) - only
    an actual `int`/`float` is coerced to `cost_usd`, anything else
    (`Unset()`, `None`) degrades to `None`, matching
    `_usage_of_embeddings()`. `usage is None` degrades the same way, to
    zeros and `cost_usd=None`.
    """
    if usage is None:
        return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=None)

    cost = usage.cost
    cost_usd = float(cost) if isinstance(cost, int | float) else None

    return Usage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=cost_usd,
    )


def generate_image(prompt: str, *, model: str | None = None) -> ImageResult:
    """Generate one portrait image and return its bytes, media type and
    usage, translating provider failures.

    `model` falls back to `get_settings().image_model` when omitted. A
    blank `prompt` raises `LlmBadRequestError()` before any network call -
    there is nothing to send. Otherwise the whole attempt runs through
    `call_with_retry()` (← sprint 03), structured exactly like
    `embed_texts()`: one `_attempt()` closure, rebuilt per attempt, so a
    blank `OPENROUTER_API_KEY` raises `LlmConfigurationError()` on attempt 1
    and is never retried; the provider call is wrapped in the same
    `except Exception` / `classify()` / re-raise-unclassified shape
    `embed_texts()` uses, so `classify()` and the retry layer work
    unchanged - no parallel error path.

    Only `model=`/`prompt=` are ever passed to `client.images.generate()`
    (← AC5): `n`, `stream`, `resolution`, `aspect_ratio` and
    `output_format` are never sent.

    Never returns a substitute (← AC5): a return that is not an
    `ImageGenerationResponse`, an empty `data`, or a `b64_json` that fails
    to decode (`binascii.Error`, otherwise unclassified and liable to
    escape as a foreign exception) all raise `LlmMalformedError()` -
    retryable, capped like every other malformed reply. `media_type` is
    `data[0].media_type`, or `"image/png"` when the provider omits it (the
    documented behaviour for standard raster output).

    A `logger.info("llm_image_request", ...)` line fires before the call,
    with `url` derived from the client's own `get_server_details()` rather
    than a hardcoded literal - the point is to prove the request goes to
    OpenRouter, not to Google's own API (← AC3); a literal would assert
    nothing.
    """
    if not prompt.strip():
        raise LlmBadRequestError()

    def _attempt() -> ImageResult:
        settings = get_settings()
        if not settings.openrouter_api_key.strip():
            raise LlmConfigurationError()

        requested_model = model if model is not None else settings.image_model
        client = build_sdk_client(settings.openrouter_api_key)
        server_url, _ = client.sdk_configuration.get_server_details()
        logger.info("llm_image_request", url=f"{server_url}/images", model=requested_model)

        try:
            response = client.images.generate(model=requested_model, prompt=prompt)
        except Exception as exc:
            if (err := classify(exc)) is not None:
                raise err from exc
            raise

        if not isinstance(response, ImageGenerationResponse) or not response.data:
            raise LlmMalformedError()

        try:
            image_bytes = base64.b64decode(response.data[0].b64_json, validate=True)
        except binascii.Error as exc:
            raise LlmMalformedError() from exc

        media_type = response.data[0].media_type or "image/png"
        usage = _usage_of_image(response.usage)
        return ImageResult(image_bytes=image_bytes, media_type=media_type, usage=usage)

    return call_with_retry(_attempt, label="image")
