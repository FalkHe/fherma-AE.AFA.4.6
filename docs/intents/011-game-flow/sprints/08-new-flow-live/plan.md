---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 08

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The five behaviours composed into one compiled flow with a single router keyed on the effect type, compiled with the durable checkpointer, plus the empty starting state for a turn (I1) | the compiled flow has exactly the five nodes, one conditional route from the scheduler and fixed returns | – |
| 2 | backend-python | Every turn runs through the new flow from the unchanged turn request: the turn kind comes from the saved request instead of scanning the transcript; a new action is recorded before the flow runs; a roll or answer resumes the saved pause; a retry resumes the saved step; the response shape and waiting marker are unchanged; the terminal play command uses the same path; tests asserting the old inference are gone | opening, action, roll answer, choice answer and retry each reach the flow as the right input; a stale answer is rejected; route and auth tests still pass | I1 |
| 3 | backend-python | Four played-through scenarios with scripted storyteller decisions against the real rules layer (I2): opening and conversation; investigation across a roll pause and a restart; a move that changes the world; a fight from initiative through damage to defeat with one ambiguous reference | transcript order and waiting marker per scenario; the restart resumes the same request; never node sequences | I1 |

## Interfaces
- I1 `agent/graph.py`: `build_graph(model: BaseChatModel, *, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph` with nodes `advance, decide, execute, await_player, narrate`; START → advance; `add_conditional_edges("advance", flow_nodes.route_after_advance, {"decide": "decide", "execute": "execute", "await_player": "await_player", "narrate": "narrate", END: END})`; fixed edge from each worker back to advance. `initial_state(frame: TurnFrame) -> GameFlowState` with every key at its empty value.
- I2 `game/service.py`: `run_turn(db, *, user_id, run_id, text) -> TurnOutcome(turn_id, kind, awaiting)` signature unchanged; `awaiting` still from `playthrough_service.get_awaiting` after the invoke. Kind: checkpoint `awaiting` present → roll or choice resume via `Command(resume=value)` (answer text for a choice, `{}` for a roll; the pause wraps it as `ResumeResult`); `snapshot.next` non-empty with no awaiting → retry via `ainvoke(None)`; else opening or action with `initial_state(TurnFrame(...))` after `record_player_action`. The answer and roll rows are written inside the flow, so the entry point writes only the new player action. `thread_state(agent, *, thread_id) -> ThreadState(awaiting: AwaitingRef | None, pending: bool)`. `flow_nodes.set_runtime(FlowRuntime(db, user_id, model))` once per turn.
- Scenario tests: `database`-marked, `ScriptedChatModel` for decisions and narration, `InMemorySaver`; restart = a fresh `build_graph` on the same saver.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI3 covers AC2 and AC4, WI1 AC3, WI2 AC5; AC1 is the live browser check before merge.

## Order
WI1 first. Then parallel: WI2, WI3. Then live check on the hosted app.
