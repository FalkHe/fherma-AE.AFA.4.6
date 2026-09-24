---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 07

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The effect types the scheduler emits (I1) and the pure scheduler (I2): from saved turn state and a fresh situation it picks exactly one next effect in the fixed order, builds action plans, computes which hostiles are still eligible, and refuses the player's text in the Dungeon Master's voice without a model call when it matches the injection guard | table over all eight priorities and ties; pending hit selects only damage; downed hero selects run completion first; each eligible hostile once per admitted round with down, absent and friendly skipped; hero side wins an initiative tie; closure refused while any obligation remains; guard text yields a canned refusal and no decision request | – (lands `effects.py` first) |
| 2 | backend-python | The five worker behaviours as plain node functions with a router keyed only on the effect type (I3); the pause interrupts with the checkpointed public request and does nothing else before it | one test per node boundary; interrupt and resume through a throwaway two-node graph in the test only, proving nothing was saved or rolled before the pause | I1 |
| 3 | backend-python | A resumed answer is mapped to its operation or rejected (I2 `resume_operation`): roll acknowledgement to the player-roll operation, choice to answer acceptance, mismatched request rejected | stale request id rejected; the two valid mappings | I1 |

## Interfaces
- I1 `agent/effects.py`: `PlayerWait(request_id, kind: Literal["roll","choice"], public_payload)`; `TurnComplete(status: Literal["open","terminal","execution_error"])`; `ResumeResult(request_id, value)`; `NextEffect = DecisionRequest | Operation | PlayerWait | BeatRequest | TurnComplete` (the three existing types re-exported unchanged from flow_state, decisions, narration); `add_usage(current: Usage | None, added: Usage) -> Usage`. `flow_state.NextEffect` placeholder is replaced by this union.
- I2 `agent/advance.py`: `select_next_effect(state, situation) -> NextEffect` composed of `advance_terminal / advance_hit / advance_request / advance_action / advance_combat / advance_reactions / advance_narration / validate_turn_close`; `eligible_hostiles(situation, combat) -> tuple[str, ...]`; `player_roll_plan(*, actor_id, consumer: OperationKind, payload)`, `attack_plan(*, actor_id, target_id, attack, is_player)`, `complete_action_plan(action_id)` → `tuple[OperationSpec, ...]`; `guard_refusal(text) -> str | None` over the existing `GUARD_PATTERNS`; `resume_operation(awaiting: AwaitingRef, resume: ResumeResult) -> Operation | None`. Guard path: canned text goes straight into the narrative draft and a `RECORD_BEAT` operation is emitted; ordinary narration and closure handling finish the turn.
- I3 `agent/flow_nodes.py`: `FlowRuntime(db, user_id, model)` set at module level by sprint 08; `async advance/decide/execute/await_player/narrate(state) -> StateDelta`; `route_after_advance(state) -> "decide" | "execute" | "await_player" | "narrate" | END`, keyed only on the effect's type. `await_player` calls langgraph `interrupt()` with `PlayerWait.public_payload` and stores a `ResumeResult`; `advance` validates it via `resume_operation`.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI tests cover AC1–AC5.

## Order
WI1 first (effects.py within minutes, then the scheduler). Then parallel: WI2, WI3.
