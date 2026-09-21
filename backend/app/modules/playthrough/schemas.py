from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import CamelModel
from app.modules.content.schemas import Abilities


class StartCampaignRunRequest(CamelModel):
    campaign_id: str = Field(min_length=1, max_length=64)


class CampaignRunRead(CamelModel):
    """The run row, not its state -- `id, campaignId, contentVersion,
    title, status, createdAt` and nothing else (I2)."""

    id: str
    campaign_id: str
    content_version: str
    title: str | None
    status: str
    created_at: datetime


class RenameCampaignRunRequest(CamelModel):
    title: str = Field(min_length=1, max_length=120)


class EventRead(CamelModel):
    """One transcript entry, on the wire -- `id, type, turnId, payload,
    createdAt` and nothing else (WI2): no visibility (a read only ever
    carries `player` rows), no cost, no run id. `payload` is already
    camelCase in storage (`append_event` writes it `by_alias=True`) and
    passes through unmapped."""

    id: str
    type: str
    turn_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class EventsRead(CamelModel):
    """The events route's whole answer (WI2, AC4b) -- the caller's
    player-visible transcript alongside `awaiting`, `service.list_events`
    and `service.get_awaiting`'s answers for the same run, read together
    so a client is never left asking twice about the same open turn.
    `awaiting` is one of `"none"`, `"roll:<id>"` or `"answer:<id>"`."""

    events: list[EventRead]
    awaiting: str


class NarrationRead(CamelModel):
    """One `narration` event, read by meaning or by recency (WI1/WI2,
    sprint 006/02) -- `id, createdAt, text` and nothing else: no distance,
    no payload, no vector. Deliberately not `EventRead`, which is the
    transcript route's own wire model and carries `type`/`turnId`/
    `payload`."""

    id: str
    created_at: datetime
    text: str


class AdventureRunRead(CamelModel):
    """One adventure run, on the wire -- `id, adventureId, status,
    startedAt` and nothing else (I1): the adventure run's internals
    (`campaignRunId`, `completedAt`, `updatedAt`) stay internal."""

    id: str
    adventure_id: str
    status: str
    started_at: datetime


class CharacterRead(CamelModel):
    """The character, on the wire -- `id, name, currentHp, maxHp,
    armourClass` and nothing else (I2): no state, no keys, no ownership."""

    id: str
    name: str
    current_hp: int
    max_hp: int
    armour_class: int


class CharacterState(BaseModel):
    """The character's `state` column (I5), written whole from the seed
    sheet and never mutated in place -- a plain `BaseModel`, not a
    `CamelModel`: this is storage, not wire shape. Carried items keep the
    column's `{}` default; only the character has no `template_id` to
    carry this data instead.

    `down` (sprint 09, WI1, AC2) starts `False` at character creation and
    is set `True` when `damage` brings the character to 0 hp -- a
    character with a member stays `is_alive=True` at zero, this field
    alone records that it is down. The column is always reassigned whole
    from this model (`model_copy(update=...)`), never mutated in place:
    plain JSONB tracks no in-place key set."""

    abilities: Abilities
    race: str
    character_class: str
    background: str
    appearance: str
    down: bool = False


class TurnCost(BaseModel):
    """One turn's `SUM(cost_usd)` (WI1, AC3) -- a plain `BaseModel`, never a
    `CamelModel`: this is `run_cost`'s own return shape, read only by the
    `app playthrough cost` command, never serialised onto the wire and never
    returned from a route (← D14). `turn_id` is `None` for events written
    with no turn; an all-`NULL` group's sum is normalised to
    `Decimal("0.000000")` rather than `None`."""

    turn_id: str | None
    total: Decimal


class RunCost(BaseModel):
    """A run's cost, whole and by turn (WI1, AC3) -- `total` is the sum
    across every turn (including the untagged one), never a separate
    query. `turns` is ordered with the `None` turn last. Plain `BaseModel`,
    never a wire schema."""

    total: Decimal
    turns: list[TurnCost]


# --- Event payloads (WI1, I2) ------------------------------------------------
#
# One `CamelModel` per shape in `docs/intents/005-game-state-services/decisions/
# mechanics.md § "Shapes carried in events.payload"`, each `extra="forbid"` so
# a payload carrying an unexpected field is refused rather than silently
# stored. Four shapes have no field list there and were settled by research:
# `narration` (`text` only) and one `NoticePayload` shared by `system`,
# `error` and `warning` (`message`, optional `details`). `EVENT_PAYLOADS`
# is the registry `append_event` validates every write against -- the only
# place these twelve names are declared.

RollKind = Literal["attack", "damage", "ability_check", "saving_throw", "initiative", "custom"]


class EventPayload(CamelModel):
    """Base for every `events.payload` shape: camelCase on the wire, stored
    the same way (`model_dump(by_alias=True)`), and closed to unknown
    fields -- a payload the caller got wrong is refused, not stored partway.
    """

    model_config = ConfigDict(extra="forbid")


class NarrationPayload(EventPayload):
    """`narration` -- prose only. No field list in `decisions/mechanics.md`;
    settled by research."""

    text: str


class PlayerActionPayload(EventPayload):
    """`player_action` -- the player's free-form action, optionally
    answering an open `question` event."""

    text: str
    answers_question_id: str | None = None


class RollRequestedPayload(EventPayload):
    """`roll_requested` -- the roll the player is asked to make.

    `context` is free-form (`decisions/mechanics.md` gives it no shape of
    its own -- the structured `{target_id?, item_id?, ability?, skill?}`
    is the *mechanic's* argument, not necessarily what ends up stored), so
    it is typed `Any` rather than constrained to a dict.
    """

    kind: RollKind
    actor_id: str
    formula: str
    context: Any


class RollPayload(EventPayload):
    """`roll` -- a resolved roll, requested or not (`request_id` is only set
    when it resolves a `roll_requested`)."""

    request_id: str | None = None
    kind: RollKind
    actor_id: str
    formula: str
    faces: list[int]
    modifier: int
    total: int


class QuestionPayload(EventPayload):
    """`question` -- put to the player; the next `player_action` answers
    it."""

    text: str
    options: list[str]


class ToolCallPayload(EventPayload):
    """`tool_call` -- one mechanic invocation, ok or refused, with the roll
    ids it consumed."""

    name: str
    args: dict[str, Any]
    roll_ids: list[str]
    result: Literal["ok", "refused"]
    outcome: dict[str, Any]


class SceneEnteredPayload(EventPayload):
    """`scene_entered` -- a move within an adventure."""

    adventure_run_id: str
    scene_id: str


class AdventurePayload(EventPayload):
    """`adventure_started` / `adventure_completed` -- share one shape."""

    adventure_run_id: str


class NoticePayload(EventPayload):
    """`system` / `error` / `warning` -- share one shape. No field list in
    `decisions/mechanics.md`; settled by research."""

    message: str
    details: dict[str, Any] | None = None


EVENT_PAYLOADS: dict[str, type[EventPayload]] = {
    "narration": NarrationPayload,
    "player_action": PlayerActionPayload,
    "roll_requested": RollRequestedPayload,
    "roll": RollPayload,
    "question": QuestionPayload,
    "tool_call": ToolCallPayload,
    "scene_entered": SceneEnteredPayload,
    "adventure_started": AdventurePayload,
    "adventure_completed": AdventurePayload,
    "system": NoticePayload,
    "error": NoticePayload,
    "warning": NoticePayload,
}
