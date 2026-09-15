"""qa acceptance tests — sprint 001/03: a transient LLM failure is retried
with backoff, invisibly, before the player is ever told anything failed
(AC1, AC2, AC3, AC4, AC5).

Black-box: every test drives `app.core.llm.retry.call_with_retry` /
`stream_with_retry` directly with a scripted `operation` / `open_stream`
callable — the module's own two public entry points, named as the binding
interface for this sprint. Sprint 02's `test_errors.py` already proves the
seam turns a real provider failure into an `LlmError` subclass; this file
proves what the retry loop built on top of that classification does, so no
test here needs a fabricated HTTP transport — a scripted callable that
raises the already-classified `LlmError` is the correct unit of black-box
input at this seam.

`retry._sleep` is monkeypatched in every test (`sleep_calls` fixture) so
nothing in this file ever waits on wall-clock time (← AC5); one test also
replaces the real `time.sleep` with a bomb, to catch a retry loop that
bypassed the injectable seam entirely.
"""

import re
import time

import pytest
import structlog

from app.core.llm import retry as retry_module
from app.core.llm.errors import (
    LlmAuthError,
    LlmMalformedError,
    LlmRateLimitError,
    LlmUnavailableError,
)
from app.core.settings import get_settings

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strips the `ConsoleRenderer`'s ANSI colour codes, which otherwise
    sit adjacent to digits and defeat a `\\b` word-boundary match (a colour
    code ends in a word character, e.g. `...35m1...`)."""
    return _ANSI_ESCAPE.sub("", text)


@pytest.fixture
def sleep_calls(monkeypatch):
    """The AC5 injection point: records the delay each retry asks for
    without ever actually waiting it out."""
    calls: list[float] = []
    monkeypatch.setattr(retry_module, "_sleep", lambda seconds: calls.append(seconds))
    return calls


@pytest.fixture
def configure_retry(monkeypatch):
    """Sets `llm_retry_attempts` / `llm_retry_backoff_seconds` for one test
    via the real `Settings` object (not a fake), clearing the process-wide
    `lru_cache` on the way in and out so the override never leaks."""

    def _configure(*, attempts=None, backoff=None):
        if attempts is not None:
            monkeypatch.setenv("LLM_RETRY_ATTEMPTS", str(attempts))
        if backoff is not None:
            monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", str(backoff))
        get_settings.cache_clear()

    yield _configure
    get_settings.cache_clear()


@pytest.fixture
def configured_logging():
    """Only restores structlog's global defaults on the way out, so one
    AC4 test's configuration can never leak into the next one. The actual
    `configure_logging()` call must happen inside each test's own body, not
    here: `capsys` swaps in a fresh buffer between fixture *setup* and the
    test's *call* phase, so binding structlog's `PrintLoggerFactory` to
    `sys.stderr` during fixture setup captures a buffer that is already
    stale (and closed) by the time the test body runs -- `configure_logging`
    must be called after `capsys` is really in its call-phase buffer, i.e.
    from inside the test itself (mirrors `test_error_envelope.py`)."""
    yield
    structlog.reset_defaults()


class TestAC1RetriedThenSucceeds:
    """A retryable failure, retried enough times within the budget, is
    invisible to the caller: the eventual success comes back normally
    (← AC1)."""

    def test_ac1_call_with_retry_returns_the_eventual_success(self, sleep_calls):
        # ← AC1
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise LlmUnavailableError()
            return "the answer"

        result = retry_module.call_with_retry(operation, label="chat")

        assert result == "the answer"
        assert attempts["count"] == 3

    def test_ac1_stream_with_retry_yields_the_eventual_chunks(self, sleep_calls):
        # ← AC1: the failure fires before the first chunk is produced — the
        # documented point at which a stream is retried at all.
        attempts = {"count": 0}

        def open_stream():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise LlmUnavailableError()
            return iter(["chunk-1", "chunk-2"])

        result = list(retry_module.stream_with_retry(open_stream, label="chat_stream"))

        assert result == ["chunk-1", "chunk-2"]
        assert attempts["count"] == 3


class TestAC2ExhaustsTheConfiguredBudget:
    """A failure that never clears is retried up to the configured total
    attempt count, then re-raised (← AC2)."""

    def test_ac2_call_with_retry_raises_after_the_configured_attempts(
        self, sleep_calls, configure_retry
    ):
        # ← AC2
        configure_retry(attempts=3)
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            raise LlmUnavailableError()

        with pytest.raises(LlmUnavailableError):
            retry_module.call_with_retry(operation, label="chat")

        assert attempts["count"] == 3

    def test_ac2_stream_with_retry_raises_after_the_configured_attempts(
        self, sleep_calls, configure_retry
    ):
        # ← AC2
        configure_retry(attempts=2)
        attempts = {"count": 0}

        def open_stream():
            attempts["count"] += 1
            raise LlmUnavailableError()

        with pytest.raises(LlmUnavailableError):
            list(retry_module.stream_with_retry(open_stream, label="chat_stream"))

        assert attempts["count"] == 2


class TestAC3NonRetryableAttemptedOnce:
    """A non-retryable class (`LLM_AUTH`) is attempted exactly once, no
    matter how large the configured budget is (← AC3)."""

    def test_ac3_call_with_retry_never_retries_a_non_retryable_class(
        self, sleep_calls, configure_retry
    ):
        # ← AC3
        configure_retry(attempts=5)
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            raise LlmAuthError()

        with pytest.raises(LlmAuthError):
            retry_module.call_with_retry(operation, label="chat")

        assert attempts["count"] == 1
        assert sleep_calls == []

    def test_ac3_stream_with_retry_never_retries_a_non_retryable_class(
        self, sleep_calls, configure_retry
    ):
        # ← AC3
        configure_retry(attempts=5)
        attempts = {"count": 0}

        def open_stream():
            attempts["count"] += 1
            raise LlmAuthError()

        with pytest.raises(LlmAuthError):
            list(retry_module.stream_with_retry(open_stream, label="chat_stream"))

        assert attempts["count"] == 1
        assert sleep_calls == []


class TestAC4EveryAttemptIsLogged:
    """Every failed attempt logs `llm_retry_attempt` with its attempt
    number and the failure class being retried; exhaustion logs
    `llm_retry_exhausted` (← AC4)."""

    def test_ac4_each_failed_attempt_logs_its_number_and_failure_class(
        self, sleep_calls, capsys, configured_logging
    ):
        # ← AC4
        from app.core.logging import configure_logging

        configure_logging()
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise LlmUnavailableError()
            return "ok"

        retry_module.call_with_retry(operation, label="chat")

        err = _plain(capsys.readouterr().err)
        attempt_lines = [line for line in err.splitlines() if "llm_retry_attempt" in line]
        assert len(attempt_lines) == 2
        for index, line in enumerate(attempt_lines, start=1):
            assert re.search(rf"\b{index}\b", line), f"expected attempt {index} in: {line!r}"
            assert "LLM_UNAVAILABLE" in line
        assert "llm_retry_exhausted" not in err

    def test_ac4_exhaustion_is_logged_once_after_the_last_attempt(
        self, sleep_calls, capsys, configured_logging
    ):
        # ← AC4
        from app.core.logging import configure_logging

        configure_logging()

        def operation():
            raise LlmUnavailableError()

        with pytest.raises(LlmUnavailableError):
            retry_module.call_with_retry(operation, label="chat")

        err = capsys.readouterr().err
        assert err.count("llm_retry_exhausted") == 1
        assert err.count("llm_retry_attempt") == get_settings().llm_retry_attempts


class TestAC5NoSleepingRetryAfterWinsBackoffIsBounded:
    """The suite never pays for a real sleep; a `Retry-After`-style delay
    on the raised error wins over the computed backoff, capped at
    `MAX_RETRY_AFTER_SECONDS`; the computed backoff itself stays within
    that same cap (← AC5)."""

    def test_ac5_the_suite_never_reaches_a_real_time_sleep(self, monkeypatch, sleep_calls):
        # ← AC5: even the backoff-computing internals must go through the
        # injectable `_sleep` seam, never straight to `time.sleep`.
        def _forbidden(seconds):
            raise AssertionError("a real time.sleep was attempted")

        monkeypatch.setattr(time, "sleep", _forbidden)
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise LlmUnavailableError()
            return "ok"

        result = retry_module.call_with_retry(operation, label="chat")

        assert result == "ok"
        assert len(sleep_calls) == 2

    def test_ac5_retry_after_seconds_wins_over_the_computed_delay(
        self, sleep_calls, configure_retry
    ):
        # ← AC5
        configure_retry(attempts=3, backoff=999.0)  # would dominate if it were used instead
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise LlmRateLimitError(retry_after_seconds=5.0)
            return "ok"

        retry_module.call_with_retry(operation, label="chat")

        assert sleep_calls == [5.0]

    def test_ac5_retry_after_seconds_is_capped_at_the_module_constant(
        self, sleep_calls, configure_retry
    ):
        # ← AC5
        configure_retry(attempts=3)
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] < 2:
                raise LlmRateLimitError(retry_after_seconds=1000.0)
            return "ok"

        retry_module.call_with_retry(operation, label="chat")

        assert sleep_calls == [retry_module.MAX_RETRY_AFTER_SECONDS]

    def test_ac5_computed_backoff_delays_grow_and_stay_within_the_cap(
        self, sleep_calls, configure_retry, monkeypatch
    ):
        # ← AC5: no `Retry-After` this time, so the delays are the computed
        # exponential-with-jitter backoff. The exact jitter formula is an
        # implementation detail (brief.md, Assumptions: "exponential with
        # jitter"), not a decision this suite can pin down — what the
        # criterion actually promises is that the seam is `_random` (so a
        # test can remove the randomness), that nothing here ever really
        # sleeps, and that every delay obeys the same cap a Retry-After
        # value does.
        monkeypatch.setattr(retry_module, "_random", lambda: 0.0)
        configure_retry(attempts=4, backoff=1.0)

        def operation():
            raise LlmUnavailableError()

        with pytest.raises(LlmUnavailableError):
            retry_module.call_with_retry(operation, label="chat")

        assert len(sleep_calls) == 3
        assert all(0 <= delay <= retry_module.MAX_RETRY_AFTER_SECONDS for delay in sleep_calls)
        assert sleep_calls == sorted(sleep_calls)

    def test_ac5_malformed_failures_use_their_own_smaller_attempt_budget(
        self, sleep_calls, configure_retry
    ):
        # ← AC5 / brief.md Assumptions: "LLM_MALFORMED is retried once; the
        # other retryable classes use the full attempt budget" — proved via
        # the named module constant, not a hard-coded "2".
        configure_retry(attempts=5)
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            raise LlmMalformedError()

        with pytest.raises(LlmMalformedError):
            retry_module.call_with_retry(operation, label="chat")

        assert attempts["count"] == retry_module.MALFORMED_MAX_ATTEMPTS
