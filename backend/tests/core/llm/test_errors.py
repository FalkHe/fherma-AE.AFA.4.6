"""qa acceptance tests — sprint 001/02: the eight LLM failure classes are
distinguishable at the seam, behind one shared message (AC1, AC2, AC5).

Black-box: every test drives `app.core.llm.service.chat()` /
`chat_stream()` — never `classify()` directly with a fabricated exception —
through a stub OpenRouter gateway wired in at the one seam the binding
interface names for this (`service.build_sdk_client`, monkeypatched to hand
back a real `openrouter.OpenRouter` client built on `httpx.MockTransport`).
No test in this file ever reaches a real socket (← AC2): `_block_real_network`
below fails any test that falls through to `httpx.HTTPTransport`, and the
key used throughout is a conspicuous, non-functional placeholder, never a
real credential — a stub gateway is enough (← decisions.md: "Failure
injection needs no key: an override base URL plus a bogus model id.").

`classify()`'s own dispatch table (status code → class, `httpx.*` → class,
`pydantic_core.ValidationError` → malformed) is WI2's own unit coverage in
`test_error_classification.py`; this file proves the *seam* reaches the same
eight classes for real triggers, including the mid-stream "silent chunk"
case research.md calls out: `finish_reason == "error" | "content_filter"`
arrives as an ordinary chunk, not an exception, so only *consuming* the
`chat_stream()` generator inside `pytest.raises` (not merely calling it,
which just builds the generator) observes the failure.
"""

import json as jsonlib

import httpx
import openrouter
import pytest

from app.core.errors import ErrorCode
from app.core.llm import service as llm_service
from app.core.llm.errors import (
    LlmAuthError,
    LlmBadRequestError,
    LlmBudgetError,
    LlmMalformedError,
    LlmRateLimitError,
    LlmRefusedError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from app.core.settings import get_settings

DUMMY_API_KEY = "sk-or-v1-not-a-real-key-0000000000000000000000000000"


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Fails any test whose request falls through to a real socket, so AC2
    ("no API key -- a stub gateway is enough") does not rest solely on every
    test remembering to wire the mock transport correctly."""

    def _forbidden(*args, **kwargs):
        raise AssertionError("a real network call was attempted")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _forbidden)


def _stub_gateway(monkeypatch, handler):
    """Injects a stub OpenRouter gateway at the seam the binding interface
    names for this (`service.build_sdk_client`), wired to
    `httpx.MockTransport` -- the only network boundary any test here
    crosses."""

    def _build(api_key):
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", _build)


def _status_handler(status_code, message="the provider said no"):
    def handler(request):
        body = {"error": {"code": status_code, "message": message}}
        return httpx.Response(status_code, json=body)

    return handler


def _raising_handler(exc):
    def handler(request):
        raise exc

    return handler


def _stream_chunk(content, finish_reason):
    return {
        "id": "gen-1",
        "created": 1,
        "model": "test/model",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
    }


def _finish_reason_handler(finish_reason):
    def handler(request):
        body = "".join(
            f"data: {jsonlib.dumps(chunk)}\n\n"
            for chunk in (_stream_chunk("partial ", None), _stream_chunk("", finish_reason))
        )
        body += "data: [DONE]\n\n"
        headers = {"content-type": "text/event-stream"}
        return httpx.Response(200, content=body.encode(), headers=headers)

    return handler


class TestAC1StatusTriggeredClasses:
    """Each of the eight raised for its own trigger, via a stub gateway
    reached through `service.build_sdk_client` (← AC1)."""

    @pytest.mark.parametrize(
        ("status_code", "expected_cls"),
        [
            (400, LlmBadRequestError),
            (401, LlmAuthError),
            (402, LlmBudgetError),
            (403, LlmRefusedError),
            (408, LlmTimeoutError),
            (429, LlmRateLimitError),
            (502, LlmUnavailableError),
        ],
    )
    def test_ac1_status_code_raises_its_class(self, monkeypatch, status_code, expected_cls):
        # ← AC1
        _stub_gateway(monkeypatch, _status_handler(status_code, message="provider says no"))

        with pytest.raises(expected_cls) as excinfo:
            llm_service.chat("Roll a d20.")

        assert excinfo.value.code is expected_cls.code
        assert excinfo.value.provider_message == "provider says no"
        assert str(excinfo.value) == "The AI service could not complete that request."

    def test_ac1_a_200_the_gateway_rejects_raises_malformed(self, monkeypatch):
        # ← AC1: LLM_MALFORMED's trigger is a parse failure on a 200 the SDK
        # itself cannot validate against its own response schema.
        _stub_gateway(monkeypatch, _malformed_200_handler())

        with pytest.raises(LlmMalformedError):
            llm_service.chat("Roll a d20.")


def _malformed_200_handler():
    def handler(request):
        return httpx.Response(200, json={})

    return handler


class TestAC1ClientSideTriggeredClasses:
    """`httpx.TimeoutException` → timeout, `httpx.ConnectError` →
    unavailable -- the two client-side triggers named alongside the status
    table (← AC1)."""

    def test_ac1_timeout_exception_raises_llm_timeout_error(self, monkeypatch):
        # ← AC1
        _stub_gateway(monkeypatch, _raising_handler(httpx.TimeoutException("timed out")))

        with pytest.raises(LlmTimeoutError):
            llm_service.chat("Roll a d20.")

    def test_ac1_connect_error_raises_llm_unavailable_error(self, monkeypatch):
        # ← AC1
        _stub_gateway(monkeypatch, _raising_handler(httpx.ConnectError("no connection")))

        with pytest.raises(LlmUnavailableError):
            llm_service.chat("Roll a d20.")


class TestAC1MidStreamSilentChunks:
    """Mid-stream failure and refusal arrive as ordinary chunks, not
    exceptions (`finish_reason == "error" | "content_filter"`); only
    consuming the generator inside `pytest.raises` sees them (← AC1)."""

    def test_ac1_content_filter_finish_reason_raises_refused(self, monkeypatch):
        # ← AC1
        _stub_gateway(monkeypatch, _finish_reason_handler("content_filter"))

        stream = llm_service.chat_stream("Roll a d20.")
        with pytest.raises(LlmRefusedError):
            list(stream)

    def test_ac1_error_finish_reason_raises_unavailable(self, monkeypatch):
        # ← AC1
        _stub_gateway(monkeypatch, _finish_reason_handler("error"))

        stream = llm_service.chat_stream("Roll a d20.")
        with pytest.raises(LlmUnavailableError):
            list(stream)

    def test_ac1_calling_chat_stream_alone_does_not_raise_yet(self, monkeypatch):
        # The trap itself: building the generator runs no code. Only
        # iterating it reaches the provider call.
        _stub_gateway(monkeypatch, _finish_reason_handler("error"))

        stream = llm_service.chat_stream("Roll a d20.")  # must not raise here
        with pytest.raises(LlmUnavailableError):
            list(stream)


class TestAC5Retryable:
    """`retryable` is True for exactly rate-limit, timeout, unavailable and
    malformed, False for the other four (← AC5)."""

    @pytest.mark.parametrize(
        ("cls", "expected_code", "expected_retryable"),
        [
            (LlmAuthError, ErrorCode.LLM_AUTH, False),
            (LlmBudgetError, ErrorCode.LLM_BUDGET, False),
            (LlmRateLimitError, ErrorCode.LLM_RATE_LIMIT, True),
            (LlmTimeoutError, ErrorCode.LLM_TIMEOUT, True),
            (LlmRefusedError, ErrorCode.LLM_REFUSED, False),
            (LlmUnavailableError, ErrorCode.LLM_UNAVAILABLE, True),
            (LlmMalformedError, ErrorCode.LLM_MALFORMED, True),
            (LlmBadRequestError, ErrorCode.LLM_BAD_REQUEST, False),
        ],
    )
    def test_ac5_retryable_flag_per_class(self, cls, expected_code, expected_retryable):
        # ← AC5
        exc = cls()

        assert exc.code is expected_code
        assert exc.retryable is expected_retryable

    def test_ac5_exactly_four_classes_are_retryable(self):
        # ← AC5
        classes = [
            LlmAuthError,
            LlmBudgetError,
            LlmRateLimitError,
            LlmTimeoutError,
            LlmRefusedError,
            LlmUnavailableError,
            LlmMalformedError,
            LlmBadRequestError,
        ]
        retryable = {cls for cls in classes if cls().retryable}
        expected = {LlmRateLimitError, LlmTimeoutError, LlmUnavailableError, LlmMalformedError}

        assert retryable == expected


class TestAC2NoRealApiKeyNeeded:
    """The whole thing runs with no real API key -- a stub gateway raising
    each status is enough (← AC2)."""

    def test_ac2_classification_works_with_a_conspicuous_fake_key(self, monkeypatch):
        # ← AC2
        monkeypatch.setenv("OPENROUTER_API_KEY", DUMMY_API_KEY)
        from app.core.settings import get_settings

        get_settings.cache_clear()
        try:
            _stub_gateway(monkeypatch, _status_handler(401, message="invalid credentials"))

            with pytest.raises(LlmAuthError):
                llm_service.chat("Roll a d20.")
        finally:
            get_settings.cache_clear()

    def test_ac2_a_non_retryable_trigger_never_touches_a_real_socket_and_asks_once(
        self, monkeypatch
    ):
        # ← AC2 -- collectively proved by every test above never tripping
        # `_block_real_network`; this test makes the guard itself explicit.
        # 401 -> LlmAuthError is not one of sprint 03's four retryable
        # classes (← AC3), so the stub sees exactly the one request a
        # single, non-retried trigger implies.
        called = {"count": 0}

        def handler(request):
            called["count"] += 1
            return httpx.Response(401, json={"error": {"code": 401, "message": "no key"}})

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmAuthError):
            llm_service.chat("Roll a d20.")

        assert called["count"] == 1

    def test_ac2_a_retryable_trigger_never_touches_a_real_socket_and_asks_the_full_budget(
        self, monkeypatch
    ):
        # ← AC2 -- same guard, but for one of sprint 03's four retryable
        # classes (← D6): 429 -> LlmRateLimitError is retried internally by
        # `chat()` (`app.core.llm.retry`), so the stub sees one request per
        # attempt, up to the configured total (`llm_retry_attempts`,
        # default 3 -- one try plus two retries), not just one. Asserted
        # against the real setting rather than a bare literal, so this
        # keeps meaning what it says if the default ever changes.
        called = {"count": 0}

        def handler(request):
            called["count"] += 1
            return httpx.Response(429, json={"error": {"code": 429, "message": "slow down"}})

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmRateLimitError):
            llm_service.chat("Roll a d20.")

        assert called["count"] == get_settings().llm_retry_attempts
