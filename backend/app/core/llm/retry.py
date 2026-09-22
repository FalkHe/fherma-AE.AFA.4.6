"""The retry loop the LLM seam runs on top of `classify()`'s output.

`call_with_retry`/`stream_with_retry` never call `classify()` themselves -
`service.chat()`/`chat_stream()` already turn every provider failure into an
`LlmError` before this module sees it (← sprint 02). This module only
decides *how many times* and *how long to wait*, then re-raises the last
`LlmError` unchanged so `commands.py` still prints exactly one generic line
regardless of how many attempts happened underneath (← D2, D6).

Budget, recomputed on every failure since the failing class can change
attempt to attempt: 1 for a non-retryable error; `LLM_MALFORMED` caps at
`MALFORMED_MAX_ATTEMPTS` (2 - "once", never above the configured budget);
everything else retryable gets `get_settings().llm_retry_attempts`, which
counts *total* attempts including the first.

`err.code`/`err.retryable`/`err.retry_after_seconds` are read tolerantly
(`getattr` with a default), never accessed directly: `LlmError` deliberately
leaves `code`/`retryable` as bare annotations with no default (← sprint 02's
`errors.py`), so a future subclass that forgets to set one must degrade to
"not retryable" here rather than crash the loop with `AttributeError`.

`acall_with_retry()` (sprint 010-02) is the async twin of `call_with_retry()`
for callers that must await the model (`service.ainvoke_chat()`). Both share
one decision function, `_decide_retry()`, for budget, backoff and logging -
only the actual wait differs: `call_with_retry()` blocks on `_sleep()`,
`acall_with_retry()` awaits `_asleep()`. Neither `stream_with_retry()` nor
its streaming shape gets an async twin - nothing here needed one.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Iterator

import structlog

from app.core.errors import ErrorCode
from app.core.llm.errors import LlmError
from app.core.settings import get_settings

logger = structlog.get_logger()

MALFORMED_MAX_ATTEMPTS = 2
MAX_RETRY_AFTER_SECONDS = 30.0


def _sleep(seconds: float) -> None:
    """Wraps `time.sleep` - the sync AC5 injection point; tests monkeypatch
    `retry._sleep` so the suite never actually sleeps."""
    time.sleep(seconds)


async def _asleep(seconds: float) -> None:
    """Wraps `asyncio.sleep` - the async AC5 injection point; tests
    monkeypatch `retry._asleep` so the async suite never actually sleeps."""
    await asyncio.sleep(seconds)


def _random() -> float:
    """Wraps `random.random` - the jitter injection point for tests."""
    return random.random()


def _code_of(err: LlmError) -> str:
    code = getattr(err, "code", None)
    return code.value if isinstance(code, ErrorCode) else "LLM_CONFIGURATION"


def _budget_of(err: LlmError, *, configured_attempts: int) -> int:
    if not getattr(err, "retryable", False):
        return 1
    if getattr(err, "code", None) == ErrorCode.LLM_MALFORMED:
        return min(configured_attempts, MALFORMED_MAX_ATTEMPTS)
    return configured_attempts


def _delay_before_next(err: LlmError, attempt: int, *, backoff_base: float) -> float:
    retry_after = getattr(err, "retry_after_seconds", None)
    if retry_after is not None:
        return min(retry_after, MAX_RETRY_AFTER_SECONDS)
    computed = backoff_base * 2 ** (attempt - 1) * (0.5 + 0.5 * _random())
    # `LLM_RETRY_BACKOFF_SECONDS` and `llm_retry_attempts` are both
    # operator-configurable, so the exponent is not bounded either - without
    # this clamp a high configured base could reproduce the multi-minute
    # hang this sprint exists to prevent. Same ceiling a provider-supplied
    # `Retry-After` gets above: the promise to the player is "no single
    # retry wait exceeds MAX_RETRY_AFTER_SECONDS", regardless of source.
    return min(computed, MAX_RETRY_AFTER_SECONDS)


def _decide_retry(err: LlmError, *, label: str, attempt: int) -> float | None:
    """Logs `llm_retry_attempt` (and `llm_retry_exhausted` when the budget is
    spent) for one failed attempt. Returns the delay to wait before the next
    attempt, or `None` when the budget is spent and the caller should stop.

    Single-sourced between the sync and async retry loops: neither one
    computes budget/backoff or logs on its own, so the two paths can never
    drift apart. Waiting out the returned delay (`_sleep()` vs. `_asleep()`)
    is the only thing left to the caller.
    """
    settings = get_settings()
    max_attempts = _budget_of(err, configured_attempts=settings.llm_retry_attempts)
    retrying = attempt < max_attempts
    delay = (
        _delay_before_next(err, attempt, backoff_base=settings.llm_retry_backoff_seconds)
        if retrying
        else None
    )

    logger.info(
        "llm_retry_attempt",
        operation=label,
        attempt=attempt,
        max_attempts=max_attempts,
        code=_code_of(err),
        retrying=retrying,
        delay_seconds=None if delay is None else round(delay, 3),
    )

    if not retrying:
        logger.warning(
            "llm_retry_exhausted",
            operation=label,
            attempt=attempt,
            max_attempts=max_attempts,
            code=_code_of(err),
        )

    return delay


def _log_attempt_and_should_retry(err: LlmError, *, label: str, attempt: int) -> bool:
    """Sync wrapper over `_decide_retry()`: sleeps out the delay via
    `_sleep()` and returns whether the caller should retry."""
    delay = _decide_retry(err, label=label, attempt=attempt)
    if delay is None:
        return False
    _sleep(delay)
    return True


async def _adecide_and_wait(err: LlmError, *, label: str, attempt: int) -> bool:
    """Async wrapper over `_decide_retry()`: awaits `_asleep()` for the
    delay and returns whether the caller should retry."""
    delay = _decide_retry(err, label=label, attempt=attempt)
    if delay is None:
        return False
    await _asleep(delay)
    return True


def call_with_retry[T](operation: Callable[[], T], *, label: str) -> T:
    """Run `operation()`, retrying on `LlmError` per the budget above.

    `operation` must rebuild anything attempt-specific itself (the caller's
    `chat_model()` call, in particular) so a config error still raises on
    attempt 1 and is never retried. The last `LlmError` re-raises unchanged
    once the budget is spent.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return operation()
        except LlmError as err:
            if not _log_attempt_and_should_retry(err, label=label, attempt=attempt):
                raise


async def acall_with_retry[T](operation: Callable[[], Awaitable[T]], *, label: str) -> T:
    """Async twin of `call_with_retry()`, for a caller that must await the
    model (`service.ainvoke_chat()`). Same budget, backoff, clamp and log
    events - see `_decide_retry()`, the function both share - awaiting
    `_asleep()` instead of blocking on `_sleep()`. The last `LlmError`
    re-raises unchanged once the budget is spent.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await operation()
        except LlmError as err:
            if not await _adecide_and_wait(err, label=label, attempt=attempt):
                raise


def stream_with_retry[T](open_stream: Callable[[], Iterator[T]], *, label: str) -> Iterator[T]:
    """Open a stream via `open_stream()`, retrying only until the first item
    is yielded.

    Limitation, by design: once the first item has been yielded the rest of
    the stream is passed through untouched, never retried. A mid-stream
    `finish_reason == "error"` (surfaced by `raise_for_finish_reason` as a
    retryable `LlmUnavailableError`, after partial text has already been
    printed) is therefore never retried despite being marked retryable -
    replaying it would mean re-emitting already-printed narration, which
    would contradict AC1's "no failure line" by visibly duplicating output.
    Retrying is only meaningful while nothing has reached the player yet.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            stream = open_stream()
            first = next(stream)
        except LlmError as err:
            if not _log_attempt_and_should_retry(err, label=label, attempt=attempt):
                raise
            continue
        else:
            break

    yield first
    yield from stream
