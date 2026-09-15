"""Sprint 02 WI2 — `app/core/llm/errors.py`: eight failure classes,
`classify()` and `raise_for_finish_reason()` (← research.md Interfaces,
`core/llm/errors.py`).

qa owns `test_errors.py`; this file is this work item's own unit coverage
for the classification table and the redaction/finish-reason helpers, which
qa's acceptance tests do not need to re-derive.
"""

import httpx
import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from pydantic import BaseModel
from pydantic_core import ValidationError

from app.core.errors import ErrorCode
from app.core.llm import errors as llm_errors
from app.core.llm.errors import (
    LlmAuthError,
    LlmBadRequestError,
    LlmBudgetError,
    LlmConfigurationError,
    LlmMalformedError,
    LlmRateLimitError,
    LlmRefusedError,
    LlmTimeoutError,
    LlmUnavailableError,
    classify,
    raise_for_finish_reason,
)


def _raw_response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers,
        request=httpx.Request("POST", "https://openrouter.ai/x"),
    )


def _fake_open_router_error(
    status_code: int, message: str = "boom", headers: dict[str, str] | None = None
):
    """A real `openrouter.errors.OpenRouterError` with an arbitrary status
    code, so `classify()` must dispatch on `.status_code` alone - never on
    which concrete SDK subclass it is (the SDK has many, and degrades to
    `OpenRouterDefaultError` on a non-JSON body)."""
    from openrouter.errors import OpenRouterError

    return OpenRouterError(message, _raw_response(status_code, headers))


class TestSubclassAttributes:
    @pytest.mark.parametrize(
        ("cls", "code", "retryable"),
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
    def test_ac5_code_and_retryable(self, cls, code, retryable):
        # ← AC5
        exc = cls()
        assert exc.code is code
        assert exc.retryable is retryable

    def test_str_is_always_the_generic_message_not_the_provider_text(self):
        # ← D2
        exc = LlmAuthError("some very specific provider text")
        assert str(exc) == llm_errors.LLM_FAILURE_MESSAGE
        assert exc.provider_message == "some very specific provider text"

    def test_provider_message_defaults_to_none(self):
        exc = LlmTimeoutError()
        assert exc.provider_message is None


class TestLlmConfigurationErrorUnchanged:
    def test_still_names_the_env_var_and_has_no_code_attribute(self):
        exc = LlmConfigurationError()
        assert "OPENROUTER_API_KEY" in str(exc)
        assert not hasattr(exc, "code")


class TestClassify:
    def test_llm_error_passed_in_comes_back_as_is(self):
        original = LlmAuthError("x")
        assert classify(original) is original

    def test_foreign_exception_returns_none(self):
        assert classify(ValueError("not ours")) is None

    @pytest.mark.parametrize(
        ("status_code", "expected_cls"),
        [
            (400, LlmBadRequestError),
            (404, LlmBadRequestError),
            (413, LlmBadRequestError),
            (422, LlmBadRequestError),
            (401, LlmAuthError),
            (402, LlmBudgetError),
            (403, LlmRefusedError),
            (408, LlmTimeoutError),
            (524, LlmTimeoutError),
            (429, LlmRateLimitError),
            (500, LlmUnavailableError),
            (502, LlmUnavailableError),
            (503, LlmUnavailableError),
            (529, LlmUnavailableError),
            (200, LlmMalformedError),
            (418, LlmBadRequestError),
            (599, LlmUnavailableError),
        ],
    )
    def test_openrouter_error_classified_by_status_code(self, status_code, expected_cls):
        exc = classify(_fake_open_router_error(status_code, message="provider said no"))
        assert isinstance(exc, expected_cls)
        assert exc.provider_message == "provider said no"

    def test_httpx_timeout_exception_classified_as_timeout(self):
        exc = classify(httpx.TimeoutException("timed out"))
        assert isinstance(exc, LlmTimeoutError)
        assert exc.provider_message is None

    def test_httpx_connect_error_classified_as_unavailable(self):
        exc = classify(httpx.ConnectError("no connection"))
        assert isinstance(exc, LlmUnavailableError)
        assert exc.provider_message is None

    def test_no_response_error_classified_as_unavailable(self):
        class _FakeNoResponseError(Exception):
            def __init__(self):
                self.message = ""
                super().__init__()

        # classify() only needs to recognise the type by name per the
        # binding interface; import the real one to be sure it matches.
        from openrouter.errors import NoResponseError

        exc = classify(NoResponseError())
        assert isinstance(exc, LlmUnavailableError)

    def test_pydantic_validation_error_classified_as_malformed(self):
        class _Model(BaseModel):
            n: int

        try:
            _Model(n="not an int")
        except ValidationError as err:
            exc = classify(err)

        assert isinstance(exc, LlmMalformedError)

    def test_output_parser_exception_classified_as_malformed(self):
        exc = classify(OutputParserException("could not parse"))
        assert isinstance(exc, LlmMalformedError)


class TestProviderMessageRedaction:
    def test_configured_api_key_is_blanked_out_of_provider_message(self, monkeypatch):
        from app.core.settings import get_settings

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-super-secret-123")
        get_settings.cache_clear()
        try:
            exc = classify(
                _fake_open_router_error(500, message="body echoed sk-super-secret-123 back")
            )
        finally:
            get_settings.cache_clear()

        assert "sk-super-secret-123" not in exc.provider_message

    def test_blank_configured_key_does_not_blank_the_whole_message(self, monkeypatch):
        from app.core.settings import get_settings

        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        get_settings.cache_clear()
        try:
            exc = classify(_fake_open_router_error(500, message="a perfectly normal message"))
        finally:
            get_settings.cache_clear()

        assert exc.provider_message == "a perfectly normal message"

    def test_provider_message_is_truncated_to_500_chars(self):
        exc = classify(_fake_open_router_error(500, message="x" * 600))
        assert len(exc.provider_message) == 500

    def test_blank_message_becomes_none(self):
        exc = classify(_fake_open_router_error(500, message=""))
        assert exc.provider_message is None


class TestRaiseForFinishReason:
    def test_content_filter_raises_refused(self):
        message = AIMessage(content="x", response_metadata={"finish_reason": "content_filter"})
        with pytest.raises(LlmRefusedError):
            raise_for_finish_reason(message)

    def test_error_raises_unavailable(self):
        message = AIMessage(content="x", response_metadata={"finish_reason": "error"})
        with pytest.raises(LlmUnavailableError):
            raise_for_finish_reason(message)

    def test_stop_returns_quietly(self):
        message = AIMessage(content="x", response_metadata={"finish_reason": "stop"})
        raise_for_finish_reason(message)

    def test_missing_finish_reason_returns_quietly(self):
        message = AIMessage(content="x", response_metadata={})
        raise_for_finish_reason(message)


class TestLlmConfigurationErrorIsSafelyNonRetryable:
    def test_retryable_is_false_and_retry_after_is_none(self):
        # sprint 03: the one error raised before any network call must
        # never crash the question a retry loop asks first.
        exc = LlmConfigurationError()
        assert exc.retryable is False
        assert exc.retry_after_seconds is None


class TestRetryAfterSeconds:
    def test_defaults_to_none_when_not_supplied(self):
        exc = LlmAuthError("x")
        assert exc.retry_after_seconds is None

    def test_stored_when_supplied_as_keyword(self):
        exc = LlmAuthError("x", retry_after_seconds=7.0)
        assert exc.retry_after_seconds == 7.0

    def test_provider_message_stays_positional_and_first(self):
        # call sites elsewhere in the codebase construct these classes with
        # a single positional argument - that must keep compiling.
        exc = LlmAuthError("just the message")
        assert exc.provider_message == "just the message"
        assert exc.retry_after_seconds is None

    def test_classify_recovers_numeric_retry_after_header_from_openrouter_error(self):
        exc = classify(_fake_open_router_error(502, headers={"retry-after": "7"}))
        assert exc.retry_after_seconds == 7.0

    def test_classify_leaves_retry_after_none_when_header_is_absent(self):
        exc = classify(_fake_open_router_error(502))
        assert exc.retry_after_seconds is None

    def test_classify_leaves_retry_after_none_when_header_is_an_http_date(self):
        exc = classify(
            _fake_open_router_error(503, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
        )
        assert exc.retry_after_seconds is None

    def test_client_side_exceptions_never_carry_a_retry_after(self):
        assert classify(httpx.TimeoutException("timed out")).retry_after_seconds is None
        assert classify(httpx.ConnectError("no connection")).retry_after_seconds is None

        class _Model(BaseModel):
            n: int

        try:
            _Model(n="not an int")
        except ValidationError as err:
            exc = classify(err)
        assert exc.retry_after_seconds is None


class TestRetryAfterOfHelper:
    """`_retry_after_of` is the parsing helper `classify()` uses on the
    `OpenRouterError` branch; exercised directly here so every failure mode
    - missing attribute, `None` object, missing key, unparseable value - is
    proven never to raise, not just the two the `classify()` path reaches."""

    def test_missing_headers_attribute_returns_none(self):
        class _NoHeaders:
            pass

        assert llm_errors._retry_after_of(_NoHeaders()) is None

    def test_none_headers_returns_none(self):
        class _NullHeaders:
            headers = None

        assert llm_errors._retry_after_of(_NullHeaders()) is None

    def test_headers_without_retry_after_key_returns_none(self):
        class _EmptyHeaders:
            headers = httpx.Headers({})

        assert llm_errors._retry_after_of(_EmptyHeaders()) is None

    def test_non_numeric_value_returns_none(self):
        class _JunkHeaders:
            headers = httpx.Headers({"retry-after": "not-a-number"})

        assert llm_errors._retry_after_of(_JunkHeaders()) is None

    def test_numeric_string_is_parsed_to_float(self):
        class _NumericHeaders:
            headers = httpx.Headers({"retry-after": "12"})

        assert llm_errors._retry_after_of(_NumericHeaders()) == 12.0
