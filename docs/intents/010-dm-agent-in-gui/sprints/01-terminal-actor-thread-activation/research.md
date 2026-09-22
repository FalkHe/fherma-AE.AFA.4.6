---
author: architect
owner: agent
created: 2026-09-23
---
# Research: sprint 010/01 — terminal actor, thread, activation

## Facts

**Actor.** `DmContext(db, user_id, actor_id=None, run_id=None, turn_id=None)` —
`game/agent/state.py:36-42`. Every acting tool falls back to `ctx.actor_id` and raises
`ValueError("actor_id is required … when no default actor is set in context.")` when it is `None`
(`game/agent/tools.py:79-83,153-156,318-321,396-399,430-432,459-461,490-492,523-526,556-558`). The CLI
supplies it only from `--actor/--actor-id` (`game/commands.py:176-178`), so an unnamed actor means every
mechanic fails mid-turn.

**The hero exists and is findable.** `create_character` writes exactly one `kind="creature"` row with
`member_id = member.id` per run (`playthrough/service.py:527-535,530`), refuses a second
(`CharacterExistsError`, `:489-494`) and moves the run to `ready` (`:581`). The seed ("ready-made") hero
is the same row, built from the pinned campaign when `sheet is None` (`:501-503`). No service function
returns it: `get_run_overview` only joins it for a name (`:395-403`), and `_build_game_context` loads
*all* members' creatures for the prompt (`game/agent/nodes.py:113-120`). Membership gate for every
run-scoped function: `_require_member` (`playthrough/service.py:171-186`).

**Thread.** `turn`/`resume` put `thread_id` into `RunnableConfig.configurable`
(`game/service.py:66-82,85-98`). The CLI mints a fresh `uuid4` per session unless `--thread-id` is given
(`commands.py:179-181`), so quitting loses the thread. It already rehydrates an in-flight interrupt from
the checkpointer at startup — `agent.aget_state(config)` → `state.tasks[0].interrupts[0].value`
(`commands.py:82-88`) — and drives the question/roll prompt from it (`:90-131`). The saver is
`AsyncPostgresSaver` in its own schema (`core/checkpointer/service.py:49-53`), so a checkpoint outlives
the process. `get_awaiting` derives the same pending state independently from the transcript
(`playthrough/service.py:2526-2573`). langgraph 1.2.11, langgraph-checkpoint-postgres 3.1.2
(`backend/uv.lock` — local lockfile).

**Activation.** `activate_campaign_run(db, *, user_id, run_id)` — `ready → active`, `active` a no-op, any
other status `InvalidRunStatusError` (`playthrough/service.py:628-645`); it has no caller, and its own
docstring names the first narration as the trigger (`:653-656`). Narration is written by the
`record_narration` node, guarded by `if text:` and committed there (`game/agent/nodes.py:305-330`).
Status lives on `CampaignRun.status` with a check constraint over
`setup|ready|active|archived|finished` (`playthrough/models.py:39-48`); `finished` is reachable mid-turn
when the last adventure's exit is used (`playthrough/service.py:1437`), so activation must not be
attempted unconditionally — that would fail the ending turn after the narration is already committed.

## Work items

- WI1 (playthrough): `get_member_character` — the caller's own creature in a run, plus
  `CharacterNotFoundError`. Tests in `backend/tests/playthrough/test_service_character_and_shelf_life.py`;
  README surface list updated.
- WI2 (game CLI): resolve the actor once per session when `--run-id` is given and `--actor` is not,
  and default the checkpointer thread to the run id. New tests in `backend/tests/game/test_commands.py`;
  `game/README.md:22-24` updated.
- WI3 (game node): first narration activates the run, in `record_narration`. Tests and stub updates in
  `backend/tests/game/test_service.py`.

WI1‖WI3 run in parallel; WI2 starts against WI1's signature below without waiting. No file is touched by
two items.

## Interfaces

**WI1 → WI2** (`app/modules/playthrough/service.py`):

```python
async def get_member_character(db: AsyncSession, *, user_id: str, run_id: str) -> GameObject
```
`_require_member` first (foreign/unknown run → `CampaignRunNotFoundError`), then the single
`GameObject` with `campaign_run_id == run_id`, `kind == "creature"`, `member_id == member.id`. No row →
`CharacterNotFoundError(run_id)` (`errors.py`, `code = ErrorCode.NOT_FOUND`, message naming the run).
Reads only: no commit, no event, no status change.

**WI2** (`app/modules/game/commands.py`): `--run-id` stays optional. In `play`, when `run_id` is set and
`actor_id` is `None`, open one session (`get_sessionmaker()`) before `_play_session` and set
`actor_id = (await playthrough_service.get_member_character(db, user_id=user_id, run_id=run_id)).id`.
`active_thread_id = thread_id or run_id or str(uuid.uuid4())`. `--actor` and `--thread-id` keep
overriding, unchanged, for debugging. `CharacterNotFoundError` is a `PlaythroughError` and already exits
1 with its message via `commands.py:191-193` — no new handling.

**WI3** (`app/modules/game/agent/nodes.py`, inside `record_narration`'s `if text:` branch, after
`append_event` + `commit`):

```python
run = await playthrough_service.get_campaign_run(ctx.db, user_id=ctx.user_id, run_id=ctx.run_id)
if run.status == "ready":
    await playthrough_service.activate_campaign_run(ctx.db, user_id=ctx.user_id, run_id=ctx.run_id)
```
The status read *is* the "first narration" test, and it keeps `finished`, `archived` and `setup` runs
untouched instead of raising `InvalidRunStatusError` on a committed turn. Trade-off: one extra query per
narration. Blast radius: this node only; the narration is already committed, so a failure here costs the
activation, not the turn's record. Existing tests that stub `nodes.playthrough_service.append_event`
(`backend/tests/game/test_service.py:159`) must also stub these two calls — the fake `db` in those tests
cannot answer a real query.

## Assumptions

- Thread id *is* the run id (intent research, option C1): no column, no migration, no session concept;
  history grows untrimmed for the life of the run.
- `awaiting` (transcript-derived) and the paused checkpoint can no longer disagree, because both are now
  keyed by the run — AC2 needs no new resume code beyond the thread id.
- One character per member, so resolution is unambiguous.

## Open questions

None product-visible.
