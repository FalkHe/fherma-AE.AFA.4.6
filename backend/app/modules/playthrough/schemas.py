from datetime import datetime
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
    carry this data instead."""

    abilities: Abilities
    race: str
    character_class: str
    background: str
    appearance: str


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
