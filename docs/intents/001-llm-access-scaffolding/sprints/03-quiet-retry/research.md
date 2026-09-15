---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: sprint 001/03 — transient failures are retried before anyone is told

## Facts

Executed in `app-cli` 2026-09-15 vs. `httpx.MockTransport` 502 — `langchain-openrouter` 0.2.8 · `openrouter` 0.10.8 · `langchain-core` 1.6.3 · `tenacity` 9.1.4 (local site-packages).

**Three retry layers; exactly one will be live, and it is ours.**
- `ChatOpenRouter.max_retries` (default 2) is read **only** in `_build_client()` (`chat_models.py:457`),
  which `validate_environment` calls only `if not self.client` (`:485`). Sprint 02 passes `client=`
  (`service.py:84`), so it is **dead today**: exactly 1 request at `max_retries` 0, 2 *and* 5. Sprint 01 did
  silently retry (no `client=` ⇒ a ~300 s backoff window); sprint 02 ended that. Nothing to undo — but pass
  `max_retries=0` explicitly, so a later edit dropping `client=` cannot resurrect it silently.
- The SDK's own backoff stays off via `retry_config=None` (`service.py:55`): the 502 surfaced in 0.01 s.
- `langchain-core` retries only through an explicit `.with_retry()`; the seam has none. ⇒ total attempts = what this sprint's loop configures, not a product of three layers.

**`Retry-After` does survive — onto the SDK exception, not onto ours.** The 502 carried
`exc.headers["retry-after"] == "7"` (`httpx.Headers`, also on `exc.raw_response.headers`), but `classify()`
keeps only `provider_message` (`errors.py:169`), losing it. One extra field on `LlmError` recovers it.

**No new dependency.** `tenacity` is transitive via `langchain-core` (`backend/uv.lock:424`), **not** declared
in `backend/pyproject.toml`; adopting it would still need custom `stop`/`wait` callables for the per-class
budget and the `Retry-After` override. Hand-roll (~40 lines).

**`LlmConfigurationError` has no `retryable`.** `LlmError` declares `retryable: bool` as a bare annotation
(`errors.py:52`); `LlmConfigurationError` (`errors.py:59`) sets neither it nor `code`, so `err.retryable`
raises `AttributeError` on the one error raised *before* any network call.

**Streaming.** `chat_stream` (`service.py:121-133`) classifies per `next()` and runs
`raise_for_finish_reason` *after* each chunk is yielded (`:133`) — a failure is either pre-first-chunk
(nothing on screen) or post-output (already printed by `commands.py:30`).

**Logging.** Module-level `logger = structlog.get_logger()` (`core/errors.py:14`), snake_case event +
kwargs (`auth/routes.py:56`), written straight to stderr (`core/logging.py:29`) — assertions call
`configure_logging()` inside the test and read `capsys`, never `caplog` (`tests/auth/test_sign_in.py:86`).
`LOG_LEVEL` defaults to `INFO` (`settings.py:11`); `conftest.py` pins no level, so a DEBUG log is untestable.

## Work items

WI1 ∥ WI2, then WI3, then WI4. All `backend-python`.

- WI1 (AC6) `app/core/settings.py` + `.env.dist` + assertions in `tests/core/test_settings.py`.
- WI2 `app/core/llm/errors.py`: `retryable` on `LlmConfigurationError`, `retry_after_seconds` on `LlmError`.
- WI3 (AC1–AC4) `app/core/llm/retry.py` (new) + wiring in `service.py`.
- WI4 (AC1–AC5) `tests/core/llm/test_retry.py` + a retried-then-succeeds case in `test_commands.py`.

## Interfaces

- **WI1** `llm_retry_attempts: int = 3` (total attempts incl. the first, `ge=1`) and
  `llm_retry_backoff_seconds: float = 0.5` (`ge=0`). `.env.dist` after `CHAT_MODEL`: `LLM_RETRY_ATTEMPTS=3`
  ("How many times a retryable LLM failure is attempted in total, the first try included. 1 disables retry;
  the player sees nothing until the budget is spent.") · `LLM_RETRY_BACKOFF_SECONDS=0.5` ("Base delay:
  attempt n waits base × 2^(n-1), jittered. A `Retry-After` header wins over this."). **`.env.dist` is
  owner-only — the human must re-copy both lines into their `.env`; note it in `progress.md`.**
- **WI2** `LlmError.__init__(self, provider_message: str | None = None, *, retry_after_seconds: float | None
  = None)` storing both (positional arg unchanged ⇒ existing call sites compile). `LlmConfigurationError`
  gains `retryable = False` and `self.retry_after_seconds = None`. New `_retry_after_of(exc) -> float | None`
  = `float()` of `getattr(exc, "headers", None).get("retry-after")`, `None` when absent / an HTTP-date /
  unparseable; `classify()` passes it on the `OpenRouterError` branch only.
- **WI3** `app/core/llm/retry.py` module-level: `MALFORMED_MAX_ATTEMPTS = 2` · `MAX_RETRY_AFTER_SECONDS =
  30.0` · `def _sleep(seconds: float) -> None` (wraps `time.sleep`) · `def _random() -> float` (wraps
  `random.random`) — **the only AC5 injection points; tests monkeypatch `retry._sleep`.** Public:
  `call_with_retry(operation: Callable[[], T], *, label: str) -> T` and
  `stream_with_retry(open_stream: Callable[[], Iterator[T]], *, label: str) -> Iterator[T]`; both callables
  raise `LlmError` already, so retry never calls `classify()` itself.
  - Budget, recomputed per failure: `1` if `not err.retryable`; `min(attempts, MALFORMED_MAX_ATTEMPTS)` for
    `ErrorCode.LLM_MALFORMED` ("once" = 2 attempts total, never above the configured budget); else
    `settings.llm_retry_attempts`.
  - Delay before attempt n+1: `min(err.retry_after_seconds, MAX_RETRY_AFTER_SECONDS)` when present, else
    `base * 2 ** (n - 1) * (0.5 + 0.5 * _random())`.
  - `stream_with_retry` retries **only until the first item is yielded**: it opens the stream and pulls the
    first item inside the retry loop, then passes the rest through untouched. D6's "before the player sees
    anything" is literally satisfiable only while nothing has been emitted, and replaying printed text would
    contradict AC1's "no failure line" with visibly duplicated narration. State the limitation in the
    docstring: a mid-stream `finish_reason == "error"` is **never** retried despite being `retryable`.
  - Every failed attempt logs (AC4) `logger.info("llm_retry_attempt", operation=label, attempt=<1-based>,
    max_attempts=<budget>, code=<`err.code.value`, else `"LLM_CONFIGURATION"`>, retrying=<bool>,
    delay_seconds=<rounded | None>)`; exhaustion adds `logger.warning("llm_retry_exhausted", …)` and
    re-raises the last `LlmError` unchanged, so `commands.py:38` still prints the one generic line.
  - `service.py`: `chat_model()` gains `max_retries=0`; `chat()` wraps its current try/except body in
    `call_with_retry(…, label="chat")`; `chat_stream()` keeps its loop as a nested generator and returns
    `stream_with_retry(_open, label="chat_stream")`. Both rebuild the model per attempt, so
    `LlmConfigurationError` still raises on attempt 1 and is never retried.
- **WI4** AC1/AC2 drive the real CLI with `service.build_sdk_client` monkeypatched to an
  `httpx.MockTransport` scripted 502→502→200, then always-502 (sprint 02's seam, `service.py:51`); AC3 uses
  401; AC4 asserts `capsys` after an in-test `configure_logging()`; AC5 monkeypatches `retry._sleep`.

## Open questions

- **None product-visible — the sprint may start.** D6 fixes the quiet-then-tell behaviour and D2 the line
  that appears afterwards; the brief's assumptions fix the retryable split. Below are my calls, for veto.
- *technical* — `llm_retry_attempts` counts **total attempts**, not retries: `3` = 1 try + 2 retries.
- *technical* — attempts log at `info` on stderr, so an operator running the CLI at the default `LOG_LEVEL`
  does see `llm_retry_attempt` lines. D6's "quiet" is read as the *player* channel: no failure line, exit 0,
  no duplicated narration. `LOG_LEVEL=WARNING` silences attempts without losing the exhaustion line.
- *technical* — `Retry-After` is honoured for any class that carries it, not 429 only, clamped to 30 s.
