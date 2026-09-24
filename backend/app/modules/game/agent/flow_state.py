"""The checkpoint-native state for the new flow (sprint 011/05, WI1): every
type `langgraph`'s own persistence walks through `JsonPlusSerializer`, frozen
dataclasses and `str`-valued enums throughout so a resumed turn restores
byte-for-byte. None of this is the database's own record of a run -- that
stays `playthrough.service`'s tables; what lives here is only the graph's
working memory for the turn and combat in flight.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, TypedDict


class OperationKind(StrEnum):
    RECORD_BEAT = "record_beat"
    COMPLETE_ACTION = "complete_action"
    CLOSE_TURN = "close_turn"
    FINISH_RUN = "finish_run"
    REQUEST_ROLL = "request_roll"
    ROLL_PLAYER = "roll_player"
    REQUEST_CHOICE = "request_choice"
    ACCEPT_CHOICE = "accept_choice"
    ROLL_ACTOR = "roll_actor"
    PASSIVE_CHECK = "passive_check"
    RESOLVE_CHECK = "resolve_check"
    RESOLVE_SAVE = "resolve_save"
    SETTLE_INITIATIVE = "settle_initiative"
    INTERACT = "interact"
    TAKE_ITEM = "take_item"
    DROP_ITEM = "drop_item"
    GIVE_ITEM = "give_item"
    USE_EXIT = "use_exit"
    ENTER_NEXT_ADVENTURE = "enter_next_adventure"
    SET_HOSTILITY = "set_hostility"
    LEAVE_SCENE = "leave_scene"
    RESOLVE_ATTACK = "resolve_attack"
    APPLY_DAMAGE = "apply_damage"


@dataclass(frozen=True)
class TurnFrame:
    run_id: str
    hero_id: str
    turn_id: str
    input_kind: Literal["opening", "action", "roll", "choice", "retry"]
    text: str | None
    status: Literal["open", "closing", "closed", "terminal"]
    round_admitted: bool


@dataclass(frozen=True)
class Move:
    intent: str
    refs: Mapping[str, str]


@dataclass(frozen=True)
class OperationSpec:
    kind: OperationKind
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ActionCursor:
    action_id: str
    actor_id: str
    kind: str
    plan: tuple[OperationSpec, ...]
    step_index: int
    status: Literal["planned", "reserved", "complete", "skipped"]
    roll_id: str | None
    roll_consumed: bool


@dataclass(frozen=True)
class CombatCursor:
    scene_id: str
    order: tuple[str, ...]
    index: int
    round: int
    round_admitted: bool
    winning_side: Literal["hero", "hostile"]


@dataclass(frozen=True)
class AwaitingRef:
    request_id: str
    kind: Literal["roll", "choice"]
    actor_id: str
    public: Mapping[str, Any]
    consumer: OperationKind
    consumer_payload: Mapping[str, Any]


@dataclass(frozen=True)
class ReactionSpec:
    reaction_id: str
    kind: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class NarrativeCursor:
    beat_id: str | None
    draft: str | None
    event_id: str | None


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    cost: Decimal | None


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str
    operation_id: str | None


@dataclass(frozen=True)
class Operation:
    operation_id: str
    kind: OperationKind
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class OperationResult:
    operation_id: str
    status: Literal["ok", "refused", "error"]
    reason: str | None
    event_ids: tuple[str, ...]
    value: Mapping[str, Any]


# Sprint 07 owns the shape of the graph's next-step effect; this is a
# forward-reference placeholder only, never resolved here.
NextEffect = Any


class GameFlowState(TypedDict):
    turn: TurnFrame
    move: Move | None
    action: ActionCursor | None
    combat: CombatCursor | None
    awaiting: AwaitingRef | None
    pending_hit_id: str | None
    reactions: list[ReactionSpec]
    narrative: NarrativeCursor
    effect: NextEffect | None
    result: OperationResult | None
    usage: Usage | None
    error: ExecutionError | None


StateDelta = dict[str, Any]


def close_turn_state(state: GameFlowState) -> StateDelta:
    """Clears every turn-local key at the end of a turn; `combat` and
    `turn` are left for the caller to set explicitly."""
    return {
        "awaiting": None,
        "move": None,
        "action": None,
        "result": None,
        "effect": None,
        "error": None,
        "reactions": [],
        "narrative": NarrativeCursor(beat_id=None, draft=None, event_id=None),
    }


def end_combat_state(state: GameFlowState) -> StateDelta:
    """Clears `combat` only."""
    return {"combat": None}
