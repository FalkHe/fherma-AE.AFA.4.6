---
author: fhit:architect
owner: agent
created: 2026-09-24
updated: 2026-09-24
---
# Research: sprint 011/07 — scheduler and node functions

## Facts

- State keys the scheduler reads: `GameFlowState` at `backend/app/modules/game/agent/flow_state.py:161`; `NextEffect = Any` placeholder at `flow_state.py:158` — this sprint replaces it. `close_turn_state()` (`flow_state.py:179`) and `end_combat_state()` (`flow_state.py:196`) already exist; the scheduler never applies them, `CLOSE_TURN`/`FINISH_RUN` handlers do (`operations_world.py:194,205`).
- Deltas the handlers return, which the scheduler must read next visit:
  - `_request_roll` → `{"awaiting": AwaitingRef(...)}` with `consumer`/`consumer_payload` (`operations.py:136`); `_request_choice` likewise (`operations.py:174`).
  - `_roll_player` → `{"awaiting": None}` and, when an action is active, `action.roll_id=<event id>`, `roll_consumed=False` (`operations.py:155`).
  - `_accept_choice` → `{"awaiting": None}` plus a `move.refs` binding (`operations.py:198`).
  - `_resolve_check`/`_resolve_save` → refuse `"roll_already_consumed"` and otherwise set `action.roll_consumed=True` (`operations.py:249,261`).
  - `_resolve_attack` → `{"pending_hit_id": result.hit_id}` on `hit`/`critical`, `value["status"]` in `hit|miss|critical` (`operations.py:327`); `_apply_damage` → `{"pending_hit_id": None}`, `value` carries `down`/`is_alive` (`operations.py:347`).
  - `_settle_initiative` with no `hero_roll_id` returns `value={"status":"awaiting_hero_roll"}` and writes no cursor (`operations.py:281`); with one it writes `CombatCursor(order, index=0, round=1, round_admitted=True, winning_side)` (`operations.py:299`). Hero-side tie win is already settled inside `playthrough_service.settle_initiative`.
  - `_complete_action` → `action.status="complete"` (`operations_world.py:189`); `_record_beat` → `narrative.event_id` set, `draft=None` (`operations_world.py:180`).
- Eligibility source: `ActorView(role, is_alive, down, hostile)` (`playthrough/situation.py:47`), `Situation.actors` = the actors *present* in the scene (`situation.py:138`), `hero.down` gives AC2. Eligible hostile = `role == "hostile"` (or `hostile`), `not down`, `is_alive`, and present in `situation.actors`. `combat.order` ∩ present, with `index` proving who acted (`flow_state.py:82`).
- Decision → plan mapping (from `docs/general/game-flow.v2.md`, "Action plans"): `ReadMoveDecision.proposed` (`decisions.py:77`) is a `tuple[OperationSpec, ...]` already validated against the situation → becomes the `ActionCursor.plan`; `MonsterAction(actor_id, attack, target_id)` (`decisions.py:104`) → `attack_plan(...)`; `ReferenceJudgement.ask_choice` (`decisions.py:90`) → `REQUEST_CHOICE` with `consumer=ACCEPT_CHOICE`; `MoveAssessment.dc` (`decisions.py:96`) → `player_roll_plan(consumer=RESOLVE_CHECK, dc=...)`; `WorldReaction.reactions` (`decisions.py:111`) → `state["reactions"]`, consumed head-first.
- `interrupt()`: `langgraph 1.2.11` (`backend/uv.lock:537`, verified in the container — source: local). `from langgraph.types import interrupt`; signature `interrupt(value: Any) -> Any`; it raises on first call and returns the resume value when the node is re-entered, so the node body before it re-runs — hence "no write before the interrupt". Resume arrives as `Command(resume=...)` (`langgraph.types.Command`); the pending payload is read at `game/service.py:80` (`result["__interrupt__"][0].value`) and `game/commands.py:99`. Existing payload shapes to mirror: `{"type":"roll_request","request_id",...}` (`agent/tools.py:600`) and `{"type":"question","question_id",...}` (`agent/tools.py:547`).
- Guard: `GUARD_PATTERNS: list[tuple[re.Pattern, str]]` at `agent/nodes.py:29` — import the list, do not copy the strings; `make_guard` (`nodes.py:401`) stays with the old graph.
- Usage: `model_call.to_usage()` returns one `Usage` per call (`agent/model_call.py:36`); `flow_state.Usage` is a flat frozen dataclass, so nodes accumulate by adding the new call's fields onto `state["usage"]` (a small `add_usage(a, b)` helper in `effects.py`), since `_record_beat` passes `state["usage"]` to `record_narration` (`operations_world.py:174`).
- Test fakes available: `backend/tests/game/fakes.py` (`ScriptedChatModel`), situation builders in `tests/game/test_operations.py` and `test_decisions.py`.

## Work items

- **WI1 — effects + pure scheduler.** `agent/effects.py` (effect types, `add_usage`) then `agent/advance.py`: `select_next_effect` split into `advance_terminal/advance_hit/advance_request/advance_action/advance_combat/advance_reactions/advance_narration/validate_turn_close`, the three plan builders, `eligible_hostiles`, the guard check. One table-driven test over all eight priorities plus the three named cases (AC1–AC3, AC5). Land `effects.py` first so WI2 can start.
- **WI2 — node functions.** `agent/flow_nodes.py`: `advance/decide/execute/await_player/narrate` plus `route_after_advance`, all plain async `(state) -> delta`, dependencies from a module-level `FlowRuntime` set by sprint 08. One boundary test per node; the interrupt/resume test builds a throwaway two-node `StateGraph` with `MemorySaver` inside the test only (AC4).
- **WI3 — resume mapping (small, fold into WI2 if it fits).** `resume_operation(awaiting, resume) -> Operation | None`: roll acknowledgement → `ROLL_PLAYER`, choice → `ACCEPT_CHOICE`, mismatched `request_id` → `None` (rejected). Lives in `advance.py`, tested with the WI1 table.

WI1 → (WI2 ‖ WI3). WI2 and WI3 run in parallel once `effects.py` exists.

## Interfaces

```python
# agent/effects.py
@dataclass(frozen=True)
class PlayerWait:
    request_id: str
    kind: Literal["roll", "choice"]
    public_payload: Mapping[str, Any]

@dataclass(frozen=True)
class TurnComplete:
    status: Literal["open", "terminal", "execution_error"]

# Operation (flow_state.py:136), DecisionRequest (decisions.py:61) and
# BeatRequest (narration.py:50) are reused unchanged; effects.py re-exports them.
NextEffect = DecisionRequest | Operation | PlayerWait | BeatRequest | TurnComplete

@dataclass(frozen=True)
class ResumeResult:
    request_id: str
    value: Any

def add_usage(current: Usage | None, added: Usage) -> Usage: ...

# agent/advance.py
def select_next_effect(state: GameFlowState, situation: Situation) -> NextEffect: ...
def eligible_hostiles(situation: Situation, combat: CombatCursor | None) -> tuple[str, ...]: ...
def player_roll_plan(*, actor_id: str, consumer: OperationKind,
                     payload: Mapping[str, Any]) -> tuple[OperationSpec, ...]: ...
def attack_plan(*, actor_id: str, target_id: str, attack: str,
                is_player: bool) -> tuple[OperationSpec, ...]: ...
def complete_action_plan(action_id: str) -> tuple[OperationSpec, ...]: ...
def guard_refusal(text: str | None) -> str | None: ...   # nodes.GUARD_PATTERNS
def resume_operation(awaiting: AwaitingRef, resume: ResumeResult) -> Operation | None: ...

# agent/flow_nodes.py
@dataclass(frozen=True)
class FlowRuntime:
    db: AsyncSession
    user_id: str
    model: BaseChatModel

async def advance(state: GameFlowState) -> StateDelta: ...
async def decide(state: GameFlowState) -> StateDelta: ...
async def execute(state: GameFlowState) -> StateDelta: ...
async def await_player(state: GameFlowState) -> StateDelta: ...
async def narrate(state: GameFlowState) -> StateDelta: ...
def route_after_advance(state: GameFlowState) -> str:  # "decide"|"execute"|"await_player"|"narrate"|END
```

Guard refusal (least effort, no model call): `advance` returns the canned text straight into `state["narrative"].draft` and emits `Operation(RECORD_BEAT)`; normal priority-7/8 handling then records it and closes the turn — no refusal beat type and no extra effect.

## Open questions

- None product-visible.
