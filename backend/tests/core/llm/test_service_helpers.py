"""Sprint 02 WI3 — `app/core/llm/service.py`: `build_sdk_client`, `chat`,
`chat_stream` (← research.md Interfaces, `core/llm/service.py`).

This work item's own unit coverage, isolated from `chat_model()`'s
construction path (already covered by sprint 01's `test_service.py`) by
monkeypatching `service.chat_model` to hand back a scripted stand-in for the
`BaseChatModel` it would otherwise return. `service.classify` is likewise
monkeypatched for the control-flow tests (WI3 owns the *wiring* to
`classify`/`raise_for_finish_reason`, not their dispatch tables - those are
WI2's `test_error_classification.py`). `raise_for_finish_reason` is used for
real in the ordering test, since that behaviour is this work item's own.

Never touches the network; not one of the qa-owned filenames
(`test_errors.py` / `test_service.py` / `test_commands.py`).

Sprint 03 WI3 wraps `chat()`/`chat_stream()` in `retry.call_with_retry()`/
`stream_with_retry()`, so a classified error that happens to be retryable
(e.g. `LlmUnavailableError` below) is now retried underneath these tests
too, not just raised once. `_no_real_sleep` (autouse) stubs `retry._sleep`
for the whole module so that retrying never costs this suite wall-clock
time - the retry *count* itself is qa's `test_retry.py`/`test_commands.py`
to assert, not this file's.

Sprint 04 WI2 adds `embed_texts()`'s own unit coverage below, in the same
spirit: `service.build_sdk_client` is monkeypatched to a scripted stand-in
for the raw SDK client (never a real `httpx.MockTransport` - that full
round-trip, including `classify()`'s real dispatch table, is qa's own
`test_embeddings.py`), so this file's embedding tests are the seam's own
control flow only - empty-input / blank-key short-circuits, the malformed
and width-mismatch checks, index-based reordering, and the usage mapping.

Sprint 010-02 WI1 adds `ainvoke_chat()`'s own unit coverage at the bottom:
a `_StubRunnable` fakes the already-built runnable it takes instead of a
`BaseChatModel`, driven with `asyncio.run()` the way this repo's other
async tests are (no `pytest-asyncio` dependency). `retry._asleep` is
monkeypatched alongside `retry._sleep` so its retries never really sleep
either.
"""

import asyncio

import openrouter
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from openrouter.operations import (
    CreateEmbeddingsData,
    CreateEmbeddingsResponseBody,
    CreateEmbeddingsUsage,
)

from app.core.llm import retry as llm_retry
from app.core.llm import service as llm_service
from app.core.llm.errors import (
    LlmAuthError,
    LlmBadRequestError,
    LlmConfigurationError,
    LlmMalformedError,
    LlmRefusedError,
    LlmUnavailableError,
)
from app.core.settings import get_settings


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr(llm_retry, "_sleep", lambda seconds: None)


class _ForeignError(Exception):
    """Stands in for an exception `classify()` does not recognise."""


class _StubChatModel:
    """Fakes the `BaseChatModel` `chat_model()` would otherwise return."""

    def __init__(self, *, invoke_result=None, invoke_error=None, chunks=None, stream_error=None):
        self._invoke_result = invoke_result
        self._invoke_error = invoke_error
        self._chunks = chunks or []
        self._stream_error = stream_error

    # `config=` is how the seam hands LangChain its run name and the
    # Langfuse callback handler (`core/tracing/`); a real `BaseChatModel`
    # accepts it on both methods.
    def invoke(self, prompt, config=None):
        if self._invoke_error is not None:
            raise self._invoke_error
        return self._invoke_result

    def stream(self, prompt, config=None):
        yield from self._chunks
        if self._stream_error is not None:
            raise self._stream_error


def test_build_sdk_client_disables_sdk_retry_and_sets_the_seam_timeout():
    client = llm_service.build_sdk_client("a-key")

    assert isinstance(client, openrouter.OpenRouter)
    assert client.sdk_configuration.retry_config is None
    assert client.sdk_configuration.timeout_ms == llm_service.REQUEST_TIMEOUT_MS
    assert llm_service.REQUEST_TIMEOUT_MS == 60_000


def test_chat_model_passes_a_retry_disabled_client_to_chat_open_router(
    recording_chat_open_router, monkeypatch
):
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)

    llm_service.chat_model()

    client = recording_chat_open_router.calls[-1]["client"]
    assert isinstance(client, openrouter.OpenRouter)
    assert client.sdk_configuration.retry_config is None


def test_chat_raises_the_classified_error_for_a_recognised_exception(monkeypatch):
    provider_exc = _ForeignError("502 from the provider")
    classified = LlmUnavailableError("502 from the provider")
    monkeypatch.setattr(
        llm_service, "chat_model", lambda **_: _StubChatModel(invoke_error=provider_exc)
    )
    monkeypatch.setattr(
        llm_service, "classify", lambda exc: classified if exc is provider_exc else None
    )

    with pytest.raises(LlmUnavailableError) as excinfo:
        llm_service.chat("hello")

    assert excinfo.value is classified
    assert excinfo.value.__cause__ is provider_exc


def test_chat_reraises_an_unclassified_exception_unchanged(monkeypatch):
    provider_exc = _ForeignError("not ours")
    monkeypatch.setattr(
        llm_service, "chat_model", lambda **_: _StubChatModel(invoke_error=provider_exc)
    )
    monkeypatch.setattr(llm_service, "classify", lambda exc: None)

    with pytest.raises(_ForeignError):
        llm_service.chat("hello")


def test_chat_raises_for_a_refused_reply(monkeypatch):
    reply = AIMessage(content="", response_metadata={"finish_reason": "content_filter"})
    monkeypatch.setattr(llm_service, "chat_model", lambda **_: _StubChatModel(invoke_result=reply))

    with pytest.raises(LlmRefusedError):
        llm_service.chat("hello")


def test_chat_returns_the_reply_when_finish_reason_is_unremarkable(monkeypatch):
    reply = AIMessage(content="fine", response_metadata={"finish_reason": "stop"})
    monkeypatch.setattr(llm_service, "chat_model", lambda **_: _StubChatModel(invoke_result=reply))

    assert llm_service.chat("hello") is reply


def test_chat_stream_yields_a_failing_chunks_text_before_raising_for_it(monkeypatch):
    # The generic failure line must land on stderr *after* partial output is
    # already on screen: the chunk that will fail is still yielded first.
    good = AIMessageChunk(content="partial ", response_metadata={"finish_reason": None})
    bad = AIMessageChunk(content="answer", response_metadata={"finish_reason": "error"})
    monkeypatch.setattr(llm_service, "chat_model", lambda **_: _StubChatModel(chunks=[good, bad]))

    stream = llm_service.chat_stream("hello")

    assert next(stream) is good
    assert next(stream) is bad
    with pytest.raises(LlmUnavailableError):
        next(stream)


def test_chat_stream_classifies_a_mid_stream_exception(monkeypatch):
    good = AIMessageChunk(content="partial ", response_metadata={"finish_reason": None})
    provider_exc = _ForeignError("connection dropped")
    classified = LlmUnavailableError("connection dropped")
    monkeypatch.setattr(
        llm_service,
        "chat_model",
        lambda **_: _StubChatModel(chunks=[good], stream_error=provider_exc),
    )
    monkeypatch.setattr(
        llm_service, "classify", lambda exc: classified if exc is provider_exc else None
    )

    stream = llm_service.chat_stream("hello")
    assert next(stream) is good
    with pytest.raises(LlmUnavailableError) as excinfo:
        next(stream)

    assert excinfo.value is classified
    assert excinfo.value.__cause__ is provider_exc


def test_chat_stream_reraises_an_unclassified_mid_stream_exception_unchanged(monkeypatch):
    provider_exc = _ForeignError("not ours")
    monkeypatch.setattr(
        llm_service, "chat_model", lambda **_: _StubChatModel(chunks=[], stream_error=provider_exc)
    )
    monkeypatch.setattr(llm_service, "classify", lambda exc: None)

    stream = llm_service.chat_stream("hello")
    with pytest.raises(_ForeignError):
        next(stream)


class _StubEmbeddingsEndpoint:
    """Fakes the `.embeddings` attribute of the raw SDK client
    `build_sdk_client()` would otherwise return. `.calls` records every
    `generate()` call's kwargs, so a test can assert `dimensions`/
    `encoding_format` were never passed (← AC5) alongside the `model`/
    `input` that were."""

    def __init__(self, *, result=None, error=None):
        self._result = result
        self._error = error
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


class _StubSdkClient:
    def __init__(self, *, result=None, error=None):
        self.embeddings = _StubEmbeddingsEndpoint(result=result, error=error)


def _embeddings_response(items, *, usage=None):
    """`items` is a list of `(vector, index)`; `index=None` mimics a data
    item that carries no `.index` at all."""
    data = [
        CreateEmbeddingsData(embedding=vector, object="embedding", index=index)
        for vector, index in items
    ]
    return CreateEmbeddingsResponseBody(
        data=data, model="test/embedding-model", object="list", usage=usage
    )


def test_embed_texts_rejects_empty_input_before_any_network_call(monkeypatch):
    calls = []
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: calls.append(key))

    with pytest.raises(LlmBadRequestError):
        llm_service.embed_texts([])

    assert calls == []


def test_embed_texts_raises_configuration_error_for_a_blank_key_without_retrying(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    build_calls = []
    monkeypatch.setattr(
        llm_service, "build_sdk_client", lambda key: build_calls.append(key) or _StubSdkClient()
    )

    try:
        with pytest.raises(LlmConfigurationError):
            llm_service.embed_texts(["hello"])
    finally:
        get_settings.cache_clear()

    assert build_calls == []


def test_embed_texts_never_sends_dimensions_or_encoding_format(monkeypatch):
    stub = _StubSdkClient(result=_embeddings_response([([1.0, 2.0, 3.0, 4.0], 0)]))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    llm_service.embed_texts(["hello"])

    call = stub.embeddings.calls[-1]
    assert "dimensions" not in call
    assert "encoding_format" not in call
    assert call["input"] == ["hello"]
    assert call["model"] == get_settings().embedding_model


def test_embed_texts_passes_the_requested_model_when_given(monkeypatch):
    stub = _StubSdkClient(result=_embeddings_response([([1.0, 2.0, 3.0, 4.0], 0)]))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    llm_service.embed_texts(["hello"], model="some/other-model")

    assert stub.embeddings.calls[-1]["model"] == "some/other-model"


def test_embed_texts_reorders_vectors_by_index_when_every_item_carries_one(monkeypatch):
    shuffled = [([2.0, 2.0, 2.0, 2.0], 1), ([1.0, 1.0, 1.0, 1.0], 0)]
    stub = _StubSdkClient(result=_embeddings_response(shuffled))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    result = llm_service.embed_texts(["a", "b"])

    assert result.vectors == [[1.0, 1.0, 1.0, 1.0], [2.0, 2.0, 2.0, 2.0]]


def test_embed_texts_keeps_response_order_when_index_is_only_partially_present(monkeypatch):
    partial = [([2.0, 2.0, 2.0, 2.0], None), ([1.0, 1.0, 1.0, 1.0], 0)]
    stub = _StubSdkClient(result=_embeddings_response(partial))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    result = llm_service.embed_texts(["a", "b"])

    assert result.vectors == [[2.0, 2.0, 2.0, 2.0], [1.0, 1.0, 1.0, 1.0]]


def test_embed_texts_raises_malformed_for_the_sse_str_response(monkeypatch):
    stub = _StubSdkClient(result="data: [DONE]\n\n")
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    with pytest.raises(LlmMalformedError):
        llm_service.embed_texts(["hello"])


def test_embed_texts_raises_malformed_for_a_base64_string_embedding(monkeypatch):
    stub = _StubSdkClient(result=_embeddings_response([("base64-blob", 0)]))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    with pytest.raises(LlmMalformedError):
        llm_service.embed_texts(["hello"])


def test_embed_texts_raises_malformed_when_data_count_does_not_match_input_count(monkeypatch):
    stub = _StubSdkClient(
        result=_embeddings_response([([1.0, 2.0, 3.0, 4.0], 0), ([1.0, 2.0, 3.0, 4.0], 1)])
    )
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    with pytest.raises(LlmMalformedError):
        llm_service.embed_texts(["only one text"])


def test_embed_texts_raises_configuration_error_naming_both_env_vars_on_width_mismatch(monkeypatch):
    stub = _StubSdkClient(result=_embeddings_response([([1.0, 2.0, 3.0], 0)]))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    with pytest.raises(LlmConfigurationError) as excinfo:
        llm_service.embed_texts(["hello"])

    message = str(excinfo.value)
    assert "EMBEDDING_DIMENSIONS" in message
    assert "EMBEDDING_MODEL" in message
    assert "3" in message


def test_embed_texts_maps_prompt_and_total_tokens_and_cost_with_zero_completion(monkeypatch):
    usage = CreateEmbeddingsUsage(prompt_tokens=7, total_tokens=7, cost=1.4e-06)
    stub = _StubSdkClient(result=_embeddings_response([([1.0, 2.0, 3.0, 4.0], 0)], usage=usage))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    result = llm_service.embed_texts(["hello"])

    assert result.usage == llm_service.Usage(
        prompt_tokens=7, completion_tokens=0, total_tokens=7, cost_usd=1.4e-06
    )


def test_embed_texts_degrades_to_zero_usage_and_no_cost_when_usage_is_absent(monkeypatch):
    stub = _StubSdkClient(result=_embeddings_response([([1.0, 2.0, 3.0, 4.0], 0)], usage=None))
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)

    result = llm_service.embed_texts(["hello"])

    assert result.usage == llm_service.Usage(
        prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=None
    )


def test_embed_texts_raises_the_classified_error_for_a_recognised_exception(monkeypatch):
    provider_exc = _ForeignError("502 from the provider")
    classified = LlmUnavailableError("502 from the provider")
    stub = _StubSdkClient(error=provider_exc)
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)
    monkeypatch.setattr(
        llm_service, "classify", lambda exc: classified if exc is provider_exc else None
    )

    with pytest.raises(LlmUnavailableError) as excinfo:
        llm_service.embed_texts(["hello"])

    assert excinfo.value is classified
    assert excinfo.value.__cause__ is provider_exc


def test_embed_texts_reraises_an_unclassified_exception_unchanged(monkeypatch):
    provider_exc = _ForeignError("not ours")
    stub = _StubSdkClient(error=provider_exc)
    monkeypatch.setattr(llm_service, "build_sdk_client", lambda key: stub)
    monkeypatch.setattr(llm_service, "classify", lambda exc: None)

    with pytest.raises(_ForeignError):
        llm_service.embed_texts(["hello"])


# --- sprint 010-02 WI1: `ainvoke_chat()` -----------------------------------
#
# `ainvoke_chat()` never calls `chat_model()` - it takes an already-built
# runnable - so these tests hand it a `_StubRunnable` directly rather than
# monkeypatching `service.chat_model` the way the `chat()` tests above do.
# `retry._asleep` is monkeypatched (not `retry._sleep`, which `chat()`'s own
# sync path uses) so the async retry loop underneath never really sleeps.


class _StubRunnable:
    """Fakes an already-built, already-tool-bound `Runnable` - what a
    caller like the game agent would hand `ainvoke_chat()`, never a raw
    `BaseChatModel`."""

    def __init__(self, *, results=None, error=None):
        self._results = list(results or [])
        self._error = error
        self.calls: list[object] = []

    async def ainvoke(self, prompt, config=None):
        self.calls.append(prompt)
        if self._results:
            next_result = self._results.pop(0)
            if isinstance(next_result, BaseException):
                raise next_result
            return next_result
        if self._error is not None:
            raise self._error
        raise AssertionError("_StubRunnable.ainvoke called with nothing scripted")


@pytest.fixture(autouse=True)
def _no_real_asleep(monkeypatch):
    monkeypatch.setattr(llm_retry, "_asleep", _noop_asleep)


async def _noop_asleep(seconds):
    return None


def test_ainvoke_chat_retries_a_retryable_failure_once_then_returns_the_reply():
    # ← behaviour: a retryable error fails once and the call then succeeds
    # quietly, returning the reply.
    reply = AIMessage(content="fine", response_metadata={"finish_reason": "stop"})
    model = _StubRunnable(results=[LlmUnavailableError("502"), reply])

    result = asyncio.run(llm_service.ainvoke_chat(model, "hello"))

    assert result is reply
    assert len(model.calls) == 2


def test_ainvoke_chat_raises_a_non_retryable_failure_at_once():
    # ← behaviour: a non-retryable error is raised at once with no second
    # attempt.
    model = _StubRunnable(error=LlmAuthError("bad key"))

    with pytest.raises(LlmAuthError):
        asyncio.run(llm_service.ainvoke_chat(model, "hello"))

    assert len(model.calls) == 1


def test_ainvoke_chat_refuses_at_once_for_a_content_filter_finish_reason():
    # ← the other `raise_for_finish_reason` outcome: a refusal is
    # non-retryable, attempted once, same as any other non-retryable class.
    refusal = AIMessage(content="", response_metadata={"finish_reason": "content_filter"})
    model = _StubRunnable(results=[refusal])

    with pytest.raises(LlmRefusedError):
        asyncio.run(llm_service.ainvoke_chat(model, "hello"))

    assert len(model.calls) == 1


def test_ainvoke_chat_caps_a_malformed_reply_at_two_attempts():
    # ← behaviour: a malformed reply is capped at two attempts, not the
    # full configured budget - same `MALFORMED_MAX_ATTEMPTS` cap `chat()`
    # already retries under.
    model = _StubRunnable(error=LlmMalformedError("truncated"))

    with pytest.raises(LlmMalformedError):
        asyncio.run(llm_service.ainvoke_chat(model, "hello"))

    assert len(model.calls) == llm_retry.MALFORMED_MAX_ATTEMPTS


def test_ainvoke_chat_translates_a_recognised_provider_exception(monkeypatch):
    provider_exc = _ForeignError("502 from the provider")
    classified = LlmUnavailableError("502 from the provider")
    monkeypatch.setattr(
        llm_service, "classify", lambda exc: classified if exc is provider_exc else None
    )
    model = _StubRunnable(error=provider_exc)

    with pytest.raises(LlmUnavailableError) as excinfo:
        asyncio.run(llm_service.ainvoke_chat(model, "hello"))

    assert excinfo.value is classified
    assert excinfo.value.__cause__ is provider_exc


def test_ainvoke_chat_reraises_an_unclassified_exception_unchanged(monkeypatch):
    provider_exc = _ForeignError("not ours")
    monkeypatch.setattr(llm_service, "classify", lambda exc: None)
    model = _StubRunnable(error=provider_exc)

    with pytest.raises(_ForeignError):
        asyncio.run(llm_service.ainvoke_chat(model, "hello"))


def test_ainvoke_chat_never_calls_chat_model(monkeypatch):
    # ← contract: unlike `chat()`, `ainvoke_chat()` must not build its own
    # model - `LlmConfigurationError` stays a `build_agent()`-time failure.
    def _explode(**_):
        raise AssertionError("ainvoke_chat must not call chat_model()")

    monkeypatch.setattr(llm_service, "chat_model", _explode)
    reply = AIMessage(content="fine", response_metadata={"finish_reason": "stop"})
    model = _StubRunnable(results=[reply])

    result = asyncio.run(llm_service.ainvoke_chat(model, "hello"))

    assert result is reply
