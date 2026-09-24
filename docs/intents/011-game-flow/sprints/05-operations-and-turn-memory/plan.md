---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 05

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The new flow's checkpoint state exists as typed structures beside the old graph state (I1): turn frame, move, action cursor with roll ownership, combat cursor, awaiting request with private consumer binding, pending hit, reactions, narrative cursor, usage, error, operation kinds and operation/result shapes, plus two pure clearers for turn close and combat end | an awaiting request and a combat cursor round-trip through the checkpoint serializer unchanged; turn close clears request, move, action, result, reactions, narration and keeps combat; combat end clears combat | – |
| 2 | backend-python | One operation registry with the dispatcher and reference validation (I2), and the handlers for player input, checks and combat; a roll request writes the visible request row with the ability, skill and difficulty the dice chip reads, a choice request writes the question with its options verbatim, and the answering row is written after the pause | every operation kind has exactly one handler; a stale or invented reference is refused before any service call | WI1 |
| 3 | backend-python | The world and lifecycle handlers in the same registry (I2) | one representative handler dispatches and returns its typed result with the same operation id; an action whose roll is already consumed cannot apply it twice | WI1, WI2's registry file |

## Interfaces
- I1 `backend/app/modules/game/agent/flow_state.py` (frozen dataclasses, str enum, one TypedDict; old `agent/state.py` untouched). Types and fields exactly as listed in `research.md → Interfaces`: `OperationKind` (23 members), `TurnFrame`, `Move`, `OperationSpec`, `ActionCursor` (with `roll_id`, `roll_consumed`), `CombatCursor`, `AwaitingRef` (public payload plus private `consumer`, `consumer_payload`), `ReactionSpec`, `NarrativeCursor`, `Usage`, `ExecutionError`, `Operation`, `OperationResult`, `GameFlowState`, `StateDelta`; `NextEffect = Any` placeholder until sprint 07. Plus:
  ```python
  def close_turn_state(state) -> StateDelta   # clears awaiting, move, action, result, reactions, narrative, effect, error; keeps combat
  def end_combat_state(state) -> StateDelta   # combat=None
  ```
  Ids from `core/ids.generate_id()`; langgraph `JsonPlusSerializer` round-trips frozen dataclasses and str enums (verified).
- I2 `backend/app/modules/game/agent/operations.py`:
  ```python
  OperationContext(db: AsyncSession, user_id, run_id, hero_id, situation: Situation)   # frozen dataclass
  Handler = Callable[[OperationContext, Operation, GameFlowState], Awaitable[tuple[OperationResult, StateDelta]]]
  OPERATION_HANDLERS: dict[OperationKind, Handler]
  def validate_refs(situation, op) -> str | None     # actor_id/target_id/object_id/item_id/exit_id/attack name/choice key vs situation actors, fixtures, loose items, exits, hero inventory
  async def execute_operation(ctx, op, state) -> tuple[OperationResult, StateDelta]   # validate_refs first; failure -> refused "stale_reference", {} and no service call; then dispatch
  ```
  `request_roll` → `request_player_roll(context={"ability", "skill", "dc"})` (the keys the dice chip reads; `formula` stays the service's derivation), stores the event id as `AwaitingRef.request_id`; `request_choice` → `ask_player(text, options)` with options verbatim; `roll_player`/`accept_choice` write the answering row after the pause. Handlers own no transaction; they call `playthrough.service` functions which do.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI tests cover AC1–AC5.

## Notes
- Type field lists live in research.md to keep this plan within its cap.

## Order
WI1 first. Then parallel: WI2 (creates the registry file), WI3 (adds entries).
