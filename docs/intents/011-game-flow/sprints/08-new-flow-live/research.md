---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 011/08 — the new flow goes live

## Facts

- Today's entry point infers the turn kind from the *old* graph's interrupt value and the transcript: `backend/app/modules/game/service.py:236-323` (`thread_state` → `snapshot.interrupt["type"] == "question"|"roll_request"`, else `snapshot.pending` → retry, else text → action, else opening). `thread_state` reads `snapshot.tasks[0].interrupts[0].value` (`service.py:156-176`). All of this is replaced by the checkpointed `awaiting: AwaitingRef | None` in `GameFlowState` (`agent/flow_state.py:160-174`): `awaiting.kind` is `"roll"` or `"choice"`; `snapshot.next` alone still means retry.
- The new `AwaitingRef` is written by the operations themselves (`agent/operations.py:136,173`) and carries `request_id` = the `roll_requested`/`question` event id, plus `public` (`{ability, skill, dc}` or `{text, options}`). `resume_operation(awaiting, resume)` (`agent/advance.py:134-149`) already validates the resumed `ResumeResult.request_id` against it and rejects a mismatch — the "validate against the checkpointed request" requirement is code that exists; `run_turn` only has to pass a `ResumeResult` with the checkpointed id.
- Answer rows are now written *inside* the graph: `_accept_choice` calls `playthrough_service.record_answer` (`operations.py:182-200`) and `_roll_player` calls `resolve_roll_request` (`operations.py:145-156`). `run_turn` must therefore stop writing the answer row it writes today (`service.py:252`). Only a *new* player action is recorded before invoke, via `playthrough_service.record_player_action` (`playthrough/service.py:3717`).
- Nodes take dependencies from a module-level runtime: `flow_nodes.set_runtime(FlowRuntime(db, user_id, model))` (`agent/flow_nodes.py:47-66`); the router is `flow_nodes.route_after_advance` (`flow_nodes.py:178-200`, returns `"decide" | "execute" | "await_player" | "narrate" | END`). No graph composes them yet; `agent/graph.py:11-45` still builds the old six-node DM graph.
- `TurnRead` stays `{turnId, kind, awaiting}` with `kind ∈ action|answer|roll|retry|opening` (`game/schemas.py:59-83`); `awaiting` is `get_awaiting` read after the turn (`playthrough/service.py:3872`, derived from the open turn's unanswered `roll_requested`/`question` rows — unchanged, because the graph still writes those two rows).
- The frontend never reads the interrupt payload or the turn body's content: `useTakeTurn.ts:57-67` uses the response only to clear its pending row and invalidate the transcript, and `usePlayTranscript.ts:73-99` takes `awaiting`/`turnUnfinished` from the *events* endpoint. The opening posts `{text: null}` (`useTakeTurn.ts:53,90`). So the interrupt payload shape is free; the three `awaiting` shapes and the event kinds are not.
- The opening is client-triggered: enter adventure (`playthrough/routes.py:152`) then a text-less turn. It maps to `TurnFrame(input_kind="opening", text=None, status="open", round_admitted=False)` (`flow_state.py:44-52`).
- CLI `play` (`game/commands.py:168-253`) drives `game_service.turn/resume` and the old interrupt dict directly. Least effort: rewrite `_play_session` to loop on `game_service.run_turn(db, ...)` plus `playthrough_service.get_awaiting`, dropping `DmContext`; it keeps working without knowing graph internals.
- DM tone: no tone value exists anywhere in the backend (only `character/prompts/.../creator.md` prose). Wiring it is not one line — it needs a stored field. Out of scope; leave the sprint 06 proposal open.
- Checkpointer: `async with checkpointer_service.checkpointer() as saver` (`service.py:232`, `core/checkpointer/service.py`), thread id = the run id. Tests use `InMemorySaver` (`tests/game/test_flow_nodes.py:6`).
- Test pattern: acceptance-through-HTTP tests stub `run_turn` wholesale (`tests/game/test_acceptance_turn_endpoint.py`), and a real scratch database is available via the `playthrough_db` fixture over `tests/database.scratch_db` with the `database` marker (`tests/game/conftest.py`, `test_concurrent_monster_rolls_database.py:88`). Recommendation: the four scenarios run `database`-marked against `playthrough_db` with `ScriptedChatModel` (`tests/game/fakes.py`) and `InMemorySaver` — real deltas, real events, no provider; anything less stubs away what the sprint is meant to prove.

## Work items

- WI1 compose the graph: `agent/graph.py` gains the five-node build (START→advance, one conditional edge from `advance` using `flow_nodes.route_after_advance`, fixed edges worker→advance), plus `initial_state`; one topology test asserting exactly five nodes and one conditional route.
- WI2 turn entry point: rewrite `game.service.run_turn` around the new state (kind from checkpointed `awaiting`/`snapshot.next`, `record_player_action` before invoke, `Command(resume=…)` for an answered request, `ainvoke(None)` for retry, `set_runtime` once per turn), keep `TurnRead`, rewrite `thread_state`, point CLI `play` at `run_turn`; delete the old-inference tests in `test_run_turn_engine.py`, keep route/auth tests.
- WI3 the four scenarios (`tests/game/test_scenarios_database.py`): opening + conversation; investigation across a roll pause *and* a restart (fresh graph instance, same saver); a world-changing move; a fight from initiative to defeat with one ambiguous reference — asserting transcript order and `awaiting`, never node sequences.

WI1 first (WI2 and WI3 need `build_graph`'s signature only); WI2 and WI3 then run in parallel.

## Interfaces

- `build_graph(model: BaseChatModel, *, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph` — nodes `"advance" | "decide" | "execute" | "await_player" | "narrate"`; router `flow_nodes.route_after_advance`, map `{"decide": "decide", "execute": "execute", "await_player": "await_player", "narrate": "narrate", END: END}`.
- `initial_state(frame: TurnFrame) -> GameFlowState` in `agent/graph.py` — every key of `GameFlowState` at its empty value, `narrative=NarrativeCursor(None, None, None)`, `reactions=[]`.
- `game.service.run_turn(db, *, user_id, run_id, text) -> TurnOutcome` — signature and `TurnOutcome(turn_id, kind, awaiting)` unchanged; `awaiting` still `get_awaiting(...)` after the invoke.
- Resume payload: `Command(resume=state.values["awaiting"].request_id and value)` → `await_player` wraps it as `ResumeResult(request_id=wait.request_id, value=value)`; the value is the answer text for a choice and ignored (`{}`) for a roll.
- `thread_state(agent, *, thread_id) -> ThreadState(awaiting: AwaitingRef | None, pending: bool)` — `awaiting` from `snapshot.values.get("awaiting")`, `pending` from `bool(snapshot.next)`.

## Open questions

None product-visible. Live check before merge: open a run, take the opening turn, talk, answer a question, press the roll button, start a fight — the waiting indicator, answer buttons and dice chips must behave as today.
