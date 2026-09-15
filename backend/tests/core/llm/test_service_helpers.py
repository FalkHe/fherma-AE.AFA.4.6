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
"""

import openrouter
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.core.llm import retry as llm_retry
from app.core.llm import service as llm_service
from app.core.llm.errors import LlmRefusedError, LlmUnavailableError


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

    def invoke(self, prompt):
        if self._invoke_error is not None:
            raise self._invoke_error
        return self._invoke_result

    def stream(self, prompt):
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
