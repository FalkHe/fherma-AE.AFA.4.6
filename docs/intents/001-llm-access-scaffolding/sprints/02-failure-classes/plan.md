---
author: sprint
owner: agent
created: 2026-09-15
---
# Plan: Sprint 02 — every gateway failure is distinguishable, and says one thing

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The eight LLM codes exist on the HTTP wire behind one shared message | each code resolves to `(502, LLM_FAILURE_MESSAGE)`; an `LlmError` raised in a route becomes the standard envelope | – |
| 2 | backend-python | Eight exception classes, a classifier, and a finish-reason check | every status maps to its class; retryable flag correct on all eight; provider text redacted; unknown exception returns `None` and is re-raised | I2 · WI1 |
| 3 | backend-python | Seam helpers that classify what the provider raises, with SDK retry off | `chat`/`chat_stream` translate provider errors; `build_sdk_client` passes `retry_config=None`; silent error chunks raise | I3 · WI1 |
| 4 | backend-python | `--details` on `app llm chat`, generic line on failure | failure prints the generic line and exits 1; `--details` adds redacted provider text, or says none was given | I4 · WI1 |
| qa | qa | Black-box acceptance tests for AC1–AC6 | all eight classes injected through `httpx.MockTransport`, no API key | I1–I4 |

## Interfaces
Verbatim from `research.md → Interfaces`; binding. Summarised here, read that file for the full text.

- I1: `core/errors.py` — `ErrorCode.LLM_AUTH | LLM_BUDGET | LLM_RATE_LIMIT | LLM_TIMEOUT | LLM_REFUSED | LLM_UNAVAILABLE | LLM_MALFORMED | LLM_BAD_REQUEST`, every `_ERROR_INFO` row `(502, LLM_FAILURE_MESSAGE)` with `LLM_FAILURE_MESSAGE = "The AI service could not complete that request."`. `@app.exception_handler(LlmError)` in `register_error_handlers`, importing `app.core.llm.errors` function-locally to avoid a cycle.
- I2: `core/llm/errors.py` — `LlmError` gains `code: ErrorCode`, `retryable: bool`, `__init__(provider_message: str | None = None)`. Eight subclasses; `retryable = True` only for rate-limit, timeout, unavailable, malformed. `classify(exc) -> LlmError | None` (`None` = not ours, re-raise unchanged), mapping by `.status_code`, never by class list. `raise_for_finish_reason(message) -> None`. `_redact()` blanks any literal `get_settings().openrouter_api_key`.
- I3: `core/llm/service.py` — `chat_model()` keeps its sprint-01 signature; adds `REQUEST_TIMEOUT_MS = 60_000` and `build_sdk_client(api_key) -> openrouter.OpenRouter` with `retry_config=None`. New `chat(...) -> AIMessage` and `chat_stream(...) -> Iterator[AIMessageChunk]`.
- I4: `core/llm/commands.py` — `--details` flag (bool, off). `except LlmError` → generic line on stderr, exit 1, never the code. `--details` appends `details: <provider_message>` or `details: the provider gave no message.`

## Acceptance tests (qa)
- AC1 → each of the eight raised for its own trigger, via `httpx.MockTransport` through `service.build_sdk_client`.
- AC2 → the whole suite runs with no API key; assert no network call is made.
- AC3 → all eight print the identical generic line and exit 1; the code never appears in it.
- AC4 → `--details` prints the provider message when present, the "no message" line when absent, and never the key.
- AC5 → `retryable` is True for exactly rate-limit, timeout, unavailable, malformed.
- AC6 → an `LlmError` surfaces through `core/errors.py`'s envelope with its own code.

## Order
Wave 1: WI1 alone (it defines the `ErrorCode` members the rest import). Wave 2, parallel: WI2, WI3, WI4, qa.

**Three traps, all verified in the container — an implementer who misses one ships a bug:**
1. SDK retry is on by default: without `retry_config=None` a 502 test hangs ~5 min. This is why WI3 owns `build_sdk_client`.
2. Mid-stream failure and refusal are **silent chunks** (`finish_reason == "error" | "content_filter"`, exit 0), not exceptions — only `raise_for_finish_reason` catches them.
3. `--details` must print only the redacted `.message`. `.body` / `.headers` / `.raw_response` carry `Authorization: Bearer <OPENROUTER_API_KEY>`.
