---
author: architect
owner: agent
created: 2026-09-23
---
# Research: sprint 010/02 — turn cost and quiet retry

## Facts

**Per-call usage already exists at the seam.** `usage_of(message) -> Usage(prompt_tokens,
completion_tokens, total_tokens, cost_usd)` reads `usage_metadata` and `response_metadata["cost"]`,
degrading to zeros/`None` (`core/llm/service.py:243-260`; dataclass `:80-85`). Nothing in `game`
calls it.

**The write side is already built.** `append_event(db, *, run_id, type, visibility, payload,
turn_id=None, actor_member_id=None, usage: Usage | None = None)`
(`playthrough/service.py:2407-2416`) fills `events.prompt_tokens/completion_tokens/cost_usd`
(`playthrough/models.py:229-231`) and adds the narration's own embedding usage on top (`:2503-2514`).
`record_narration` passes no `usage=` (`game/agent/nodes.py:319-327`), so the columns stay NULL.

**The read side is already built.** `run_cost(db, *, user_id, run_id) -> RunCost(total,
turns=[TurnCost(turn_id, total)])` groups `SUM(cost_usd)` by `turn_id`
(`playthrough/service.py:2602-2635`), reachable as `app playthrough cost`
(`playthrough/commands.py:91`). No new read, no ledger (AC2).

**A turn's model replies are all in checkpointed state.** Each `narrate` pass appends its
`AIMessage` (`nodes.py:291-292`); a turn opens with exactly one `HumanMessage`
(`game/service.py:80`) and a `resume` adds none (`:97`). The messages after the last `HumanMessage`
are therefore precisely this turn's model replies — across an interrupt too, since messages are
checkpointed. `turn_id` is a fresh `uuid4` per `turn` *and* per `resume` (`game/commands.py:43,66`),
carried on `DmContext.turn_id` (`agent/state.py:140`).

**The seam is synchronous only — the brief's assumption is confirmed.** `chat()`
(`core/llm/service.py:154-188`) wraps `.invoke()` in `classify()` + `raise_for_finish_reason()` +
`call_with_retry(_attempt, label="chat")`. `retry.py` is sync throughout: `call_with_retry:113`,
`stream_with_retry:131`, budget `_budget_of:55`, backoff `_delay_before_next:63`, and
`_log_attempt_and_should_retry:77`, which both decides *and* sleeps (`_sleep:109`).

**The DM bypasses all of it.** `make_narrate` binds once at build time — `bound =
model.bind_tools(TOOLS)` (`nodes.py:282`) — and awaits `bound.ainvoke([system, *state["messages"]])`
(`nodes.py:291`): no classification, no retry. The model comes from `chat_model()`
(`game/service.py:47`) and is injectable for tests (`tests/game/test_service.py:93-98`). The turn as
a whole is already traced (`game/service.py:75-81`).

**Two tools spend model money invisibly**: `lookup_rule` → `srd_service.search_rules`
(`srd/service.py:469`) and `recall` → `playthrough_service.recall` (`playthrough/service.py:2728`)
each embed their query and discard the returned `usage`; neither return shape carries it
(`game/agent/tools.py:661-707`).

No new external API: `bound.ainvoke` and `usage_metadata` are already used here (langchain-core
1.6.3, langgraph 1.2.11 — `backend/uv.lock`, source: local); the async retry needs only
`asyncio.sleep`.

## Work items

- **WI1 — `core/llm` async twin** (backend-python): `retry.acall_with_retry` plus
  `service.ainvoke_chat` (I1, I2), splitting decide-from-sleep out of
  `_log_attempt_and_should_retry` so budget, backoff and logging stay single-sourced. `chat`,
  `chat_stream`, `call_with_retry`, `stream_with_retry` untouched. Tests: a retryable error retried
  quietly, a non-retryable raised at once, malformed capped at two, `retry._asleep` monkeypatched so
  nothing sleeps.
- **WI2 — `game` narration cost and retry** (backend-python): `narrate` calls the seam (AC3, AC4);
  `record_narration` sums this turn's replies and passes `usage=` (AC1, AC2, I3); `game/README.md`
  updated. Tests: a model failing once still ends in a narration; a permanent failure raises the
  classified `LlmError` with the player action and rolls already committed; a two-call turn's
  narration carries the sum.

Both run in parallel once I1 is fixed; only WI2 consumes it.

## Interfaces

**I1 — `app/core/llm/service.py`**

```python
async def ainvoke_chat(
    model: Runnable[LanguageModelInput, BaseMessage],
    prompt: LanguageModelInput,
    *,
    label: str = "chat_async",
) -> AIMessage
```

Awaits `model.ainvoke(prompt)`; a provider exception goes through `classify()` (this app's
`LlmError` or the original re-raised), then `raise_for_finish_reason(message)`; the whole attempt
runs through `acall_with_retry(..., label=label)`. It takes an already-built, already-tool-bound
runnable and — unlike `chat()` — never calls `chat_model()`: `LlmConfigurationError` stays at
`build_agent()` time and the injected-model test seam is untouched. It passes no `config=` and opens
no span; the turn is already traced.

**I2 — `app/core/llm/retry.py`**

```python
async def acall_with_retry[T](operation: Callable[[], Awaitable[T]], *, label: str) -> T
```

Same budget, backoff, clamp and log events as `call_with_retry`, awaiting a module-level `_asleep`
(wrapper over `asyncio.sleep`, the test seam). Re-raises the last `LlmError` unchanged.

**I3 — narration usage** (existing signature, `playthrough/service.py:2407`)

`record_narration` builds one `Usage` by summing `llm_service.usage_of(m)` over the `AIMessage`s
after the last `HumanMessage` in `state["messages"]` — token counts added as ints; `cost_usd` the
sum of the non-`None` costs, or `None` when no call reported one — and passes it as `usage=` beside
the existing `payload={"text": ...}`. The payload shape is unchanged (`NarrationPayload`,
`playthrough/schemas.py:242`): cost lives in columns, never in the payload, so no wire shape moves.

## Open questions

*Product-visible*: none — nothing is displayed (← D8).

*Technical (my assumptions, for veto)*

- The query embeddings inside `lookup_rule` and `recall` stay uncounted: capturing them means
  widening two other modules' return shapes or adding an ambient collector to the seam, and chat
  tokens dominate the turn. The narration's own embedding is already added by `append_event`.
- A turn interrupted by a question or roll resumes under a new `turn_id`, so the whole turn's model
  cost lands on the resumed leg's narration while the earlier events keep the first id. The run
  total (AC2) stays exact; the per-turn breakdown splits.
- Rejected: accumulating usage in `DmState` behind a reset-on-`None` reducer (a checkpointed field
  for a number the messages already carry), and mutating a list on `DmContext` (lost across the
  interrupt, since a fresh context is built per leg).
