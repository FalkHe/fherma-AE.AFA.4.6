---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: sprint 001/02 — every gateway failure is distinguishable

## Facts

**Sprint 01's seam.** `chat_model()` returns a raw `ChatOpenRouter` (`app/core/llm/service.py:30`), so
provider errors surface at the *caller* (`commands.py:30`,`:36`), never inside it. `LlmError` is the plug-in
point (`errors.py:1`) and the CLI catches it (`commands.py:39`), but `LlmConfigurationError` keeps its own
message (`tests/core/llm/test_commands.py:104`) — the generic line must not move onto the base. Sprint-01
tests monkeypatch module-level `service.ChatOpenRouter` (`tests/core/test_llm_seam.py:34`,
`tests/core/llm/conftest.py:25`) asserting `model`/`temperature`/`api_key` only: extra kwargs are safe,
replacing the constructed name is not. `core/errors.py` is wire-only (`:17`,`:30`,`:48`,`:71`); **no route
calls the seam, nor is one in scope**.

**External — read and executed inside `app-cli` (site-packages, 2026-09-15): `openrouter` 0.10.8 ·
`langchain-openrouter` 0.2.8 · `langchain-core` 1.6.3.**

- `ChatOpenRouter` catches nothing (`chat_models.py:572`,`:607`): every status raises a typed
  `openrouter.errors.*` subclass of `OpenRouterError` carrying `.status_code: int` and `.message` == the
  provider's `error.message`, a non-JSON body degrading to `OpenRouterDefaultError` — **match on
  `.status_code`, never the class list**. A 200 the SDK rejects raises `ResponseValidationError`
  (`.status_code == 200`); langchain-openrouter's provider-error `ValueError` branches are dead code here.
- **Mid-stream failure and refusal are silent chunks, not exceptions** (executed): `finish_reason` lands in
  `chunk.response_metadata` on `.stream()` and `message.response_metadata` on `.invoke()`; `'error'` and
  `'content_filter'` both returned normally, exit 0. `LLM_UNAVAILABLE`/`LLM_REFUSED` are reachable on the
  stream path **only** by inspecting that key.
- **SDK retry is on and near-unbounded**: `max_retries=2` (today's default) → `max_elapsed_time 300_000 ms`;
  `max_retries=0` → the SDK's own `BackoffStrategy(500, 60000, 1.5, 3_600_000)` on `5XX`
  (`openrouter/chat.py:597`) — a 502 hangs minutes before surfacing, and WI5's 5XX tests hang with it.
  `retry_config=None` on the SDK client switches it off (verified: 5XX instant), and `ChatOpenRouter.client:
  Any` (`:164`) accepts such a prebuilt `openrouter.OpenRouter`, which takes
  `client=httpx.Client(transport=…)` and `timeout_ms`.

## Work items

WI1 first (unblocks the import), WI2–WI4 in parallel, WI5 last; `backend-python`, WI5 `qa-backend`.

- WI1 wire codes (AC6): eight `ErrorCode` members, eight `_ERROR_INFO` rows, `LLM_FAILURE_MESSAGE` and an
  `LlmError` handler, all in `backend/app/core/errors.py`.
- WI2 (AC1, AC5) `core/llm/errors.py`: eight subclasses, `classify()`, `raise_for_finish_reason()`.
- WI3 seam: `core/llm/service.py` — `build_sdk_client()`, `chat()`, `chat_stream()`.
- WI4 CLI (AC3, AC4): `core/llm/commands.py` — `--details`, generic line, exit 1.
- WI5 tests (AC2): `tests/core/llm/test_errors.py` (all eight via `httpx.MockTransport`), additions to
  `test_commands.py`, `tests/core/test_llm_error_envelope.py`. Sprint-01's tests stay green.

## Interfaces

- `core/errors.py` (WI1): `ErrorCode.LLM_AUTH | LLM_BUDGET | LLM_RATE_LIMIT | LLM_TIMEOUT | LLM_REFUSED |
  LLM_UNAVAILABLE | LLM_MALFORMED | LLM_BAD_REQUEST`, each `_ERROR_INFO` row `(502, LLM_FAILURE_MESSAGE)`,
  `LLM_FAILURE_MESSAGE = "The AI service could not complete that request."` Handler
  `@app.exception_handler(LlmError)` in `register_error_handlers` emitting `_envelope(exc.code, message,
  None)`, importing `app.core.llm.errors` function-locally.
- `core/llm/errors.py` (WI2). `LlmError` gains class attrs `code: ErrorCode`, `retryable: bool` and
  `__init__(self, provider_message: str | None = None)` storing it and passing `LLM_FAILURE_MESSAGE` to
  `super()`; `LlmConfigurationError` unchanged, no `code`. Subclasses `LlmAuthError`, `LlmBudgetError`,
  `LlmRateLimitError`, `LlmTimeoutError`, `LlmRefusedError`, `LlmUnavailableError`, `LlmMalformedError`,
  `LlmBadRequestError` — each `code` is the matching `ErrorCode` member, `retryable = True` for
  rate-limit/timeout/unavailable/malformed only (AC5).
  - `classify(exc: Exception) -> LlmError | None`; `None` = not ours, re-raise unchanged. `LlmError` → as is.
    `OpenRouterError` by `.status_code`: 400/404/413/422 bad request · 401 auth · 402 budget · 403 refused ·
    408/524 timeout · 429 rate limit · 500/502/503/529 unavailable · 200 malformed; other 4xx → bad request,
    other 5xx → unavailable. `httpx.TimeoutException` → timeout · `httpx.ConnectError`/`NoResponseError` →
    unavailable · `pydantic_core.ValidationError`/`OutputParserException` → malformed. `provider_message =
    _redact(getattr(exc, "message", "") or "")[:500] or None` — provider text only, `None` for client-side
    exceptions. `_redact(text: str) -> str` blanks any literal `get_settings().openrouter_api_key`, since
    `OpenRouterDefaultError` inlines the raw response body into its own message.
  - `raise_for_finish_reason(message: BaseMessage) -> None` — on `response_metadata["finish_reason"]`:
    `"content_filter"` → `LlmRefusedError`, `"error"` → `LlmUnavailableError`, else return.
- `core/llm/service.py` (WI3). `chat_model()` keeps its signature and still constructs module-level
  `ChatOpenRouter`, now with `client=build_sdk_client(settings.openrouter_api_key)`. New module-level names
  `REQUEST_TIMEOUT_MS = 60_000` and `build_sdk_client(api_key: str) -> openrouter.OpenRouter` =
  `OpenRouter(api_key=api_key, retry_config=None, timeout_ms=REQUEST_TIMEOUT_MS)`; WI5 monkeypatches
  `service.build_sdk_client` to return one wired to `httpx.Client(transport=httpx.MockTransport(handler))` —
  the injection seam for all eight. `chat(prompt: LanguageModelInput, *, model=None, temperature=None) ->
  AIMessage` and `chat_stream(...) -> Iterator[AIMessageChunk]` call `chat_model(...).invoke`/`.stream`, wrap
  the provider call in `except Exception as exc: if (e := classify(exc)): raise e from exc; raise`, and run
  `raise_for_finish_reason` on the reply (streaming: per yielded chunk, i.e. *after* its text is out — the
  generic line lands on stderr, exit 1). 03, 04/05 and 08 consume these two helpers.
- `core/llm/commands.py` (WI4): new flag `--details` (bool, off); both paths call
  `llm_service.chat`/`chat_stream`. `except LlmError` prints `str(exc)` to stderr (the generic line, never the
  code) and exits 1; `--details` adds `details: <provider_message>`, or `details: the provider gave no
  message.` when `None`.

## Open questions

- **None product-visible — the sprint may start**: D2 fixes the user-facing behaviour, AC5 the retryable
  split. The calls below are mine, for veto.
- *technical* — all eight reach the wire as `(502, LLM_FAILURE_MESSAGE)` — one status, one wording (← D2).
- *technical* — 404/413/422 fold into `LLM_BAD_REQUEST`, 529 into `LLM_UNAVAILABLE` (no separable signal).
- *technical* — SDK-internal retry is switched off in the seam so sprint 03 owns retry.
- *technical* — `--details` prints only the redacted `.message`, **never `.body`, `.headers` or
  `.raw_response`: `raw_response.request.headers` carries `Authorization: Bearer <OPENROUTER_API_KEY>`, so
  printing them would leak the API key to the terminal.**
- *technical, for sprint 03's research* — D6's quiet retry sits on an SDK that retries `5XX` itself. This
  sprint disables it at the seam; 03 must confirm that holds where it adds backoff, or it ships
  retries-on-retries and multi-minute waits.
