---
author: sprint
owner: agent
created: 2026-09-15
---
# Plan: Sprint 03 — transient failures are retried before anyone is told

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Attempt count and backoff base are configurable, with documented defaults | both fields validate their bounds; defaults match `.env.dist`; the suite still pins dummy env | – |
| 2 | backend-python | Errors carry a retry-after hint, and the config error is safely non-retryable | `retry_after_seconds` is parsed from the provider header and `None` when absent or unparseable; `LlmConfigurationError.retryable` no longer raises | I2 |
| 3 | backend-python | A retry loop the seam runs, quiet until the budget is spent | retryable classes retried, non-retryable attempted once, malformed capped at two, delay honours `Retry-After` then backoff, every attempt logged | I1, I2, I3 · WI1, WI2 |
| qa | qa | Black-box acceptance tests for AC1–AC6 | scripted 502→502→200 and always-502 through the sprint-02 mock seam; no sleeping | I1–I3 |

## Interfaces
Verbatim from `research.md → Interfaces`; binding. Summarised — read that file for the full text.

- I1: `settings.py` — `llm_retry_attempts: int = 3` (**total** attempts including the first, `ge=1`) and `llm_retry_backoff_seconds: float = 0.5` (`ge=0`). `.env.dist` gains `LLM_RETRY_ATTEMPTS=3` and `LLM_RETRY_BACKOFF_SECONDS=0.5` with the comment text given in the research.
- I2: `core/llm/errors.py` — `LlmError.__init__(provider_message=None, *, retry_after_seconds: float | None = None)`; the positional argument is unchanged so existing call sites keep compiling. `LlmConfigurationError` gains `retryable = False` and `retry_after_seconds = None`. New `_retry_after_of(exc)` reads `exc.headers["retry-after"]`, returning `None` when absent, an HTTP-date, or unparseable; `classify()` passes it on the `OpenRouterError` branch only.
- I3: `core/llm/retry.py` (new) — module constants `MALFORMED_MAX_ATTEMPTS = 2`, `MAX_RETRY_AFTER_SECONDS = 30.0`, and `_sleep(seconds)` / `_random()` wrappers which are **the only AC5 injection points**. Public: `call_with_retry(operation, *, label) -> T` and `stream_with_retry(open_stream, *, label) -> Iterator[T]`. Budget per failure: 1 if not retryable; `min(attempts, MALFORMED_MAX_ATTEMPTS)` for malformed; else the configured attempts. Delay: clamped `retry_after_seconds` when present, else `base * 2 ** (n - 1) * (0.5 + 0.5 * _random())`. Logs `llm_retry_attempt` per failure and `llm_retry_exhausted` at the end, then re-raises the last `LlmError` unchanged.
- I3b: `service.py` — `chat_model()` gains `max_retries=0`; `chat()` wraps its body in `call_with_retry(..., label="chat")`; `chat_stream()` returns `stream_with_retry(_open, label="chat_stream")`. Both rebuild the model per attempt.

## Acceptance tests (qa)
- AC1 → scripted 502→502→200: command succeeds, no failure line, exit 0.
- AC2 → always-502: the generic line appears exactly once, after the configured attempts, exit 1.
- AC3 → 401: attempted exactly once, never retried.
- AC4 → each attempt logs its attempt number and failure class.
- AC5 → the whole suite asserts without sleeping; `retry._sleep` is monkeypatched.
- AC6 → both settings exist with the documented defaults.

## Order
Wave 1, parallel: WI1, WI2, qa. Then WI3 alone, which needs both.

**Three findings that shape this sprint:**
1. `ChatOpenRouter.max_retries` is **dead** since sprint 02 passes `client=` — but sprint 01 *was* silently retrying with a ~300 s window. Set `max_retries=0` as a guard so a later edit dropping `client=` cannot resurrect it.
2. `LlmConfigurationError` sets neither `code` nor `retryable`, so `err.retryable` raises `AttributeError` — on the one error raised before any network call. Same family as the `code` bug sprint 02 fixed at its gate.
3. Streaming retries **only before the first chunk is yielded**. A mid-stream `finish_reason == "error"` is never retried despite being marked retryable — replaying printed text would contradict AC1. This is a stated limitation and belongs in the docstring, not glossed over.
