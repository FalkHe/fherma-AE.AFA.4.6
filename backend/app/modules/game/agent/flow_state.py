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

    def __post_init__(self) -> None:
        # See `CombatCursor.__post_init__`: msgpack restores `plan` as a
        # list, normalised back here once.
        object.__setattr__(self, "plan", tuple(self.plan))


@dataclass(frozen=True)
class CombatCursor:
    scene_id: str
    order: tuple[str, ...]
    index: int
    round: int
    round_admitted: bool
    winning_side: Literal["hero", "hostile"]

    def __post_init__(self) -> None:
        # The checkpoint serializer has no tuple type -- msgpack restores
        # `order` as a list -- so it is normalised back here, once, rather
        # than at every call site that reads a restored `CombatCursor`.
        object.__setattr__(self, "order", tuple(self.order))


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

    def __post_init__(self) -> None:
        # See `CombatCursor.__post_init__`.
        object.__setattr__(self, "event_ids", tuple(self.event_ids))


# `effects.NextEffect` (sprint 011/07) owns the real shape -- a union that
# reaches back up through `decisions.DecisionRequest`, this module's own
# `Operation` and `narration.BeatRequest`, which would circularly import
# this module. `GameFlowState.effect` keeps the untyped placeholder; only
# `TYPE_CHECKING` callers (none yet) should import the real alias.
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
        "pending_hit_id": None,
        "result": None,
        "usage": None,
        "effect": None,
        "error": None,
        "reactions": [],
        "narrative": NarrativeCursor(beat_id=None, draft=None, event_id=None),
    }


def end_combat_state(state: GameFlowState) -> StateDelta:
    """Clears `combat` only."""
    return {"combat": None}
