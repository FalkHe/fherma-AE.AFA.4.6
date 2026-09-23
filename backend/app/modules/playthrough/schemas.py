from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import CamelModel
from app.modules.character.schemas import SheetItem
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


class CampaignRunSummaryRead(CamelModel):
    """One `GET /runs` row (WI1, AC1/AC2): the run's own facts alongside
    its pinned campaign's copy, enriched with counts no single table
    carries. `campaignTitle`/`campaignSummary`/`adventuresTotal` are
    `None` and `unavailable` is `true` when the pinned campaign or
    version can no longer be loaded -- `adventuresCompleted` and
    `playerCount` stay counted either way, since both come from this
    run's own rows, not from content."""

    id: str
    campaign_id: str
    status: str
    created_at: datetime
    campaign_title: str | None
    campaign_summary: str | None
    adventures_completed: int
    adventures_total: int | None
    player_count: int
    unavailable: bool


class Ability(CamelModel):
    """One ability score and its signed modifier, on the wire (WI1, sprint
    010/05) -- `modifier` is `dice.ability_modifier(score)`, computed once
    by `service.character_read` rather than left for a client to derive;
    it may be zero or negative."""

    score: int
    modifier: int


class CharacterAbilities(CamelModel):
    """The character's six ability scores, each an `Ability` (WI1, sprint
    010/05) -- the wire twin of `content.schemas.Abilities`, which carries
    the bare scores alone."""

    strength: Ability
    dexterity: Ability
    constitution: Ability
    intelligence: Ability
    wisdom: Ability
    charisma: Ability


class Item(CamelModel):
    """One carried instance, on the wire (WI1, sprint 010/05) -- `id`,
    `name` only. One entry per unit of quantity: identical items arrive as
    separate rows here, and the client groups them, never this shape."""

    id: str
    name: str


class CharacterRead(CamelModel):
    """The character, on the wire -- `id, name, currentHp, maxHp,
    armourClass, race, characterClass, level, appearance, abilities,
    backstory, items` and nothing else (I2; sprint 009-07 adds the four
    card facts -- ← research Decision 5; WI1 sprint 010/05 widens this to
    the one hero shape shared by every read that already returns one --
    the run overview, the `POST …/character` route and intent 009's
    character card): no full state, no keys, no ownership, and no
    `isAlive`/`down` (← D7 keeps conditions off the card). `race`/
    `characterClass`/`level`/`appearance`/`abilities`/`backstory` are read
    off the object's `state` column (`CharacterState`), never stored as
    columns of their own -- `backstory` is `CharacterState.background`
    under its wire name. `items` is one entry per unit of carried
    quantity, supplied by the caller rather than queried inside
    `character_read`."""

    id: str
    name: str
    current_hp: int
    max_hp: int
    armour_class: int
    race: str
    character_class: str
    level: int
    abilities: CharacterAbilities
    appearance: str
    backstory: str
    items: list[Item]


class CampaignRunMemberRead(CamelModel):
    """One seat in `GET /runs/{runId}/overview` (WI2, AC3; sprint 009-07 --
    the character card rides here whole) -- `userId, username, role, ready,
    character`. `ready` is `character is not None`; a non-player creature
    never counts, since only a member's own character carries
    `objects.member_id`."""

    user_id: str
    username: str
    role: str
    ready: bool
    character: CharacterRead | None


class CampaignRunAdventureRead(CamelModel):
    """One of the campaign's adventures, in the campaign's own order
    (WI2, AC3) -- `id, title, introExcerpt, status`. `id` is the campaign's
    adventure id, never the `adventure_runs` row id. `status` is
    `done`/`active`/`unplayed`, mapped from the matching `adventure_runs`
    row's own `status` (`completed`/`active`) or its absence."""

    id: str
    title: str
    intro_excerpt: str
    status: str


class CampaignRunOverviewRead(CamelModel):
    """`GET /runs/{runId}/overview`'s whole answer (WI2, AC3): the run
    itself, its members and its adventures, together -- so an overview
    screen never has to make three calls where one now does. Mirrors
    `CampaignRunSummaryRead`'s unavailable-content contract (AC2): a run
    whose pinned campaign or version no longer loads answers with
    `campaignTitle`/`campaignSummary` `None`, `unavailable` `True` and
    `adventures` empty; `members` is unaffected, since it never reads
    content."""

    id: str
    campaign_id: str
    content_version: str
    title: str | None
    status: str
    created_at: datetime
    campaign_title: str | None
    campaign_summary: str | None
    unavailable: bool
    members: list[CampaignRunMemberRead]
    adventures: list[CampaignRunAdventureRead]


class TableAdventure(CamelModel):
    """The current adventure, on the play screen's own read (WI2, sprint
    010/05, I1) -- `id` is the campaign's own adventure id (content),
    `runId` the `adventure_runs` row id, alongside `title` and `status`
    (`"active"`/`"completed"`, `adventure_runs.status` verbatim -- `use_exit`
    marks a row `completed` without clearing anyone's position, so a
    finished adventure still reads here rather than vanishing)."""

    id: str
    run_id: str
    title: str
    status: Literal["active", "completed"]


class TableScene(CamelModel):
    """The scene the acting hero stands in, on the play screen's own read
    (WI2, sprint 010/05, I1) -- `id, name` and nothing else. `name` is the
    pinned scene's own `title`."""

    id: str
    name: str


class TableRead(CamelModel):
    """The play screen's whole answer, in one call (WI2, sprint 010/05,
    I1/I2): the run, its pinned campaign's title, the current adventure and
    scene, and every seated hero -- serves the screen's header, its party
    rail and its full character sheet alike.

    `adventure`/`scene` are anchored on the **acting caller's own hero**
    (its `objects.adventure_run_id`/`scene_id`), never on whichever
    `adventure_runs` row happens to read `status == 'active'` -- `use_exit`
    completes a row without clearing anyone's position, so an active-row
    anchor would blank the header at exactly the moment an adventure ends
    (← research). Both are `None` when no adventure was entered yet, the
    caller has no hero on this run, or the pinned content no longer loads.
    `campaignTitle` is `None` exactly when the pinned content no longer
    loads (`_load_pinned` -> `None`), independent of either. `heroes` is
    every member's character (`CharacterRead`, WI1), ordered by member id,
    empty before any character has been created -- a member with no
    character yet contributes no row here, unlike `CampaignRunOverviewRead`
    which carries one row per member either way."""

    run_id: str
    run_title: str | None
    run_status: str
    campaign_title: str | None
    adventure: TableAdventure | None
    scene: TableScene | None
    heroes: list[CharacterRead]


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
    plain JSONB tracks no in-place key set.

    `level`, `alignment`, `speed`, `proficiency_bonus`, `saving_throws`,
    `skills` and `equipment` (sprint 009-02, WI2, AC4) carry a built
    character's full sheet alongside `abilities`/`race`/`character_class`
    -- every field defaults so the seed hero's path writes exactly what
    it wrote before. `background` keeps its name here and takes a built
    sheet's own `backstory`."""

    abilities: Abilities
    race: str
    character_class: str
    background: str
    appearance: str
    down: bool = False
    level: int = 1
    alignment: str | None = None
    speed: int = 30
    proficiency_bonus: int = 2
    saving_throws: list[str] = []
    skills: list[str] = []
    equipment: list[SheetItem] = []


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
# place these sixteen names are declared: the twelve settled in intent 005,
# plus four added by intent 010 sprint 04 (`item_moved`, `hp_changed`,
# `way_opened`, `rule_looked_up`) per that sprint's plan, interface I1.

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
    """`scene_entered` -- a move within an adventure. `scene_title` (sprint
    010/04) is read from the destination's pinned content by the mechanic
    that writes this event; it stays optional since older rows, written
    before this field existed, carry none."""

    adventure_run_id: str
    scene_id: str
    scene_title: str | None = None


class AdventurePayload(EventPayload):
    """`adventure_started` / `adventure_completed` -- share one shape."""

    adventure_run_id: str


class NoticePayload(EventPayload):
    """`system` / `error` / `warning` -- share one shape. No field list in
    `decisions/mechanics.md`; settled by research."""

    message: str
    details: dict[str, Any] | None = None


class ItemMovedPayload(EventPayload):
    """`item_moved` (sprint 010/04, I1) -- a hero takes, drops or gives an
    item, `movement` naming which. `to_id`/`to_name` name the receiver and
    are only ever set for `movement="given"`; `take`/`drop` leave both
    `None`."""

    movement: Literal["taken", "dropped", "given"]
    actor_id: str
    actor_name: str
    item_id: str
    item_name: str
    to_id: str | None = None
    to_name: str | None = None


class HpChangedPayload(EventPayload):
    """`hp_changed` (sprint 010/04, I1) -- a target's hit points move from
    `before` to `after`, alongside `max_hp` and the two derived flags
    `alive`/`down` the mechanic already holds when it writes this."""

    target_id: str
    target_name: str
    before: int
    after: int
    max_hp: int
    alive: bool
    down: bool


class WayOpenedPayload(EventPayload):
    """`way_opened` (sprint 010/04, I1) -- an interaction with a fixture
    succeeded and changed something. `action` is the authored action
    verbatim (e.g. `"pick_lock"`), never the model's own words; written on
    success only -- a failed check changed nothing and leaves no row."""

    actor_id: str
    actor_name: str
    object_id: str
    object_name: str
    action: str


class RuleLookedUpPayload(EventPayload):
    """`rule_looked_up` (sprint 010/04, I1) -- `topic` is the best match's
    full `heading_path` (e.g. `"Chapter 7 › Using Ability Scores ›
    Hiding"`), never the rules text and never the model's own query."""

    topic: str


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
    "item_moved": ItemMovedPayload,
    "hp_changed": HpChangedPayload,
    "way_opened": WayOpenedPayload,
    "rule_looked_up": RuleLookedUpPayload,
}
