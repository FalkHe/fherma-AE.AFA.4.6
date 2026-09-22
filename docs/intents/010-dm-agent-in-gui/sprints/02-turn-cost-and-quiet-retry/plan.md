---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 02

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The shared model seam gains an asynchronous entry point with the same quiet retry and error classification the synchronous one has | a retryable failure is retried and succeeds; a non-retryable one is raised at once; a malformed reply is capped at two attempts; nothing actually sleeps in tests | – |
| 2 | backend-python | The Dungeon Master's narration call goes through that seam, and each turn's narration carries the summed token counts and cost of every model call that turn made | a model failing once still ends in a narration; a permanent failure raises the classified error with everything already recorded intact; a two-call turn's narration carries the sum | interfaces I1, I2, I3 |

## Interfaces
- I1 (`app/core/llm/service.py`):
  `async def ainvoke_chat(model: Runnable[LanguageModelInput, BaseMessage], prompt: LanguageModelInput, *, label: str = "chat_async") -> AIMessage`
  Awaits `model.ainvoke(prompt)`; a provider exception goes through `classify()`, then
  `raise_for_finish_reason(message)`; the whole attempt runs through `acall_with_retry(..., label=label)`.
  Takes an already-built, already-tool-bound runnable and never calls `chat_model()` — so
  `LlmConfigurationError` stays at `build_agent()` time and the injected-model test seam is untouched.
  Passes no `config=`, opens no span: the turn is already traced.
- I2 (`app/core/llm/retry.py`):
  `async def acall_with_retry[T](operation: Callable[[], Awaitable[T]], *, label: str) -> T`
  Same budget, backoff, clamp and log events as `call_with_retry`, awaiting a module-level `_asleep`
  (wrapper over `asyncio.sleep`, the test seam). Re-raises the last `LlmError` unchanged. Decide-from-sleep
  is split out of `_log_attempt_and_should_retry` so budget, backoff and logging stay single-sourced;
  `chat`, `chat_stream`, `call_with_retry`, `stream_with_retry` are untouched.
- I3 (narration usage, existing signature `playthrough/service.py:2407`):
  `record_narration` builds one `Usage` by summing `llm_service.usage_of(m)` over the `AIMessage`s after
  the last `HumanMessage` in `state["messages"]` — token counts added as ints, `cost_usd` the sum of the
  non-`None` costs or `None` when no call reported one — and passes it as `usage=` beside the existing
  `payload={"text": ...}`. `NarrationPayload` is unchanged: cost lives in columns, never in the payload,
  so no wire shape moves. The run-level sum (`run_cost`, `playthrough/service.py:2602`) already exists.

## Acceptance tests (qa)
No qa work item — the backlog reserves acceptance tests for sprint 03. AC1, AC2 → WI2; AC3, AC4 → WI1 and WI2.

## Order
Parallel: WI1, WI2. WI2 implements against I1/I2 without waiting.
