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
- I1 `backend/app/modules/game/agent/flow_state.py` (frozen dataclasses, str enum, one TypedDict; old `agent/state.py` untouched):
  ```python
  class OperationKind(str, Enum):  # value = lower name; exactly these 23
      RECORD_BEAT COMPLETE_ACTION CLOSE_TURN FINISH_RUN
      REQUEST_ROLL ROLL_PLAYER REQUEST_CHOICE ACCEPT_CHOICE
      ROLL_ACTOR PASSIVE_CHECK RESOLVE_CHECK RESOLVE_SAVE SETTLE_INITIATIVE
      INTERACT TAKE_ITEM DROP_ITEM GIVE_ITEM USE_EXIT ENTER_NEXT_ADVENTURE SET_HOSTILITY LEAVE_SCENE
      RESOLVE_ATTACK APPLY_DAMAGE
  TurnFrame(run_id, hero_id, turn_id, input_kind: Literal["opening","action","roll","choice","retry"], text: str | None, status: Literal["open","closing","closed","terminal"], round_admitted: bool)
  Move(intent: str, refs: Mapping[str, str])                      # role -> object id
  OperationSpec(kind: OperationKind, payload: Mapping[str, Any])
  ActionCursor(action_id, actor_id, kind: str, plan: tuple[OperationSpec, ...], step_index: int, status: Literal["planned","reserved","complete","skipped"], roll_id: str | None, roll_consumed: bool)
  CombatCursor(scene_id, order: tuple[str, ...], index: int, round: int, round_admitted: bool, winning_side: Literal["hero","hostile"])
  AwaitingRef(request_id, kind: Literal["roll","choice"], actor_id, public: Mapping[str, Any], consumer: OperationKind, consumer_payload: Mapping[str, Any])
  ReactionSpec(reaction_id, kind: str, payload: Mapping[str, Any])
  NarrativeCursor(beat_id: str | None, draft: str | None, event_id: str | None)
  Usage(prompt_tokens: int, completion_tokens: int, cost: Decimal | None)
  ExecutionError(code: str, message: str, operation_id: str | None)
  Operation(operation_id, kind: OperationKind, payload: Mapping[str, Any])
  OperationResult(operation_id, status: Literal["ok","refused","error"], reason: str | None, event_ids: tuple[str, ...], value: Mapping[str, Any])
  NextEffect = Any   # placeholder; sprint 07 owns it
  class GameFlowState(TypedDict): turn: TurnFrame; move: Move | None; action: ActionCursor | None; combat: CombatCursor | None; awaiting: AwaitingRef | None; pending_hit_id: str | None; reactions: list[ReactionSpec]; narrative: NarrativeCursor; effect: NextEffect | None; result: OperationResult | None; usage: Usage | None; error: ExecutionError | None
  StateDelta = dict[str, Any]
  def close_turn_state(state) -> StateDelta      # clears awaiting, move, action, result, reactions, narrative, effect, error; keeps combat
  def end_combat_state(state) -> StateDelta      # combat=None
  ```
  Ids from `core/ids.generate_id()`. Serializer: langgraph `JsonPlusSerializer` round-trips frozen dataclasses and str enums (verified).
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

## Order
WI1 first. Then parallel: WI2 (creates the registry file), WI3 (adds entries).
