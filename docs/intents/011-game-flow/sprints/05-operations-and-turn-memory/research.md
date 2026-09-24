---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 05 — operations and turn memory

## Facts

Serialization (langgraph 1.2.11 / langgraph-checkpoint 4.2.0 — source: local
site-packages in the app image). `JsonPlusSerializer._msgpack_default`
(`langgraph/checkpoint/serde/jsonplus.py:472,489`) encodes `Enum` and any
`dataclasses.is_dataclass` object as msgpack ext constructors (kwargs by field
name) and revives them by importing the module. `LANGGRAPH_STRICT_MSGPACK`
defaults to `false` (`serde/_msgpack.py:12`), so app-owned classes are allowed;
the permissive path logs, it never calls `warnings.warn`, so pytest's
`filterwarnings = ["error"]` is not tripped. **Verified representation:**
`GameFlowState` as `TypedDict` (plain dict), every nested value a frozen
dataclass, every kind a `str`-valued `Enum` or `Literal`. Matches
`playthrough/situation.py:33+`, which already round-trips frozen dataclasses.

Ids: `app.core.ids.generate_id()` → 26-char ULID string (`core/ids.py:16`).
Use it for `operation_id`, `request_id`, `action_id`, `beat_id`.

Services the handlers wrap (all `playthrough/service.py`, all keyword-only,
all take `db, *, user_id, ..., turn_id`):
`request_player_roll(actor_id, kind: RollKind, context: Any) -> Event` :1886 ·
`roll(actor_id, kind, context, visibility="dm") -> Event` :1986 ·
`request_hero_initiative(hero_ids) -> Event` :2015 ·
`settle_initiative(run_id, hero_roll_id, hero_ids, hostile_ids) -> InitiativeResult` :2055 ·
`passive_check(actor_id, ability, dc, skill=None) -> bool` :2113 ·
`resolve_check(roll_id, dc) -> bool` :2349 · `resolve_save(roll_id, dc) -> bool` :2366 ·
`ask_player(run_id, text, options) -> Event` :2155 ·
`record_answer(run_id, text, question_id, turn_id) -> Event` :3744 ·
`record_player_action(run_id, text, turn_id, answers_question_id=None)` :3717 ·
`record_narration(run_id, text, turn_id, usage=None)` :3768 ·
`record_outcome(run_id, name, args, outcome, roll_ids=())` :3802 ·
`interact(actor_id, object_id, action, roll_id=None)` :2607 ·
`take(actor_id, item_id)` :2889 · `drop(...)` :2964 · `give(from_id, to_id, item_id)` :3035 ·
`use_exit(actor_id, exit_id)` :2409 · `enter_next_adventure(run_id)` :1427 ·
`set_hostility(actor_id, hostile)` :1303 · `leave_scene(actor_id)` :1363 ·
`finish_run(run_id, outcome)` :1488 — these nine return `MutationResult`
(`schemas.py:13`: `status`, `reason`, `event_ids`, `facts`) ·
`attack(actor_id, target_id, item_id=None, roll_id) -> AttackResult` :3165 (`schemas.py:540`, `hit_id`) ·
`damage(target_id, roll_id, hit_id, critical=False) -> DamageResult` :3412 (`schemas.py:558`) ·
`get_situation(run_id, recent_limit=…) -> Situation` :735 · `authored_check(entry)` :2103 ·
`is_down(obj)` :405. `RollKind` = `schemas.py:355`.

Frontend-read payload keys: `transcript.ts:137-153,185-198` reads
`roll_requested.context.ability`, `.skill`, `.dc` (defensively) and the
event's own `formula` as the chip's `notation`; `question.options` verbatim
(`transcript.ts:46`). So `request_roll` must pass
`context={"ability", "skill"?, "dc"?}` — the same dict shape
`request_player_roll` already stores (`schemas.py:382` types it `Any`).

Spent-roll scan: `_roll_already_spent` (`service.py:2197`) and `_consume_roll`
(:2214) still guard every roll-spending service and are exercised by
`tests/playthrough/test_acceptance_rolls_spent_once.py`. The old graph relies
on them. **Keep them**; this sprint adds the graph-level guarantee in
`ActionCursor`/`AwaitingRef` only. Removal belongs with the old flow (sprint 09).

Old `agent/state.py` keeps `DmState`/`DmContext` untouched → new files
`agent/flow_state.py` and `agent/operations.py`. Test helper: scratch DB via
`tests/game/conftest.py:12` (`playthrough_db`); handler tests otherwise use
fakes — `backend/tests/conftest.py` forbids a real engine.

## Work items

- WI1 `agent/flow_state.py`: every state type below, `OperationKind`,
  `Operation`/`OperationResult`, plus pure `close_turn_state(state)` and
  `end_combat_state(state)`; test serializes and restores an `AwaitingRef` and
  a `CombatCursor` through `JsonPlusSerializer` and asserts the two clearers.
- WI2 `agent/operations.py` part A: `OperationContext`, `validate_refs`,
  `execute_operation`, handlers for player input, checks and combat; tests for
  registry completeness and for a stale reference reaching no service.
- WI3 `agent/operations.py` part B: world and lifecycle handlers; test that one
  representative handler dispatches and returns its typed result, and that an
  action whose `AwaitingRef`/`ActionCursor` roll is already consumed cannot
  apply it twice.

WI2 and WI3 need WI1's `OperationKind`, `Operation`, `OperationResult`,
`GameFlowState`, `ActionCursor`, `CombatCursor`, `AwaitingRef` — land WI1 first;
WI2 and WI3 then run in parallel on one shared registry dict (WI2 creates the
file and the empty-but-typed registry, WI3 adds entries).

## Interfaces

```python
class OperationKind(str, Enum):  # 23 members, exactly intent §4
    RECORD_BEAT COMPLETE_ACTION CLOSE_TURN FINISH_RUN
    REQUEST_ROLL ROLL_PLAYER REQUEST_CHOICE ACCEPT_CHOICE
    ROLL_ACTOR PASSIVE_CHECK RESOLVE_CHECK RESOLVE_SAVE SETTLE_INITIATIVE
    INTERACT TAKE_ITEM DROP_ITEM GIVE_ITEM USE_EXIT ENTER_NEXT_ADVENTURE
    SET_HOSTILITY LEAVE_SCENE RESOLVE_ATTACK APPLY_DAMAGE   # value = lower name

@dataclass(frozen=True)
class TurnFrame: run_id: str; hero_id: str; turn_id: str
    input_kind: Literal["opening","action","roll","choice","retry"]
    text: str | None; status: Literal["open","closing","closed","terminal"]
    round_admitted: bool
@dataclass(frozen=True)
class Move: intent: str; refs: Mapping[str, str]        # role -> object id
@dataclass(frozen=True)
class OperationSpec: kind: OperationKind; payload: Mapping[str, Any]
@dataclass(frozen=True)
class ActionCursor: action_id: str; actor_id: str; kind: str
    plan: tuple[OperationSpec, ...]; step_index: int
    status: Literal["planned","reserved","complete","skipped"]
    roll_id: str | None; roll_consumed: bool          # AC4 ownership
@dataclass(frozen=True)
class CombatCursor: scene_id: str; order: tuple[str, ...]; index: int
    round: int; round_admitted: bool
    winning_side: Literal["hero","hostile"]
@dataclass(frozen=True)
class AwaitingRef: request_id: str; kind: Literal["roll","choice"]
    actor_id: str; public: Mapping[str, Any]           # see below
    consumer: OperationKind                            # private binding
    consumer_payload: Mapping[str, Any]                # private: dc, target_id, choice key -> object id
@dataclass(frozen=True)
class ReactionSpec: reaction_id: str; kind: str; payload: Mapping[str, Any]
@dataclass(frozen=True)
class NarrativeCursor: beat_id: str | None; draft: str | None; event_id: str | None
@dataclass(frozen=True)
class Usage: prompt_tokens: int; completion_tokens: int; cost: Decimal | None
@dataclass(frozen=True)
class ExecutionError: code: str; message: str; operation_id: str | None

@dataclass(frozen=True)
class Operation: operation_id: str; kind: OperationKind; payload: Mapping[str, Any]
@dataclass(frozen=True)
class OperationResult: operation_id: str
    status: Literal["ok","refused","error"]; reason: str | None
    event_ids: tuple[str, ...]; value: Mapping[str, Any]

class GameFlowState(TypedDict):
    turn: TurnFrame; move: Move | None; action: ActionCursor | None
    combat: CombatCursor | None; awaiting: AwaitingRef | None
    pending_hit_id: str | None; reactions: list[ReactionSpec]
    narrative: NarrativeCursor; effect: NextEffect | None
    result: OperationResult | None; usage: Usage | None; error: ExecutionError | None

StateDelta = dict[str, Any]          # partial GameFlowState keys only

@dataclass(frozen=True)
class OperationContext:
    db: AsyncSession; user_id: str; run_id: str; hero_id: str; situation: Situation

Handler = Callable[[OperationContext, Operation, GameFlowState],
                   Awaitable[tuple[OperationResult, StateDelta]]]
OPERATION_HANDLERS: dict[OperationKind, Handler]

async def execute_operation(ctx, op, state) -> tuple[OperationResult, StateDelta]
    # validate_refs(ctx.situation, op) first; on failure return
    # OperationResult(status="refused", reason="stale_reference") and {} —
    # no service call. Then OPERATION_HANDLERS[op.kind](ctx, op, state).

def validate_refs(situation: Situation, op: Operation) -> str | None
    # checks actor_id/target_id/object_id/item_id/exit_id/attack name/choice key
    # against situation.actors/.fixtures/.loose_items/.exits/hero inventory.
```

`request_roll` payload → `request_player_roll(context=public)` with
`public = {"ability": str, "skill": str | None, "dc": int | None}`; the event's
`formula` stays the service's own derivation. `request_choice` →
`ask_player(text, options)` with `options` verbatim. Both store the returned
event id as `AwaitingRef.request_id`; the answering `roll` / `player_action`
row is written by `roll_player` / `accept_choice` after the pause.
`NextEffect` is imported as a forward union placeholder here; sprint 07 owns it.

## Open questions

None product-visible.
