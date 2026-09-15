"""Sprint 03 WI3 — `app/core/llm/retry.py`: budget, delay and logging for
`call_with_retry`/`stream_with_retry` (← research.md Interfaces, I3).

Unit-level coverage of the loop's own decisions (budget computation, delay
formula, tolerant attribute reads, logging) in isolation from any real
network call or `classify()` dispatch table - `classify()` is never called
from this module, so every case here hands the loop an already-built
`LlmError`. `retry._sleep`/`retry._random` are monkeypatched throughout so
this suite never actually sleeps (← AC5's injection points).

Not one of the qa-owned filenames (`test_retry.py` / `test_errors.py` /
`test_service.py` / `test_commands.py`) - qa drives the loop black-box,
through the real CLI and a scripted `httpx.MockTransport`; this file drives
`retry.py` directly.
"""

import re

import pytest

from app.core.llm import retry as llm_retry
from app.core.llm.errors import LlmAuthError, LlmError, LlmMalformedError, LlmUnavailableError

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strips the `ConsoleRenderer`'s ANSI colour codes, which otherwise sit
    adjacent to digits and defeat a `\\b` word-boundary match."""
    return _ANSI_ESCAPE.sub("", text)


class _StubSettings:
    def __init__(self, *, llm_retry_attempts=3, llm_retry_backoff_seconds=0.5):
        self.llm_retry_attempts = llm_retry_attempts
        self.llm_retry_backoff_seconds = llm_retry_backoff_seconds


class _ForgetfulError(LlmError):
    """A subclass that forgets to set `code`/`retryable`, same as WI2's
    `LlmConfigurationError` would without its own overrides - the read at
    this call site must degrade, never raise `AttributeError`."""


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm_retry, "_sleep", lambda seconds: None)


@pytest.fixture
def stub_settings(monkeypatch):
    def _apply(*, attempts=3, backoff=0.5):
        settings = _StubSettings(llm_retry_attempts=attempts, llm_retry_backoff_seconds=backoff)
        monkeypatch.setattr(llm_retry, "get_settings", lambda: settings)
        return settings

    return _apply


def _operation(*, fail_times, error_factory):
    """Returns a zero-arg callable that raises `error_factory()` for the
    first `fail_times` calls, then returns the call count."""
    calls = {"count": 0}

    def _call():
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise error_factory()
        return calls["count"]

    _call.calls = calls
    return _call


def test_call_with_retry_attempts_a_non_retryable_error_exactly_once(stub_settings):
    stub_settings(attempts=3)
    op = _operation(fail_times=99, error_factory=LlmAuthError)

    with pytest.raises(LlmAuthError):
        llm_retry.call_with_retry(op, label="chat")

    assert op.calls["count"] == 1


def test_call_with_retry_retries_a_retryable_error_up_to_the_configured_budget(stub_settings):
    stub_settings(attempts=3)
    op = _operation(fail_times=2, error_factory=LlmUnavailableError)

    result = llm_retry.call_with_retry(op, label="chat")

    assert result == 3
    assert op.calls["count"] == 3


def test_call_with_retry_reraises_the_last_error_unchanged_once_the_budget_is_spent(
    stub_settings,
):
    stub_settings(attempts=3)
    errors = [
        LlmUnavailableError("first"),
        LlmUnavailableError("second"),
        LlmUnavailableError("third"),
    ]

    def _factory():
        return errors[min(len(errors) - 1, op.calls["count"])]

    op = _operation(fail_times=99, error_factory=_factory)

    with pytest.raises(LlmUnavailableError) as excinfo:
        llm_retry.call_with_retry(op, label="chat")

    assert op.calls["count"] == 3
    assert excinfo.value is errors[2]


def test_call_with_retry_caps_a_malformed_error_at_two_attempts_even_with_a_larger_budget(
    stub_settings,
):
    stub_settings(attempts=5)
    op = _operation(fail_times=99, error_factory=LlmMalformedError)

    with pytest.raises(LlmMalformedError):
        llm_retry.call_with_retry(op, label="chat")

    assert op.calls["count"] == 2


def test_call_with_retry_never_exceeds_a_configured_budget_below_the_malformed_cap(
    stub_settings,
):
    stub_settings(attempts=1)
    op = _operation(fail_times=99, error_factory=LlmMalformedError)

    with pytest.raises(LlmMalformedError):
        llm_retry.call_with_retry(op, label="chat")

    assert op.calls["count"] == 1


def test_call_with_retry_degrades_a_forgetful_error_subclass_to_non_retryable(stub_settings):
    stub_settings(attempts=3)
    op = _operation(fail_times=99, error_factory=_ForgetfulError)

    with pytest.raises(_ForgetfulError):
        llm_retry.call_with_retry(op, label="chat")

    assert op.calls["count"] == 1


def test_call_with_retry_honours_retry_after_over_backoff_and_clamps_it(stub_settings, monkeypatch):
    stub_settings(attempts=2, backoff=10.0)
    sleeps = []
    monkeypatch.setattr(llm_retry, "_sleep", lambda seconds: sleeps.append(seconds))
    op = _operation(
        fail_times=1,
        error_factory=lambda: LlmUnavailableError(retry_after_seconds=99.0),
    )

    llm_retry.call_with_retry(op, label="chat")

    assert sleeps == [llm_retry.MAX_RETRY_AFTER_SECONDS]


def test_call_with_retry_backoff_formula_uses_configured_base_and_jitter(
    stub_settings, monkeypatch
):
    stub_settings(attempts=3, backoff=1.0)
    monkeypatch.setattr(llm_retry, "_random", lambda: 0.0)
    sleeps = []
    monkeypatch.setattr(llm_retry, "_sleep", lambda seconds: sleeps.append(seconds))
    op = _operation(fail_times=2, error_factory=LlmUnavailableError)

    llm_retry.call_with_retry(op, label="chat")

    # attempt 1 fails: base * 2**0 * 0.5 = 0.5; attempt 2 fails: base * 2**1 * 0.5 = 1.0
    assert sleeps == [0.5, 1.0]


def test_call_with_retry_logs_each_attempt_and_the_exhaustion(stub_settings, capsys):
    import structlog

    from app.core.logging import configure_logging

    configure_logging()
    try:
        stub_settings(attempts=2)
        op = _operation(fail_times=99, error_factory=LlmUnavailableError)

        with pytest.raises(LlmUnavailableError):
            llm_retry.call_with_retry(op, label="chat")
    finally:
        structlog.reset_defaults()

    output = _plain(capsys.readouterr().err)
    attempt_lines = [line for line in output.splitlines() if "llm_retry_attempt" in line]
    assert len(attempt_lines) == 2
    for index, line in enumerate(attempt_lines, start=1):
        assert re.search(rf"\b{index}\b", line), f"expected attempt {index} in: {line!r}"
        assert "chat" in line
        assert "LLM_UNAVAILABLE" in line
    assert output.count("llm_retry_exhausted") == 1


def test_stream_with_retry_retries_only_before_the_first_item(stub_settings):
    stub_settings(attempts=3)
    open_calls = {"count": 0}

    def _open_stream():
        open_calls["count"] += 1
        if open_calls["count"] == 1:
            raise LlmUnavailableError()
        return iter(["first", "second"])

    result = list(llm_retry.stream_with_retry(_open_stream, label="chat_stream"))

    assert result == ["first", "second"]
    assert open_calls["count"] == 2


def test_stream_with_retry_never_retries_a_mid_stream_failure(stub_settings):
    stub_settings(attempts=3)
    open_calls = {"count": 0}

    def _bad_rest():
        yield "first"
        raise LlmUnavailableError()

    def _open_stream():
        open_calls["count"] += 1
        return _bad_rest()

    stream = llm_retry.stream_with_retry(_open_stream, label="chat_stream")

    assert next(stream) == "first"
    with pytest.raises(LlmUnavailableError):
        next(stream)
    assert open_calls["count"] == 1


def test_stream_with_retry_gives_up_a_non_retryable_error_after_one_attempt(stub_settings):
    stub_settings(attempts=3)
    open_calls = {"count": 0}

    def _open_stream():
        open_calls["count"] += 1
        raise LlmAuthError()

    with pytest.raises(LlmAuthError):
        next(llm_retry.stream_with_retry(_open_stream, label="chat_stream"))

    assert open_calls["count"] == 1
