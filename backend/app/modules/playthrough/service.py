"""Starting, listing and reading a campaign run; giving it its character;
renaming and archiving it; appending to its transcript.

Imported as a module (`from app.modules.playthrough import service`) and
called `service.f(...)` -- never import the functions by name, the test
suite's monkeypatching depends on it (AGENTS.md).
"""

import asyncio
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.core.llm import service as llm_service
from app.core.llm.service import Usage
from app.core.settings import get_settings
from app.modules.character.schemas import CharacterSheet
from app.modules.content import service as content_service
from app.modules.content.errors import ContentError, ContentNotFoundError
from app.modules.content.schemas import (
    Abilities,
    AbilityName,
    Attack,
    CreatureTemplate,
    FixtureCheck,
    FixtureTemplate,
    ItemTemplate,
    LoadedCampaign,
    ObjectTemplate,
    Secret,
    SeedCharacter,
)
from app.modules.playthrough import dice
from app.modules.playthrough import situation as situation_types
from app.modules.playthrough.errors import (
    AdventureActiveError,
    AdventureExhaustedError,
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    CharacterExistsError,
    CharacterNotFoundError,
    GameObjectNotFoundError,
    HitNotUsableError,
    InvalidDcError,
    InvalidEventPayloadError,
    InvalidRunStatusError,
    ObjectNotReachableError,
    RollNotFoundError,
    RollNotUsableError,
    RollRequestNotFoundError,
    RunArchivedError,
    SituationError,
)
from app.modules.playthrough.models import (
    EMBEDDING_WIDTH,
    AdventureRun,
    CampaignRun,
    CampaignRunMember,
    Event,
    GameObject,
)
from app.modules.playthrough.schemas import (
    EVENT_PAYLOADS,
    AttackResult,
    CampaignRunAdventureRead,
    CampaignRunMemberRead,
    CampaignRunOverviewRead,
    CampaignRunSummaryRead,
    CharacterAbilities,
    CharacterRead,
    CharacterState,
    DamageResult,
    InitiativeResult,
    Item,
    MutationResult,
    NarrationRead,
    RollKind,
    RollPayload,
    RollRequestedPayload,
    RunCost,
    TableAdventure,
    TableRead,
    TableScene,
    TurnCost,
)
from app.modules.users.models import User

logger = structlog.get_logger()

_ZERO_COST = Decimal("0.000000")

_EVENT_VISIBILITIES = frozenset({"player", "dm"})

# The SRD's own difficulty table (← D6); sprint 07a raised the authoring
# floor to 5 to match, so both ends of the system now agree.
_MIN_DC = 5
_MAX_DC = 30


def _build_object(
    *,
    campaign_run_id: str,
    template: ObjectTemplate,
    instance_key: str,
    source_adventure_id: str | None = None,
    source_scene_id: str | None = None,
) -> GameObject:
    """One `objects` row for a placed or carried instance of `template`.

    Position (`adventure_run_id`, `scene_id`) and `member_id` all stay
    NULL -- nothing is positioned at start (← D3). The id is generated here
    rather than left to the column default, because a placement's carried
    children need it (`owner_object_id`) before the placement row has gone
    through a flush. `source_adventure_id`/`source_scene_id` default to
    `None` for `create_character`'s carried items -- they are seed
    inventory, not sourced from any adventure or scene.
    """
    obj = GameObject(
        id=generate_id(),
        campaign_run_id=campaign_run_id,
        kind=template.kind,
        template_id=template.id,
        instance_key=instance_key,
        name=template.name,
        source_adventure_id=source_adventure_id,
        source_scene_id=source_scene_id,
    )
    if template.kind == "creature":
        obj.max_hp = template.stat_block.max_hp
        obj.current_hp = template.stat_block.max_hp
        obj.armour_class = template.stat_block.armour_class
        obj.is_alive = True
    return obj


def _build_run_objects(
    loaded: LoadedCampaign, *, campaign_run_id: str
) -> tuple[list[GameObject], list[GameObject]]:
    """Every placement and carried instance the pinned campaign declares,
    as two lists in authored order: placements (id already set, so a
    carried child can reference it) and their carried children
    (`owner_object_id` set).

    A carried instance belongs to a placement *instance*, not to the
    placement itself: a `count: 3` placement that carries something
    yields three carried rows, one per placement instance, each owned by
    its own copy. `instance_key` follows 003 ASSUMPTION 9 verbatim.
    """
    placement_rows: list[GameObject] = []
    carried_rows: list[GameObject] = []

    for adventure_id in loaded.campaign.adventures:
        adventure = loaded.adventures[adventure_id]
        for scene in adventure.scenes:
            for placement in scene.placements:
                template = loaded.object_templates[placement.template]
                for ordinal in range(1, placement.count + 1):
                    instance_key = f"{adventure_id}:{scene.id}:{placement.template}:{ordinal}"
                    row = _build_object(
                        campaign_run_id=campaign_run_id,
                        template=template,
                        instance_key=instance_key,
                        source_adventure_id=adventure_id,
                        source_scene_id=scene.id,
                    )
                    placement_rows.append(row)

                    for carried in placement.carries:
                        carried_template = loaded.object_templates[carried.template]
                        for carried_ordinal in range(1, carried.count + 1):
                            carried_key = f"{instance_key}/{carried.template}:{carried_ordinal}"
                            carried_row = _build_object(
                                campaign_run_id=campaign_run_id,
                                template=carried_template,
                                instance_key=carried_key,
                                source_adventure_id=adventure_id,
                                source_scene_id=scene.id,
                            )
                            carried_row.owner_object_id = row.id
                            carried_rows.append(carried_row)

    return placement_rows, carried_rows


async def _require_member(db: AsyncSession, *, run_id: str, user_id: str) -> CampaignRunMember:
    """The first call in every function that takes a `run_id`.

    One query: an unknown run and someone else's run both come back as no
    row, so both raise the identical `CampaignRunNotFoundError` (← D12) --
    there is no branch that could tell them apart.
    """
    stmt = select(CampaignRunMember).where(
        CampaignRunMember.campaign_run_id == run_id,
        CampaignRunMember.user_id == user_id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if member is None:
        raise CampaignRunNotFoundError(run_id)
    return member


async def start_campaign_run(db: AsyncSession, *, user_id: str, campaign_id: str) -> CampaignRun:
    """Pins the content version, creates the run and its owning
    membership, and instantiates every object the pinned campaign
    declares, all unpositioned. One commit; no event appended.
    """
    try:
        content_version = content_service.list_versions(campaign_id)[-1]
        loaded = content_service.load_campaign(campaign_id, content_version)
    except ContentNotFoundError as exc:
        raise CampaignNotFoundError(campaign_id) from exc

    run = CampaignRun(campaign_id=campaign_id, content_version=content_version)

    try:
        db.add(run)
        await db.flush()

        db.add(CampaignRunMember(campaign_run_id=run.id, user_id=user_id, role="owner"))
        await db.flush()

        # Two flushes, placements before carries: there is no ORM
        # relationship between rows of `objects`, so nothing else orders
        # the inserts, and a carried row's `owner_object_id` FK needs its
        # placement already written.
        placement_rows, carried_rows = _build_run_objects(loaded, campaign_run_id=run.id)
        db.add_all(placement_rows)
        await db.flush()

        db.add_all(carried_rows)
        await db.flush()

        await db.commit()
    except IntegrityError as exc:
        # `(campaign_run_id, instance_key)` is unique *within one run*: it
        # guarantees this run's world is instantiated exactly once, not
        # that the campaign can only ever be started once -- two starts of
        # the same campaign by the same user get two distinct runs, each
        # with its own random id and its own full object set. This only
        # fires if instantiation is ever attempted twice into the *same*
        # run; there is no pre-check.
        await db.rollback()
        raise CampaignRunExistsError(campaign_id) from exc

    await db.refresh(run)
    return run


async def list_campaign_runs(db: AsyncSession, *, user_id: str) -> list[CampaignRun]:
    """Every run the caller is a member of, newest first (`id DESC` --
    ULIDs are creation-ordered), archived included.
    """
    stmt = (
        select(CampaignRun)
        .join(CampaignRunMember, CampaignRunMember.campaign_run_id == CampaignRun.id)
        .where(CampaignRunMember.user_id == user_id)
        .order_by(CampaignRun.id.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _load_pinned(run: CampaignRun) -> LoadedCampaign | None:
    """`run`'s pinned campaign, reloaded -- or `None` when the pinned
    `(campaign_id, content_version)` no longer loads. Catches
    `ContentError` alone, logging a warning; anything else (a bug, not a
    missing-content fact) travels to the caller.
    """
    try:
        return content_service.load_campaign(run.campaign_id, run.content_version)
    except ContentError as exc:
        logger.warning("playthrough_content_unavailable", run_id=run.id, error=str(exc))
        return None


async def list_run_summaries(db: AsyncSession, *, user_id: str) -> list[CampaignRunSummaryRead]:
    """The caller's runs, enriched for a picker screen (WI1, AC1/AC2):
    newest first, archived included -- the same rows and order as
    `list_campaign_runs` -- each carrying its pinned campaign's title and
    summary, how many of its adventures are done versus the campaign's
    total, and how many players are seated, or `unavailable=True` with no
    campaign copy when the pinned content no longer loads.

    Two grouped counts, both keyed by `campaign_run_id`: completed rows in
    `adventure_runs` and rows in `campaign_run_members`. `_load_pinned` is
    cached per `(campaign_id, content_version)`, so two runs of the same
    campaign at the same version load its content once. Reads only: no
    commit, no status change, no event.
    """
    runs = await list_campaign_runs(db, user_id=user_id)
    if not runs:
        return []

    run_ids = [run.id for run in runs]

    completed_stmt = (
        select(AdventureRun.campaign_run_id, func.count())
        .where(AdventureRun.campaign_run_id.in_(run_ids), AdventureRun.status == "completed")
        .group_by(AdventureRun.campaign_run_id)
    )
    completed_result = await db.execute(completed_stmt)
    completed_counts = dict(completed_result.all())

    member_stmt = (
        select(CampaignRunMember.campaign_run_id, func.count())
        .where(CampaignRunMember.campaign_run_id.in_(run_ids))
        .group_by(CampaignRunMember.campaign_run_id)
    )
    member_result = await db.execute(member_stmt)
    member_counts = dict(member_result.all())

    content_by_pin: dict[tuple[str, str], LoadedCampaign | None] = {}
    summaries: list[CampaignRunSummaryRead] = []
    for run in runs:
        pin = (run.campaign_id, run.content_version)
        if pin not in content_by_pin:
            content_by_pin[pin] = _load_pinned(run)
        loaded = content_by_pin[pin]

        summaries.append(
            CampaignRunSummaryRead(
                id=run.id,
                campaign_id=run.campaign_id,
                status=run.status,
                created_at=run.created_at,
                campaign_title=loaded.campaign.title if loaded is not None else None,
                campaign_summary=loaded.campaign.summary if loaded is not None else None,
                adventures_completed=completed_counts.get(run.id, 0),
                adventures_total=len(loaded.campaign.adventures) if loaded is not None else None,
                player_count=member_counts.get(run.id, 0),
                unavailable=loaded is None,
            )
        )

    return summaries


async def _get_run(db: AsyncSession, run_id: str) -> CampaignRun:
    """The run row itself. Most callers reach this once membership is
    already confirmed -- there an unknown id is only reachable if the run
    was deleted between the membership check and here. The operator reads
    (`recap`, `recall`, sprint 006/02) call this alone, with no membership
    check at all, so it doubles as their entire existence gate. Either
    way, a missing id raises `CampaignRunNotFoundError`.
    """
    result = await db.execute(select(CampaignRun).where(CampaignRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise CampaignRunNotFoundError(run_id)
    return run


async def get_run(db: AsyncSession, run_id: str) -> CampaignRun:
    """The run row itself without a membership gate."""
    return await _get_run(db, run_id)


async def get_latest_campaign_run_id(db: AsyncSession) -> str | None:
    """The most recently created campaign run id, or None if no runs exist."""
    stmt = (
        select(CampaignRun.id)
        .order_by(CampaignRun.created_at.desc(), CampaignRun.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _require_writable(run: CampaignRun) -> None:
    """Raises `RunArchivedError` when `run` is archived.

    Called first by every write against an existing run: rename and
    character creation here, sprint 06's `enter_adventure` later. There is
    no unarchive, so this is the run's entire shelf life in one check.
    """
    if run.status == "archived":
        raise RunArchivedError(run.id)


async def get_campaign_run(db: AsyncSession, *, user_id: str, run_id: str) -> CampaignRun:
    """One run, gated by membership -- a foreign or unknown id both raise
    `CampaignRunNotFoundError` out of `_require_member`.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    return await _get_run(db, run_id)


def _excerpt(text: str, limit: int = 200) -> str:
    """`text` unchanged when it already fits `limit`; otherwise cut at
    `limit`, dropped back to the last space so the cut never lands
    mid-word (kept as-is when there is no space to drop back to),
    `rstrip()`ped and closed with `"…"` (WI2, I2)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space != -1:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def _character_abilities(scores: Abilities) -> CharacterAbilities:
    """Every ability score paired with its signed modifier (WI1, sprint
    010/05), through `dice.ability_modifier` -- the one formula, computed
    once here rather than left for a client to derive."""
    return CharacterAbilities.model_validate(
        {
            name: {"score": score, "modifier": dice.ability_modifier(score)}
            for name, score in scores.model_dump().items()
        }
    )


def is_down(obj: GameObject) -> bool:
    """True when `obj` cannot act, or be acted on as a living target (sprint
    011/02, WI3, I3): any object with `is_alive == False` -- a dead
    creature, the only way a non-member ever reaches this -- or a member's
    own character whose `state` was written `down=True` at 0 hp
    (`damage`'s own write). Only a character's `state` ever carries `down`;
    a template-less monster/npc's `is_alive` already says everything there
    is to say, so `member_id is None` short-circuits to that alone.

    The one rule `damage` writes by and every read (`describe_scene_
    creatures`, `character_read`, `resolve_actor_ref`, the live-creature
    hint, `attack`'s own refusal) checks by -- HP, `is_alive` and `down`
    agree everywhere (intent §1.5)."""
    if not obj.is_alive:
        return True
    if obj.member_id is None:
        return False
    return bool(obj.state.get("down", False))


def character_read(obj: GameObject, *, items: Sequence[GameObject] = ()) -> CharacterRead:
    """`CharacterRead` from a character `GameObject` (sprint 009-07, ←
    research Decision 5; widened WI1 sprint 010/05 into the one hero shape
    shared by every read that already returns one) -- the four card facts
    (`race`, `characterClass`, `level`, `appearance`), the six ability
    scores and `backstory` (`CharacterState.background`, under its wire
    name) are read off `obj.state` through `CharacterState`, the fighting
    stats off the object's own columns. `items` are the carried rows a
    caller already fetched -- one `Item` per row, never queried here, so
    `get_run_overview` can supply every hero's items from one grouped
    query rather than one per hero. Shared by `get_run_overview`'s member
    list and the `POST …/character` route, so both answer the same
    shape."""
    state = CharacterState.model_validate(obj.state)
    return CharacterRead(
        id=obj.id,
        name=obj.name,
        current_hp=obj.current_hp,
        max_hp=obj.max_hp,
        armour_class=obj.armour_class,
        race=state.race,
        character_class=state.character_class,
        level=state.level,
        abilities=_character_abilities(state.abilities),
        appearance=state.appearance,
        backstory=state.background,
        items=[Item(id=item.id, name=item.name) for item in items],
        down=is_down(obj),
    )


async def get_run_overview(
    db: AsyncSession, *, user_id: str, run_id: str
) -> CampaignRunOverviewRead:
    """One aggregate overview for a run screen (WI2, AC3): the run itself,
    every member with username, role, a `ready` flag and the character
    card when one exists, and the campaign's adventures in the campaign's
    own order with a clipped intro and a done/active/unplayed status.

    Gated by membership exactly like every other read (`_require_member`
    then `_get_run`). Members come from one query joining
    `campaign_run_members` to `users` and outer-joining `objects` on
    `member_id == member.id AND kind == 'creature'` -- a non-player
    creature's `member_id` is always `None`, so it can never supply a
    character (← research). Every character's carried items (WI1, sprint
    010/05) come from one further query, grouped in Python by
    `owner_object_id` -- one query for every hero on the run, never one
    per hero -- skipped outright when no member has a character.
    Adventures come from `_load_pinned(run)`
    (`None` means unavailable, AC2's twin) paired with this run's own
    `adventure_runs` rows. Reads only: no commit, no status change, no
    event.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)

    member_stmt = (
        select(CampaignRunMember, User.username, GameObject)
        .join(User, User.id == CampaignRunMember.user_id)
        .outerjoin(
            GameObject,
            (GameObject.member_id == CampaignRunMember.id) & (GameObject.kind == "creature"),
        )
        .where(CampaignRunMember.campaign_run_id == run_id)
        .order_by(CampaignRunMember.id)
    )
    member_result = await db.execute(member_stmt)
    member_rows = member_result.all()

    character_ids = [
        character_object.id
        for _, _, character_object in member_rows
        if character_object is not None
    ]
    items_by_owner: dict[str, list[GameObject]] = {}
    if character_ids:
        items_stmt = (
            select(GameObject)
            .where(GameObject.kind == "item", GameObject.owner_object_id.in_(character_ids))
            .order_by(GameObject.instance_key)
        )
        items_result = await db.execute(items_stmt)
        for item in items_result.scalars().all():
            items_by_owner.setdefault(item.owner_object_id, []).append(item)

    members = [
        CampaignRunMemberRead(
            user_id=member.user_id,
            username=username,
            role=member.role,
            ready=character_object is not None,
            character=(
                character_read(character_object, items=items_by_owner.get(character_object.id, []))
                if character_object is not None
                else None
            ),
        )
        for member, username, character_object in member_rows
    ]

    adventure_run_stmt = select(AdventureRun).where(AdventureRun.campaign_run_id == run_id)
    adventure_run_result = await db.execute(adventure_run_stmt)
    status_by_adventure_id = {
        row.adventure_id: row.status for row in adventure_run_result.scalars().all()
    }

    loaded = _load_pinned(run)
    adventures: list[CampaignRunAdventureRead] = []
    if loaded is not None:
        for adventure_id, adventure in loaded.adventures.items():
            row_status = status_by_adventure_id.get(adventure_id)
            if row_status == "completed":
                status = "done"
            elif row_status == "active":
                status = "active"
            else:
                status = "unplayed"
            adventures.append(
                CampaignRunAdventureRead(
                    id=adventure.id,
                    title=adventure.title,
                    intro_excerpt=_excerpt(adventure.intro),
                    status=status,
                )
            )

    return CampaignRunOverviewRead(
        id=run.id,
        campaign_id=run.campaign_id,
        content_version=run.content_version,
        title=run.title,
        status=run.status,
        created_at=run.created_at,
        campaign_title=loaded.campaign.title if loaded is not None else None,
        campaign_summary=loaded.campaign.summary if loaded is not None else None,
        unavailable=loaded is None,
        members=members,
        adventures=adventures,
    )


async def get_table(db: AsyncSession, *, user_id: str, run_id: str) -> TableRead:
    """One aggregate read for the play screen (WI2, sprint 010/05, AC1/AC2):
    the run, its pinned campaign's title, the current adventure and scene,
    and every seated hero's full sheet -- serving the screen's header, its
    party rail and the full sheet alike, in one call.

    Gated by membership exactly like every other read (`_require_member`
    then `_get_run`). Members and their characters come from the same join
    `get_run_overview` uses, but only rows with a character contribute a
    hero here -- unlike that overview, this read has no seat-without-a-
    character row to carry. Items are fetched the same way: one further
    query, grouped in Python by `owner_object_id`, skipped when no member
    has a character.

    The current adventure and scene are anchored on the **caller's own**
    hero, never on whichever `adventure_runs` row reads `status ==
    'active'` (← research, sprint plan I2): `use_exit` marks a row
    `completed` without ever clearing anyone's position, so an
    active-row anchor would blank the header at exactly the moment an
    adventure ends. Both answer `None` when the caller has no hero yet,
    the hero has entered no adventure (`adventure_run_id is None` --
    `scene_id` is always `None` right alongside it, the same tied pair
    `objects`'s own check constraint enforces), or the pinned content no
    longer loads. `campaignTitle` answers `None` under that last condition
    alone, independent of the caller's own hero. Reads only: no commit, no
    status change, no event.
    """
    member = await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)

    member_stmt = (
        select(CampaignRunMember, GameObject)
        .outerjoin(
            GameObject,
            (GameObject.member_id == CampaignRunMember.id) & (GameObject.kind == "creature"),
        )
        .where(CampaignRunMember.campaign_run_id == run_id)
        .order_by(CampaignRunMember.id)
    )
    member_result = await db.execute(member_stmt)
    member_rows = member_result.all()

    character_ids = [
        character_object.id for _, character_object in member_rows if character_object is not None
    ]
    items_by_owner: dict[str, list[GameObject]] = {}
    if character_ids:
        items_stmt = (
            select(GameObject)
            .where(GameObject.kind == "item", GameObject.owner_object_id.in_(character_ids))
            .order_by(GameObject.instance_key)
        )
        items_result = await db.execute(items_stmt)
        for item in items_result.scalars().all():
            items_by_owner.setdefault(item.owner_object_id, []).append(item)

    heroes = [
        character_read(character_object, items=items_by_owner.get(character_object.id, []))
        for _, character_object in member_rows
        if character_object is not None
    ]

    caller_character = next(
        (
            character_object
            for run_member, character_object in member_rows
            if run_member.id == member.id and character_object is not None
        ),
        None,
    )

    loaded = _load_pinned(run)

    adventure: TableAdventure | None = None
    scene: TableScene | None = None
    if (
        loaded is not None
        and caller_character is not None
        and caller_character.adventure_run_id is not None
    ):
        adventure_run_result = await db.execute(
            select(AdventureRun).where(AdventureRun.id == caller_character.adventure_run_id)
        )
        adventure_run = adventure_run_result.scalar_one_or_none()
        if adventure_run is not None:
            adventure_content = loaded.adventures.get(adventure_run.adventure_id)
            if adventure_content is not None:
                adventure = TableAdventure(
                    id=adventure_run.adventure_id,
                    run_id=adventure_run.id,
                    title=adventure_content.title,
                    status=adventure_run.status,
                )

        scene_content = (
            loaded.scenes.get(caller_character.scene_id)
            if caller_character.scene_id is not None
            else None
        )
        if scene_content is not None:
            scene = TableScene(id=scene_content.id, name=scene_content.title)

    return TableRead(
        run_id=run.id,
        run_title=run.title,
        run_status=run.status,
        campaign_title=loaded.campaign.title if loaded is not None else None,
        adventure=adventure,
        scene=scene,
        heroes=heroes,
    )


def _creature_template_attacks_and_disposition(
    creature: GameObject, *, campaign_id: str, version: str
) -> tuple[str | None, tuple[situation_types.AttackView, ...]]:
    """A scene creature's authored `disposition` and full `Attack`s, read
    off its own template -- `None`/`()` for a template-less object (a
    player character, whose own attacks live on carried items, never
    here). Unlike `_creature_attack_names`, never swallows: a broken
    template is a broken `Situation` (intent §2.5), not a display gap."""
    if creature.template_id is None:
        return None, ()
    template = content_service.load_object_template(campaign_id, version, creature.template_id)
    if not isinstance(template, CreatureTemplate):
        return None, ()
    attacks = tuple(
        situation_types.AttackView(name=attack.name, to_hit=attack.to_hit, damage=attack.damage)
        for attack in template.stat_block.attacks
    )
    return template.disposition, attacks


def _item_attacks(
    item: GameObject, *, campaign_id: str, version: str
) -> tuple[situation_types.AttackView, ...]:
    """An item's own attacks -- its carried row's own `state["attacks"]`
    when present (a sheet-born weapon, mirroring `dice._attacks_for`'s
    own first branch), otherwise its template's, given or seeded alike;
    `()` for anything with neither, including a non-weapon such as a
    shield. Read-only display data for `_resolve_hero_weapon`'s own
    deterministic fallback -- never a roll, never through `dice` itself,
    which stays the one seam that derives a formula."""
    raw_attacks = item.state.get("attacks")
    if raw_attacks:
        return tuple(
            situation_types.AttackView(name=parsed.name, to_hit=parsed.to_hit, damage=parsed.damage)
            for parsed in (Attack.model_validate(a) for a in raw_attacks)
        )
    if item.template_id is None:
        return ()
    template = content_service.load_object_template(campaign_id, version, item.template_id)
    if not isinstance(template, ItemTemplate):
        return ()
    return tuple(
        situation_types.AttackView(name=attack.name, to_hit=attack.to_hit, damage=attack.damage)
        for attack in template.attacks
    )


async def _actor_view(
    creature: GameObject,
    *,
    is_hero: bool,
    campaign_id: str,
    version: str,
    inventory: Sequence[GameObject],
) -> situation_types.ActorView:
    disposition, attacks = (
        (None, ())
        if is_hero
        else _creature_template_attacks_and_disposition(
            creature, campaign_id=campaign_id, version=version
        )
    )
    state_hostile = creature.state.get("hostile")
    role = situation_types.derive_role(
        is_hero=is_hero, state_hostile=state_hostile, disposition=disposition, attacks=attacks
    )
    return situation_types.ActorView(
        id=creature.id,
        name=creature.name,
        role=role,
        kind=creature.kind,
        current_hp=creature.current_hp,
        max_hp=creature.max_hp,
        armour_class=creature.armour_class,
        is_alive=creature.is_alive,
        down=is_down(creature),
        disposition=disposition,
        hostile=role == "hostile",
        attacks=attacks,
        inventory=tuple(
            situation_types.ItemView(
                id=item.id,
                name=item.name,
                attacks=_item_attacks(item, campaign_id=campaign_id, version=version),
            )
            for item in inventory
        ),
    )


async def get_situation(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    recent_limit: int = situation_types.RECENT_WINDOW,
) -> situation_types.Situation:
    """The one-shot projection of the caller's current moment (sprint
    011/04, WI1, I1): the scene's authored truth, its present actors with
    roles derived fresh (never stored), its fixtures and their recorded
    outcomes, its exits, its hidden facts, and the run's last
    `recent_limit` player-visible events, oldest first.

    Gated exactly like `get_table` (`_require_member` then `_get_run`),
    then anchored on the **caller's own** hero exactly the way `get_table`
    is (← research) -- never on whichever `adventure_runs` row happens to
    read `active`. Unlike `get_table`, a missing hero, adventure, scene or
    piece of pinned content each raise `SituationError` rather than
    degrading a field to `None`: there is no partial `Situation` (intent
    §2.5).
    """
    member = await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)

    loaded = _load_pinned(run)
    if loaded is None:
        raise SituationError(run_id, reason="pinned content unavailable")

    hero_stmt = select(GameObject).where(
        GameObject.member_id == member.id, GameObject.kind == "creature"
    )
    hero_result = await db.execute(hero_stmt)
    hero = hero_result.scalar_one_or_none()
    if hero is None:
        raise SituationError(run_id, reason="caller has no hero")
    if hero.adventure_run_id is None or hero.scene_id is None:
        raise SituationError(run_id, reason="hero has entered no adventure")

    adventure_run = await db.get(AdventureRun, hero.adventure_run_id)
    if adventure_run is None:
        raise SituationError(run_id, reason="hero's adventure run no longer exists")

    adventure_content = loaded.adventures.get(adventure_run.adventure_id)
    if adventure_content is None:
        raise SituationError(
            run_id, reason=f"adventure not in pinned content: {adventure_run.adventure_id}"
        )

    scene_content = loaded.scenes.get(hero.scene_id)
    if scene_content is None:
        raise SituationError(run_id, reason=f"scene not in pinned content: {hero.scene_id}")

    campaign_id = run.campaign_id
    version = run.content_version

    items_stmt = select(GameObject).where(
        GameObject.owner_object_id.in_(
            select(GameObject.id).where(
                GameObject.campaign_run_id == run_id,
                GameObject.scene_id == hero.scene_id,
                GameObject.kind == "creature",
            )
        )
    )
    items_result = await db.execute(items_stmt)
    items_by_owner: dict[str, list[GameObject]] = {}
    for item in items_result.scalars().all():
        items_by_owner.setdefault(item.owner_object_id, []).append(item)

    hero_view = await _actor_view(
        hero,
        is_hero=True,
        campaign_id=campaign_id,
        version=version,
        inventory=items_by_owner.get(hero.id, []),
    )

    other_creatures_stmt = (
        select(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.scene_id == hero.scene_id,
            GameObject.kind == "creature",
            GameObject.owner_object_id.is_(None),
            GameObject.id != hero.id,
        )
        .order_by(GameObject.id)
    )
    other_creatures_result = await db.execute(other_creatures_stmt)
    actors = tuple(
        [
            await _actor_view(
                creature,
                is_hero=False,
                campaign_id=campaign_id,
                version=version,
                inventory=items_by_owner.get(creature.id, []),
            )
            for creature in other_creatures_result.scalars().all()
        ]
    )

    fixtures_stmt = (
        select(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.scene_id == hero.scene_id,
            GameObject.kind == "fixture",
            GameObject.owner_object_id.is_(None),
        )
        .order_by(GameObject.id)
    )
    fixtures_result = await db.execute(fixtures_stmt)
    fixtures = []
    for fixture in fixtures_result.scalars().all():
        checks: tuple[situation_types.FixtureCheckView, ...] = ()
        description = fixture.name
        if fixture.template_id is not None:
            template = content_service.load_object_template(
                campaign_id, version, fixture.template_id
            )
            if isinstance(template, FixtureTemplate):
                description = template.description
                checks = tuple(
                    situation_types.FixtureCheckView(
                        action=check.action,
                        ability=check.ability,
                        skill=check.skill,
                        dc=check.dc,
                        success=check.success,
                    )
                    for check in template.checks
                )
        outcomes = {
            action: entry["success"]
            for action, entry in fixture.state.get("fixture_outcomes", {}).items()
        }
        fixtures.append(
            situation_types.FixtureView(
                id=fixture.id,
                name=fixture.name,
                description=description,
                checks=checks,
                outcomes=outcomes,
            )
        )

    loose_items_stmt = (
        select(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.scene_id == hero.scene_id,
            GameObject.kind == "item",
            GameObject.owner_object_id.is_(None),
        )
        .order_by(GameObject.id)
    )
    loose_items_result = await db.execute(loose_items_stmt)
    loose_items = tuple(
        situation_types.ItemView(id=item.id, name=item.name)
        for item in loose_items_result.scalars().all()
    )

    exits = tuple(
        situation_types.ExitView(
            id=exit_.id,
            kind=exit_.kind,
            to=exit_.to,
            description=exit_.description,
            condition=exit_.condition,
        )
        for exit_ in scene_content.exits
    )

    secrets = tuple(
        situation_types.SecretView(
            fact=secret.fact,
            ability=secret.ability,
            skill=secret.skill,
            dc=secret.dc,
            discovered_by=secret.discovered_by,
        )
        for secret in scene_content.hidden
    )

    recent_stmt = (
        select(Event)
        .where(Event.campaign_run_id == run_id, Event.visibility == "player")
        .order_by(Event.id.desc())
        .limit(recent_limit)
    )
    recent_result = await db.execute(recent_stmt)
    recent = tuple(
        situation_types.RecentEvent(
            id=event.id,
            turn_id=event.turn_id,
            type=event.type,
            payload=event.payload,
            created_at=event.created_at,
        )
        for event in reversed(recent_result.scalars().all())
    )

    return situation_types.Situation(
        run_id=run.id,
        hero_id=hero.id,
        adventure_run_id=adventure_run.id,
        scene_id=hero.scene_id,
        campaign_title=loaded.campaign.title,
        adventure_title=adventure_content.title,
        scene_title=scene_content.title,
        truth=tuple(scene_content.truth),
        consequences=tuple(scene_content.consequences),
        pressure=scene_content.pressure,
        npc_intent=scene_content.npc_intent,
        secrets=secrets,
        hero=hero_view,
        actors=actors,
        fixtures=tuple(fixtures),
        loose_items=loose_items,
        exits=exits,
        recent=recent,
    )


async def create_character(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    sheet: CharacterSheet | SeedCharacter | None = None,
) -> GameObject:
    """The run's one player character, built from `sheet` -- or, when
    `sheet` is `None`, from the seed character the run's pinned campaign
    declares (← D4). A built `CharacterSheet` (sprint 009-02, WI2, AC4/AC5)
    writes its full state (`level`, `alignment`, `speed`,
    `proficiency_bonus`, `saving_throws`, `skills`, `equipment` alongside
    the fields the seed path already wrote) and one carried `item` row per
    *unit of quantity* of each `SheetItem` -- `template_id=None`, its own
    `name`, `state={"srd_id", "attacks"}` -- rather than the seed path's
    one row per template-driven inventory entry.

    Refuses a second character on this run (`CharacterExistsError`, a
    Stage-01 game rule, not a schema constraint -- ← 003-D13) and refuses
    an archived run (`RunArchivedError`). Builds the creature, flushes,
    builds the carried rows, flushes, moves the run to `ready`, and
    commits once -- the same single commit boundary either path takes.
    Appends no event. Catches nothing else: any other failure (a stat
    outside its check constraint, a bad foreign key) is a bug, not a
    domain error, and travels to the 500 envelope.
    """
    member = await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)
    _require_writable(run)

    existing = await db.execute(
        select(GameObject.id).where(
            GameObject.campaign_run_id == run_id,
            GameObject.kind == "creature",
            GameObject.member_id == member.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise CharacterExistsError(run_id)

    loaded = content_service.load_campaign(run.campaign_id, run.content_version)
    if sheet is None:
        sheet = loaded.campaign.seed_character

    instance_key = f"pc:{member.id}:1"

    if isinstance(sheet, CharacterSheet):
        state = CharacterState(
            abilities=sheet.abilities,
            race=sheet.race,
            character_class=sheet.character_class,
            background=sheet.backstory,
            appearance=sheet.appearance,
            level=sheet.level,
            alignment=sheet.alignment,
            speed=sheet.speed,
            proficiency_bonus=sheet.proficiency_bonus,
            saving_throws=list(sheet.saving_throws),
            skills=list(sheet.skills),
            equipment=list(sheet.equipment),
        )
    else:
        state = CharacterState(
            abilities=sheet.abilities,
            race=sheet.race,
            character_class=sheet.character_class,
            background=sheet.background,
            appearance=sheet.appearance,
        )

    character = GameObject(
        id=generate_id(),
        campaign_run_id=run_id,
        member_id=member.id,
        kind="creature",
        instance_key=instance_key,
        name=sheet.name,
        current_hp=sheet.max_hp,
        max_hp=sheet.max_hp,
        armour_class=sheet.armour_class,
        is_alive=True,
        state=state.model_dump(),
    )
    db.add(character)
    await db.flush()

    carried_rows: list[GameObject] = []
    if isinstance(sheet, CharacterSheet):
        for item in sheet.equipment:
            for n in range(1, item.quantity + 1):
                carried_key = f"{instance_key}/{item.id}:{n}"
                carried_rows.append(
                    GameObject(
                        id=generate_id(),
                        campaign_run_id=run_id,
                        kind="item",
                        template_id=None,
                        instance_key=carried_key,
                        name=item.name,
                        owner_object_id=character.id,
                        state={
                            "srd_id": item.id,
                            "attacks": [attack.model_dump() for attack in item.attacks],
                        },
                    )
                )
    else:
        # `n` counts repeats of the same template within the pack -- greenhollow's
        # five entries are distinct, so every carried key here ends `:1`.
        ordinals: dict[str, int] = {}
        for template_id in sheet.inventory:
            ordinals[template_id] = ordinals.get(template_id, 0) + 1
            carried_key = f"{instance_key}/{template_id}:{ordinals[template_id]}"
            carried_row = _build_object(
                campaign_run_id=run_id,
                template=loaded.object_templates[template_id],
                instance_key=carried_key,
            )
            carried_row.owner_object_id = character.id
            carried_rows.append(carried_row)

    db.add_all(carried_rows)
    await db.flush()

    run.status = "ready"
    await db.commit()
    await db.refresh(character)
    return character


async def get_member_character(db: AsyncSession, *, user_id: str, run_id: str) -> GameObject:
    """The caller's own character on this run.

    Gated by membership exactly like every other read (`_require_member`
    first) -- a foreign or unknown run raises `CampaignRunNotFoundError`
    before this ever looks at `objects`. The one `objects` row with
    `member_id == member.id AND kind == 'creature'` is this member's
    character (`create_character` never lets a second one exist -- ←
    `CharacterExistsError`); no row yet raises `CharacterNotFoundError`.
    Reads only: no commit, no event, no status change.
    """
    member = await _require_member(db, run_id=run_id, user_id=user_id)

    result = await db.execute(
        select(GameObject).where(
            GameObject.campaign_run_id == run_id,
            GameObject.kind == "creature",
            GameObject.member_id == member.id,
        )
    )
    character = result.scalar_one_or_none()
    if character is None:
        raise CharacterNotFoundError(run_id)
    return character


async def rename_campaign_run(
    db: AsyncSession, *, user_id: str, run_id: str, title: str
) -> CampaignRun:
    """Sets the run's title. Refuses an archived run (`RunArchivedError`)."""
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)
    _require_writable(run)

    run.title = title
    await db.commit()
    await db.refresh(run)
    return run


async def archive_campaign_run(db: AsyncSession, *, user_id: str, run_id: str) -> None:
    """Puts the run away.

    `ready`, `active` and `finished` move to `archived`; already `archived`
    is a no-op that succeeds -- there is no unarchive, an archived run's
    story is kept to be re-read, never played on again. A `setup` run was
    never started in any way a player would recognise, so archiving it
    deletes it outright: the run row, its membership and every object the
    campaign instantiated, all removed by the `ON DELETE CASCADE` foreign
    keys the schema already carries (`campaign_run_members`, `objects`,
    `adventure_runs`, `events` -> `campaign_runs.id`) once this row goes.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)

    if run.status == "archived":
        return

    if run.status == "setup":
        await db.delete(run)
        await db.commit()
        return

    run.status = "archived"
    await db.commit()


async def activate_campaign_run(db: AsyncSession, *, user_id: str, run_id: str) -> CampaignRun:
    """`ready -> active`; already `active` is a no-op. Any other status
    cannot activate (`InvalidRunStatusError`). No route calls this yet --
    phase 8's adventure intro will (← D3).
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)

    if run.status == "active":
        return run
    if run.status != "ready":
        raise InvalidRunStatusError(run_id)

    run.status = "active"
    await db.commit()
    await db.refresh(run)
    return run


async def enter_adventure(db: AsyncSession, *, user_id: str, run_id: str) -> AdventureRun:
    """Enters the next adventure the pinned campaign declares that this
    run has no `adventure_runs` row for yet, positions its cast and every
    member character, and records that it began (WI1, AC1).

    `_require_member` -> `_get_run` -> `_require_writable` -> the run's
    status must be `ready` or `active` (`InvalidRunStatusError`
    otherwise). Does not touch the campaign run's own status: the first
    narration moves it to `active`, not entry (← D3,
    `activate_campaign_run`).

    "Next" is the first id in `campaign.adventures` with no
    `adventure_runs` row in this run -- the query behind that carries no
    status filter, so a `completed` row exhausts an id exactly the same
    way an `active` one would. None left raises `AdventureExhaustedError`,
    which is therefore also AC4's refusal for re-entering a completed
    adventure, not a separate code.

    The insert is speculative -- it may collide with
    `uq_adventure_runs_active` -- so it runs inside its own SAVEPOINT
    (`db.begin_nested()`), not the outer transaction: undoing it that way
    touches only the failed statement. A plain `db.rollback()` here would
    expire every ORM object the *session* holds, not just this
    function's own; the caller's already-loaded objects (its `run`, say)
    would then raise `MissingGreenlet` on their next ordinary attribute
    access, since an expired attribute needs a lazy reload and there is no
    async context left to do it in outside a real request. This is the
    same hazard the verifier recorded against 05b's `latest_event_id`,
    which rolls back for a different reason. Only `uq_adventure_runs_active`
    is translated to `AdventureActiveError`; any other integrity failure
    propagates unchanged, rather than the wide catch sprint 03 used for a
    different constraint.

    Once the insert holds, two `UPDATE objects` statements run in the
    outer transaction: the first positions that adventure's cast (matched
    by `source_adventure_id`, excluding anything with an owner -- carried
    items are never repositioned), the second positions every member
    character (matched by `member_id IS NOT NULL` alone, since a character
    made before any adventure existed has no `source_adventure_id` for the
    first statement to match on). `append_event` records
    `adventure_started` at `player` visibility with the new adventure
    run's id. Sprint 010/04, I2: it also records `scene_entered` for the
    entry scene the cast and every character were just positioned into,
    carrying that scene's own pinned `sceneTitle` -- the opening move
    otherwise left no such row at all. One commit closes both writes.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)
    _require_writable(run)

    if run.status not in ("ready", "active"):
        raise InvalidRunStatusError(run_id)

    loaded = content_service.load_campaign(run.campaign_id, run.content_version)

    entered = await db.execute(
        select(AdventureRun.adventure_id).where(AdventureRun.campaign_run_id == run_id)
    )
    entered_ids = set(entered.scalars().all())

    next_adventure_id = next(
        (
            adventure_id
            for adventure_id in loaded.campaign.adventures
            if adventure_id not in entered_ids
        ),
        None,
    )
    if next_adventure_id is None:
        raise AdventureExhaustedError(run_id)

    adventure = loaded.adventures[next_adventure_id]
    adventure_run = AdventureRun(
        campaign_run_id=run_id, adventure_id=next_adventure_id, status="active"
    )

    try:
        async with db.begin_nested():
            db.add(adventure_run)
            await db.flush()
    except IntegrityError as exc:
        if "uq_adventure_runs_active" not in str(exc.orig):
            raise
        raise AdventureActiveError(run_id) from exc

    await db.execute(
        update(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.source_adventure_id == next_adventure_id,
            GameObject.owner_object_id.is_(None),
        )
        .values(adventure_run_id=adventure_run.id, scene_id=GameObject.source_scene_id)
    )
    await db.execute(
        update(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.member_id.is_not(None),
        )
        .values(adventure_run_id=adventure_run.id, scene_id=adventure.entry_scene)
    )

    await append_event(
        db,
        run_id=run_id,
        type="adventure_started",
        visibility="player",
        payload={"adventure_run_id": adventure_run.id},
    )
    await append_event(
        db,
        run_id=run_id,
        type="scene_entered",
        visibility="player",
        payload={
            "adventure_run_id": adventure_run.id,
            "scene_id": adventure.entry_scene,
            "scene_title": loaded.scenes[adventure.entry_scene].title,
        },
    )

    await db.commit()
    await db.refresh(adventure_run)
    return adventure_run


async def set_hostility(
    db: AsyncSession, *, user_id: str, actor_id: str, hostile: bool, turn_id: str | None = None
) -> MutationResult:
    """Sets whether the creature at `actor_id` is hostile, in `state["hostile"]`
    (sprint 011/03, WI2). Absent means undecided -- the situation falls back
    to the creature's authored disposition prose; this call is the only way
    that ever changes.

    Gate order matches every other mechanic in this module:
    `_resolve_actor_and_run` first (an unknown or foreign actor, an archived
    run, a run outside `ready`/`active` each raise before anything else
    runs). A non-creature actor (`item`/`fixture`) is refused
    (`ACTOR_NOT_CREATURE` is not a distinct code -- reuses `outcome.reason`
    text; there is no dedicated exception because this is an expected
    refusal, not a programming error). `state` is reassigned whole, never
    mutated in place, matching the house rule for `GameObject.state`.
    """
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)

    if actor.kind != "creature":
        reason = f"actor is not a creature: {actor_id}"
        event = await append_event(
            db,
            run_id=run.id,
            type="tool_call",
            visibility="dm",
            turn_id=turn_id,
            payload={
                "name": "set_hostility",
                "args": {"actorId": actor_id, "hostile": hostile},
                "roll_ids": [],
                "result": "refused",
                "outcome": {"reason": reason},
            },
        )
        await db.commit()
        return MutationResult(status="refused", reason=reason, event_ids=[event.id])

    state = dict(actor.state)
    state["hostile"] = hostile
    actor.state = state

    event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "set_hostility",
            "args": {"actorId": actor_id, "hostile": hostile},
            "roll_ids": [],
            "result": "ok",
            "outcome": {},
        },
    )
    await db.commit()
    return MutationResult(status="ok", event_ids=[event.id], facts={"hostile": hostile})


async def leave_scene(
    db: AsyncSession, *, user_id: str, actor_id: str, turn_id: str | None = None
) -> MutationResult:
    """Removes the actor at `actor_id` from its scene, remembering where it
    left in `state["left_scene"] = {"sceneId", "adventureRunId"}` (sprint
    011/03, WI2). `scene_id` and `adventure_run_id` are cleared together --
    `GameObject`'s own `position` CHECK allows only both null or both set,
    never one alone.

    Gate order matches `set_hostility`. An actor with no `scene_id` already
    -- never positioned, or already departed -- is refused
    (`ALREADY_LEFT` is not a distinct code, same convention as above).
    """
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)

    if actor.scene_id is None:
        reason = f"actor has already left the scene: {actor_id}"
        event = await append_event(
            db,
            run_id=run.id,
            type="tool_call",
            visibility="dm",
            turn_id=turn_id,
            payload={
                "name": "leave_scene",
                "args": {"actorId": actor_id},
                "roll_ids": [],
                "result": "refused",
                "outcome": {"reason": reason},
            },
        )
        await db.commit()
        return MutationResult(status="refused", reason=reason, event_ids=[event.id])

    scene_id = actor.scene_id
    adventure_run_id = actor.adventure_run_id
    state = dict(actor.state)
    state["left_scene"] = {"sceneId": scene_id, "adventureRunId": adventure_run_id}
    actor.state = state
    actor.scene_id = None
    actor.adventure_run_id = None

    event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "leave_scene",
            "args": {"actorId": actor_id},
            "roll_ids": [],
            "result": "ok",
            "outcome": {},
        },
    )
    await db.commit()
    return MutationResult(
        status="ok",
        event_ids=[event.id],
        facts={"sceneId": scene_id, "adventureRunId": adventure_run_id},
    )


async def enter_next_adventure(
    db: AsyncSession, *, user_id: str, run_id: str, turn_id: str | None = None
) -> MutationResult:
    """Thin graph-facing wrapper over `enter_adventure` (sprint 011/03,
    WI2): same gates, same writes, but returns `MutationResult` and records
    its own dm `tool_call` -- `enter_adventure`'s own callers (sprint 06)
    predate that convention and are left alone.

    `AdventureExhaustedError` -- every adventure already entered -- is the
    one expected refusal (← AC4); every other error `enter_adventure`
    raises (`CampaignRunNotFoundError`, `RunArchivedError`,
    `InvalidRunStatusError`, `AdventureActiveError`) keeps raising.
    """
    try:
        adventure_run = await enter_adventure(db, user_id=user_id, run_id=run_id)
    except AdventureExhaustedError:
        reason = f"campaign run has no adventure left to enter: {run_id}"
        event = await append_event(
            db,
            run_id=run_id,
            type="tool_call",
            visibility="dm",
            turn_id=turn_id,
            payload={
                "name": "enter_next_adventure",
                "args": {},
                "roll_ids": [],
                "result": "refused",
                "outcome": {"reason": reason},
            },
        )
        await db.commit()
        return MutationResult(status="refused", reason=reason, event_ids=[event.id])

    event = await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "enter_next_adventure",
            "args": {},
            "roll_ids": [],
            "result": "ok",
            "outcome": {},
        },
    )
    await db.commit()
    return MutationResult(
        status="ok", event_ids=[event.id], facts={"adventureRunId": adventure_run.id}
    )


_FINISH_RUN_MESSAGES: dict[str, str] = {
    "victory": "The party has triumphed. The adventure ends in victory.",
    "defeat": "The party has fallen. The adventure ends in defeat.",
    "authored": "The story has run its course.",
}


async def finish_run(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    outcome: Literal["victory", "defeat", "authored"],
    turn_id: str | None = None,
) -> MutationResult:
    """Marks `run_id` finished with `outcome` (sprint 011/03, WI2): sets
    `status="finished"` on the run and appends one player-visible `system`
    event carrying the ending prose plus `details.outcome` -- there is no
    column for how a run ended and the persistence boundary forbids adding
    one (← research), so the event is the only record.

    Gate order: `_require_member` -> `_get_run` -> `_require_writable` (an
    archived run keeps raising `RunArchivedError`). A run already
    `status="finished"` is refused, typed, rather than raising -- calling
    this twice is an expected shape (`use_exit`'s own last-adventure branch
    and a retried `authored` ending can both reach here), not a programming
    error.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)
    _require_writable(run)

    if run.status == "finished":
        reason = f"campaign run is already finished: {run_id}"
        event = await append_event(
            db,
            run_id=run_id,
            type="tool_call",
            visibility="dm",
            turn_id=turn_id,
            payload={
                "name": "finish_run",
                "args": {"outcome": outcome},
                "roll_ids": [],
                "result": "refused",
                "outcome": {"reason": reason},
            },
        )
        await db.commit()
        return MutationResult(status="refused", reason=reason, event_ids=[event.id])

    run.status = "finished"

    ending_event = await append_event(
        db,
        run_id=run_id,
        type="system",
        visibility="player",
        turn_id=turn_id,
        payload={"message": _FINISH_RUN_MESSAGES[outcome], "details": {"outcome": outcome}},
    )
    tool_call_event = await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "finish_run",
            "args": {"outcome": outcome},
            "roll_ids": [],
            "result": "ok",
            "outcome": {},
        },
    )
    await db.commit()
    return MutationResult(
        status="ok",
        event_ids=[ending_event.id, tool_call_event.id],
        facts={"outcome": outcome},
    )


async def _get_game_object(db: AsyncSession, object_id: str) -> GameObject:
    """The one object `actor_id` names, with no run context yet -- `use_exit`
    loads the actor before it knows which run's membership to check, so
    this cannot filter on `campaign_run_id` the way every other lookup in
    this module does.
    """
    result = await db.execute(select(GameObject).where(GameObject.id == object_id))
    obj = result.scalar_one_or_none()
    if obj is None:
        raise GameObjectNotFoundError(object_id)
    return obj


async def _require_ready_or_active_run(
    db: AsyncSession, *, run_id: str, user_id: str
) -> CampaignRun:
    """`use_exit`'s own gate order, for a run already known by id:
    `_require_member` -> `_get_run` -> `_require_writable` -> the run must
    be `ready` or `active` (`InvalidRunStatusError` otherwise). Shared by
    every WI2 producer that takes a `run_id` directly (`ask_player`) or
    resolves one from something else it was given
    (`_resolve_actor_and_run`, `resolve_roll_request`).
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    run = await _get_run(db, run_id)
    _require_writable(run)
    if run.status not in ("ready", "active"):
        raise InvalidRunStatusError(run.id)
    return run


async def _resolve_actor_and_run(
    db: AsyncSession, *, actor_id: str, user_id: str
) -> tuple[GameObject, CampaignRun]:
    """Loads the actor `actor_id` names, with no run context yet -- exactly
    `use_exit`'s own first step -- then gates the run it belongs to."""
    actor = await _get_game_object(db, actor_id)
    run = await _require_ready_or_active_run(db, run_id=actor.campaign_run_id, user_id=user_id)
    return actor, run


async def resolve_actor_ref(db: AsyncSession, *, run_id: str, ref: str) -> GameObject:
    """`ref` -- whatever the model passed as an `actor_id` -- resolved to
    one creature of `run_id` (sprint 010/10, ← finding: a scene with
    several identically-named monsters gave the model no way to tell them
    apart, and its own id is the one thing that always does).

    An id match wins outright, whether or not that object is still alive
    -- `attack`/`damage`/`roll` already refuse a dead or out-of-scene
    actor on their own terms once resolved, and an exact id is never
    ambiguous. Failing that, `ref` is matched case-insensitively against
    every *living, positioned* creature's own `name` in this run --
    `scene_id IS NOT NULL` excludes a creature instantiated for a scene
    the party has not reached yet (`start_campaign_run`/`enter_adventure`
    instantiate a whole adventure's objects up front, unpositioned): it is
    nowhere in the fiction yet and is never what a name alone should mean.
    The first match (by id, i.e. creation order) wins when more than one
    shares the name -- the caller's own result already names `actor_id`
    with whichever one was actually used, so which twin acted is never
    silently lost.

    Raises `GameObjectNotFoundError(ref)` when neither an id nor a living,
    positioned name matches -- the caller is expected to catch this and
    hand the model `describe_scene_creatures` instead of a bare refusal
    (← D11's own spirit, applied to a lookup rather than a mechanic)."""
    result = await db.execute(select(GameObject).where(GameObject.id == ref))
    obj = result.scalar_one_or_none()
    if obj is not None and obj.campaign_run_id == run_id:
        return obj

    stmt = (
        select(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.kind == "creature",
            GameObject.is_alive.is_(True),
            GameObject.scene_id.is_not(None),
        )
        .order_by(GameObject.id)
    )
    result = await db.execute(stmt)
    for candidate in result.scalars().all():
        if is_down(candidate):
            continue
        if candidate.name.casefold() == ref.casefold():
            return candidate

    raise GameObjectNotFoundError(ref)


def _creature_attack_names(creature: GameObject, *, campaign_id: str, version: str) -> list[str]:
    """The named attacks a scene creature's own stat block carries, or
    `[]` for a template-less object (a player character, whose own
    attacks live on carried items, not here) or one whose template fails
    to load. Never raises -- this is display only."""
    if creature.template_id is None:
        return []
    try:
        template = content_service.load_object_template(campaign_id, version, creature.template_id)
    except ContentError:
        return []
    if not isinstance(template, CreatureTemplate):
        return []
    return [attack.name for attack in template.stat_block.attacks]


async def describe_scene_creatures(
    db: AsyncSession,
    *,
    run_id: str,
    scene_id: str | None = None,
    near_actor_id: str | None = None,
    campaign_id: str | None = None,
    version: str | None = None,
) -> list[dict[str, Any]]:
    """Every creature positioned in one scene of `run_id` -- id first, so a
    scene with several identically-named monsters can still be told apart
    (sprint 010/10, ← finding). `scene_id` names the scene directly (what
    `get_scene` already knows); `near_actor_id` instead names an actor
    whose own `scene_id` is looked up first, the way `_build_game_context`
    finds "the current scene" from the party's own position. Neither
    given, or naming nobody positioned anywhere, answers `[]`. `campaign_id`
    and `version` let a caller that already loaded the run (`_build_game_
    context` does) skip re-reading it here; omitted, both are read off
    `run_id`'s own row.

    Each entry is `id, name, role, is_alive, down, current_hp, max_hp,
    armour_class, attacks` -- `down` is `is_down(creature)` (sprint 011/02,
    WI3, I3): `is_alive` alone lets a downed hero read as a living,
    targetable actor, since `damage` never flips a member's own `is_alive`
    at 0 hp. `role` is `player` for a member's own
    character, else `monster` when its stat block carries at least one
    attack, else `npc` (Mira the innkeeper: `attacks: []`, never a
    combatant) -- there is no authored hostile/friendly flag to read
    instead. `attacks` is the creature's own named attacks, empty for a
    template-less object or one with none, so a caller building
    `context['attack']` never has to guess."""
    if scene_id is None and near_actor_id is not None:
        near = await db.get(GameObject, near_actor_id)
        if near is not None and near.campaign_run_id == run_id:
            scene_id = near.scene_id
    if scene_id is None:
        return []

    if campaign_id is None or version is None:
        run = await _get_run(db, run_id)
        campaign_id = campaign_id or run.campaign_id
        version = version or run.content_version

    stmt = (
        select(GameObject)
        .where(
            GameObject.campaign_run_id == run_id,
            GameObject.scene_id == scene_id,
            GameObject.kind == "creature",
            GameObject.owner_object_id.is_(None),
        )
        .order_by(GameObject.id)
    )
    result = await db.execute(stmt)
    creatures = list(result.scalars().all())

    described = []
    for creature in creatures:
        attacks = _creature_attack_names(creature, campaign_id=campaign_id, version=version)
        role = "player" if creature.member_id is not None else ("monster" if attacks else "npc")
        described.append(
            {
                "id": creature.id,
                "name": creature.name,
                "role": role,
                "is_alive": creature.is_alive,
                "down": is_down(creature),
                "current_hp": creature.current_hp,
                "max_hp": creature.max_hp,
                "armour_class": creature.armour_class,
                "attacks": attacks,
            }
        )
    return described


async def _get_roll_request_event(db: AsyncSession, request_id: str) -> Event:
    """The `roll_requested` event named `request_id`, with no run context
    yet -- `resolve_roll_request` learns which run to gate from this row's
    own `campaign_run_id`, the same way `use_exit` learns its run from the
    actor it loads first. An unknown id, or one that names an event of any
    other type, is refused identically (`RollRequestNotFoundError`): there
    is nothing to disambiguate them by.
    """
    result = await db.execute(select(Event).where(Event.id == request_id))
    event = result.scalar_one_or_none()
    if event is None or event.type != "roll_requested":
        raise RollRequestNotFoundError(request_id)
    return event


async def _append_roll_requested(
    db: AsyncSession,
    *,
    run: CampaignRun,
    actor: GameObject,
    kind: RollKind,
    context: Any,
    visibility: str,
    turn_id: str | None,
) -> Event:
    """Derives the formula from `kind` and `actor` alone (← D6 -- never a
    number a caller passed) and appends `roll_requested` at `visibility`.
    Shared by `request_player_roll` (always `player`, since the player is
    the one being asked) and `roll` (whatever visibility its caller asked
    for).

    For `attack`/`damage`, `context["item_id"]` may name either a content
    template or a carried item row. A row from this run is handed to
    `dice.derive_formula` directly so the runtime item ID exposed to the DM
    also works for seeded template weapons and sheet-born weapons alike;
    anything else falls through to the template-driven path unchanged."""
    item: GameObject | None = None
    if kind in ("attack", "damage"):
        item_id = context.get("item_id") if isinstance(context, dict) else None
        if item_id is not None:
            candidate = await db.get(GameObject, item_id)
            if candidate is not None and candidate.campaign_run_id == run.id:
                item = candidate
    formula = dice.derive_formula(
        kind,
        actor,
        context,
        campaign_id=run.campaign_id,
        version=run.content_version,
        item=item,
    )
    return await append_event(
        db,
        run_id=run.id,
        type="roll_requested",
        visibility=visibility,
        turn_id=turn_id,
        payload={"kind": kind, "actor_id": actor.id, "formula": formula, "context": context},
    )


async def _append_roll(
    db: AsyncSession, *, run: CampaignRun, request_event: Event, turn_id: str | None
) -> Event:
    """Answers `request_event` with a `roll`, re-using its own stored
    `formula`, `kind` and `actor_id` verbatim and at its own visibility --
    re-deriving here could hand back a different formula than the one
    already promised (I3). Shared by `resolve_roll_request` and `roll`."""
    requested = RollRequestedPayload.model_validate(request_event.payload)
    rolled = dice.roll(requested.formula)
    return await append_event(
        db,
        run_id=run.id,
        type="roll",
        visibility=request_event.visibility,
        turn_id=turn_id,
        payload={
            "request_id": request_event.id,
            "kind": requested.kind,
            "actor_id": requested.actor_id,
            "formula": requested.formula,
            "faces": rolled.faces,
            "modifier": rolled.modifier,
            "total": rolled.total,
        },
    )


async def _find_pending_roll_request(
    db: AsyncSession, *, run_id: str, turn_id: str, actor_id: str, kind: RollKind
) -> Event | None:
    """The most recent `roll_requested` this turn for `actor_id`/`kind` that
    no `roll` has answered yet, or `None`.

    Reads every payload back through `RollRequestedPayload`/`RollPayload`
    rather than raw dict keys: `append_event` stores a payload's camelCase
    wire alias (`CamelModel`), so a plain `payload.get("request_id")`
    against the stored row silently never matches (← finding, sprint
    010/09). Backs `request_player_roll`'s own idempotency: a LangGraph
    resume re-executes the calling tool's code from the top, including
    whatever ran before its `interrupt()`, so the same `turn_id`/
    `actor_id`/`kind` seen twice in one turn is the same request replaying,
    not a second one.
    """
    stmt = (
        select(Event)
        .where(
            Event.campaign_run_id == run_id,
            Event.turn_id == turn_id,
            Event.type.in_(("roll_requested", "roll")),
        )
        .order_by(Event.id)
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())
    answered_request_ids = {
        RollPayload.model_validate(e.payload).request_id for e in events if e.type == "roll"
    }
    candidates = [
        e
        for e in events
        if e.type == "roll_requested"
        and e.id not in answered_request_ids
        and (requested := RollRequestedPayload.model_validate(e.payload))
        and requested.actor_id == actor_id
        and requested.kind == kind
    ]
    return candidates[-1] if candidates else None


_PLAYER_ROLL_KINDS: frozenset[str] = frozenset(
    {"ability_check", "saving_throw", "initiative", "custom"}
)
"""What `request_player_roll` may ask for (sprint 010/10, ← finding): a
player rolls their own checks, saves, initiative and the odd bespoke
`custom` roll -- never `attack`/`damage`, which deterministic combat
operations resolve for every actor, hero included."""


async def request_player_roll(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    kind: RollKind,
    context: Any,
    turn_id: str | None = None,
) -> Event:
    """Asks the player to make a roll of `kind`, appending `roll_requested`
    at `player` visibility -- the player is the one being asked. The
    event's own id is the request id `resolve_roll_request` answers later
    (WI2, AC2).

    Guarded against three ways the model can misuse this instead of
    `roll`/`roll_dice` (sprint 010/10, ← finding: a monster's attack asked
    the player for a "saving throw" that was never the rules', and a
    dice-less `custom` expression such as `"10"` produced a button with
    nothing to roll): `actor_id` must name a member's own character --
    never an NPC or a monster, which have no player to ask; `kind` must be
    one of `_PLAYER_ROLL_KINDS`, never `attack`/`damage`; and a `custom`
    roll's `context['expression']` must contain a `d` -- a bare constant
    is not a roll. Each raises `ValueError` naming what was wrong, exactly
    `dice.derive_formula`'s own pattern for an actionable message the
    model can act on next turn, before any event is written.

    Idempotent within one turn (sprint 010/09, ← finding): when `turn_id`
    is given and an unanswered `roll_requested` for the same actor and kind
    already exists on it, that event is returned again rather than a
    second one being written -- see `_find_pending_roll_request`."""
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    if actor.member_id is None:
        raise ValueError(
            f"request_player_roll is for a player character only; {actor_id!r} "
            "is not one of the party's own characters -- roll for it with roll_dice instead."
        )
    if kind not in _PLAYER_ROLL_KINDS:
        raise ValueError(
            f"request_player_roll cannot ask for a {kind!r} roll -- only "
            f"{sorted(_PLAYER_ROLL_KINDS)} are the player's to roll; an attack or damage "
            "roll, for any actor including the hero, goes through roll_dice."
        )
    if kind == "custom":
        expression = context.get("expression") if isinstance(context, dict) else None
        if not expression or "d" not in str(expression).casefold():
            raise ValueError(
                f"a custom player roll must name a dice expression in context['expression'] "
                f"(e.g. '2d6+1'), got {expression!r} -- a plain number is not a roll."
            )
    if turn_id is not None:
        pending = await _find_pending_roll_request(
            db, run_id=run.id, turn_id=turn_id, actor_id=actor_id, kind=kind
        )
        if pending is not None:
            return pending
    event = await _append_roll_requested(
        db, run=run, actor=actor, kind=kind, context=context, visibility="player", turn_id=turn_id
    )
    await db.commit()
    await db.refresh(event)
    return event


async def _find_roll_answering(db: AsyncSession, *, run_id: str, request_id: str) -> Event | None:
    """The `roll` event, if any, whose own `request_id` already answers
    `request_id` -- read through `RollPayload` rather than a raw dict key,
    for the same reason `_find_pending_roll_request` does."""
    stmt = select(Event).where(Event.campaign_run_id == run_id, Event.type == "roll")
    result = await db.execute(stmt)
    for candidate in result.scalars().all():
        if RollPayload.model_validate(candidate.payload).request_id == request_id:
            return candidate
    return None


async def resolve_roll_request(
    db: AsyncSession, *, user_id: str, request_id: str, turn_id: str | None = None
) -> Event:
    """Answers the `roll_requested` event named `request_id` with a `roll`,
    re-using its stored `formula`, `kind`, `actor_id` and `visibility`
    verbatim (WI2, AC2).

    Idempotent (sprint 010/09, ← finding): a second call naming a
    `request_id` that already has a `roll` -- the `request_player_roll`
    tool calling this again because its own enclosing LangGraph node
    replayed on resume -- returns that `roll` again rather than rolling a
    second time."""
    request_event = await _get_roll_request_event(db, request_id)
    run = await _require_ready_or_active_run(
        db, run_id=request_event.campaign_run_id, user_id=user_id
    )
    existing = await _find_roll_answering(db, run_id=run.id, request_id=request_id)
    if existing is not None:
        return existing
    event = await _append_roll(db, run=run, request_event=request_event, turn_id=turn_id)
    await db.commit()
    await db.refresh(event)
    return event


async def roll(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    kind: RollKind,
    context: Any,
    visibility: str = "dm",
    turn_id: str | None = None,
) -> Event:
    """Requests and answers a roll in one call, both at `visibility` (`dm`
    by default -- a roll nobody was asked to make). Appends both
    `roll_requested` and `roll`; the latter is returned (WI2, AC2)."""
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    requested = await _append_roll_requested(
        db,
        run=run,
        actor=actor,
        kind=kind,
        context=context,
        visibility=visibility,
        turn_id=turn_id,
    )
    event = await _append_roll(db, run=run, request_event=requested, turn_id=turn_id)
    await db.commit()
    await db.refresh(event)
    return event


async def request_hero_initiative(
    db: AsyncSession,
    *,
    user_id: str,
    hero_ids: list[str],
    turn_id: str | None = None,
) -> Event:
    """Asks the hero side to roll initiative (WI1, AC1/AC4, intent §1.3:
    "one hero-side roll"): scans `hero_ids` for the first id that carries
    a `member_id` -- a player's own character -- and asks it to roll
    through `request_player_roll`, a player's own click still deciding
    the hero side's roll, exactly as the old `_roll_for_side` did for a
    member-holding side. A side with no member on it (never expected in
    practice, but not assumed) falls back to rolling its own first id
    outright, through `roll` at `player` visibility, so this never raises
    for an empty scan. Returns the `roll_requested` event -- unanswered
    until the player resolves it -- for `settle_initiative` to settle
    against once it exists."""
    for candidate_id in hero_ids:
        candidate = await _get_game_object(db, candidate_id)
        if candidate.member_id is not None:
            return await request_player_roll(
                db,
                user_id=user_id,
                actor_id=candidate_id,
                kind="initiative",
                context={},
                turn_id=turn_id,
            )
    return await roll(
        db,
        user_id=user_id,
        actor_id=hero_ids[0],
        kind="initiative",
        context={},
        visibility="player",
        turn_id=turn_id,
    )


async def settle_initiative(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    hero_roll_id: str,
    hero_ids: list[str],
    hostile_ids: list[str],
    turn_id: str | None = None,
) -> InitiativeResult:
    """Settles a stable side and actor order once per fight (WI1, AC1/AC2,
    intent §1.3): `hero_roll_id` must already be a resolved `roll` event
    -- `request_hero_initiative`'s own return, once the player has
    answered it (`RollNotFoundError` otherwise, exactly `_get_roll_event`'s
    own refusal for any other roll-spending call, since there is nothing
    to settle against yet). The hostile side then rolls automatically,
    through `roll` at `player` visibility -- an initiative roll is not
    DM-only bookkeeping. The two totals decide `winning_side`, the hero
    side winning a tie; `order` lists every actor id, the winning side
    first then the other, each side keeping its own given id order.
    Nothing about the fight is stored anywhere else (← D7, 003-D8): no
    encounter, no turn order, no `in_combat` flag, on this call or any
    other in this module."""
    await _require_ready_or_active_run(db, run_id=run_id, user_id=user_id)
    hero_event = await _get_roll_event(db, hero_roll_id)
    hostile_event = await roll(
        db,
        user_id=user_id,
        actor_id=hostile_ids[0],
        kind="initiative",
        context={},
        visibility="player",
        turn_id=turn_id,
    )
    hero_total = RollPayload.model_validate(hero_event.payload).total
    hostile_total = RollPayload.model_validate(hostile_event.payload).total
    winning_side: Literal["hero", "hostile"] = "hostile" if hostile_total > hero_total else "hero"
    order = [*hero_ids, *hostile_ids] if winning_side == "hero" else [*hostile_ids, *hero_ids]
    return InitiativeResult(
        hero_total=hero_total,
        hostile_total=hostile_total,
        hero_roll_id=hero_event.id,
        hostile_roll_id=hostile_event.id,
        winning_side=winning_side,
        order=order,
    )


def authored_check(entry: Secret | FixtureCheck) -> tuple[AbilityName, str | None, int]:
    """Pulls the mechanics -- ability, skill, DC -- off an authored `Secret`
    or `FixtureCheck` verbatim, never off its prose (`fact`/`action`,
    `success`, `discovered_by`). The one place a check built from content
    turns authored fields into the tuple `passive_check`, `resolve_check`
    and `resolve_save`'s own callers pass on: nothing here rolls a die or
    writes an event."""
    return entry.ability, entry.skill, entry.dc


async def passive_check(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    ability: str,
    dc: int,
    turn_id: str | None = None,
    skill: str | None = None,
) -> bool:
    """A passive score -- `10` plus the named ability's modifier, no die
    rolled at all -- against `dc`. Recorded as a `tool_call` at `dm`, never
    a `roll`: it has no faces and must never be consumable by a later
    sprint's check consumer (WI2, AC2). `skill`, when an authored check or
    secret named one (`authored_check`), rides along in the same event
    payload/args purely as a record -- it never changes the modifier,
    which is always the named ability's own."""
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    abilities = dice._actor_abilities(
        actor, campaign_id=run.campaign_id, version=run.content_version
    )
    modifier = dice.ability_modifier(getattr(abilities, ability))
    passive_score = 10 + modifier
    success = passive_score >= dc
    await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "passive_check",
            "args": {"actorId": actor_id, "ability": ability, "skill": skill, "dc": dc},
            "roll_ids": [],
            "result": "ok",
            "outcome": {"passiveScore": passive_score, "dc": dc, "success": success},
        },
    )
    await db.commit()
    return success


async def ask_player(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    text: str,
    options: list[str],
    turn_id: str | None = None,
) -> Event:
    """Puts a question to the player -- the next `player_action` may answer
    it (`PlayerActionPayload.answers_question_id`). Appends `question` at
    `player` visibility (WI2, AC4a)."""
    run = await _require_ready_or_active_run(db, run_id=run_id, user_id=user_id)
    event = await append_event(
        db,
        run_id=run.id,
        type="question",
        visibility="player",
        turn_id=turn_id,
        payload={"text": text, "options": options},
    )
    await db.commit()
    await db.refresh(event)
    return event


async def _get_roll_event(db: AsyncSession, roll_id: str) -> Event:
    """The `roll` event named `roll_id`, with no run context yet --
    `resolve_check`/`resolve_save` learn which run to gate from this row's
    own `campaign_run_id`, exactly the way `_get_roll_request_event` learns
    `resolve_roll_request`'s run from the `roll_requested` event it
    answers. An unknown id, or one that names an event of any other type,
    is refused identically (`RollNotFoundError`): there is nothing to
    disambiguate them by.
    """
    result = await db.execute(select(Event).where(Event.id == roll_id))
    event = result.scalar_one_or_none()
    if event is None or event.type != "roll":
        raise RollNotFoundError(roll_id)
    return event


async def _roll_already_spent(
    db: AsyncSession, *, run_id: str, roll_id: str, turn_id: str | None
) -> bool:
    """True when some *successful* `tool_call` in this run-and-turn already
    named `roll_id` in its `rollIds` -- the subtle half of `_consume_roll`
    (WI1, I2): a merely `refused` attempt is never searched here, so it can
    never burn the roll it named.
    """
    stmt = select(Event.payload).where(Event.campaign_run_id == run_id, Event.type == "tool_call")
    stmt = stmt.where(Event.turn_id.is_(None) if turn_id is None else Event.turn_id == turn_id)
    result = await db.execute(stmt)
    return any(
        payload["result"] == "ok" and roll_id in payload["rollIds"]
        for payload in result.scalars().all()
    )


async def _consume_roll(
    db: AsyncSession, *, run_id: str, roll_id: str, kind: RollKind, turn_id: str | None
) -> Event:
    """Decides, from the transcript alone, whether `roll_id` may be spent
    as a `kind` roll in `run_id`'s open turn -- no consumption column
    anywhere (WI1, I2).

    In order: the event exists, is a `roll`, and belongs to `run_id`
    (`RollNotFoundError` otherwise -- indistinguishable from an unknown id,
    ← D12); its `kind` matches (a `custom` roll therefore fails every
    check, deliberately) and its `turn_id` equals `turn_id` (`None` counts
    as equal to `None`); it has not already been spent by an earlier
    *successful* `tool_call` naming it. The last two conditions both raise
    `RollNotUsableError` -- the caller records the refusal and commits it
    before re-raising, this function never touches the transcript itself.
    Returns the `roll` event when it may be spent.
    """
    event = await _get_roll_event(db, roll_id)
    if event.campaign_run_id != run_id:
        raise RollNotFoundError(roll_id)
    if event.payload["kind"] != kind or event.turn_id != turn_id:
        raise RollNotUsableError(roll_id)
    if await _roll_already_spent(db, run_id=run_id, roll_id=roll_id, turn_id=turn_id):
        raise RollNotUsableError(roll_id)
    return event


async def _refuse_roll(
    db: AsyncSession,
    *,
    run_id: str,
    name: str,
    roll_id: str,
    dc: int,
    turn_id: str | None,
    reason: str,
) -> None:
    """Records a roll-spending refusal where only the DM sees it (← D11)
    and commits it alone -- the pattern `_refuse_exit` established:
    `append_event` only flushes, and the caller's rollback on the way to
    raising would erase the record. Names `roll_id` in `roll_ids` too, for
    the record -- safe against `_roll_already_spent`'s scan, which only
    ever looks at `result: "ok"` entries, never a `refused` one.
    """
    await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": name,
            "args": {"rollId": roll_id, "dc": dc},
            "roll_ids": [roll_id],
            "result": "refused",
            "outcome": {"reason": reason},
        },
    )
    await db.commit()


async def _resolve_roll_outcome(
    db: AsyncSession,
    *,
    user_id: str,
    roll_id: str,
    dc: int,
    kind: RollKind,
    name: str,
    turn_id: str | None,
) -> bool:
    """Shared by `resolve_check` and `resolve_save`: turns `roll_id` into
    pass or fail against `dc`, differing only in which `RollKind` the roll
    must be and which mechanic name the transcript records (WI1, AC3).

    Pass or fail lives on this call's own `tool_call`, never on the roll
    itself (← D11) -- `_consume_roll` decides only whether the roll may be
    spent, never what spending it means. `dc` outside 5-30 (← D6) and a
    roll `_consume_roll` refuses are each recorded as a refusal and
    committed (`_refuse_roll`) before the matching error is raised; an
    unknown roll id, or one on a foreign run, surfaces as `NOT_FOUND`
    before any run is known to record a refusal into, exactly like every
    other lookup in this module (← D12).
    """
    roll_event = await _get_roll_event(db, roll_id)
    run = await _require_ready_or_active_run(db, run_id=roll_event.campaign_run_id, user_id=user_id)

    if not (_MIN_DC <= dc <= _MAX_DC):
        await _refuse_roll(
            db,
            run_id=run.id,
            name=name,
            roll_id=roll_id,
            dc=dc,
            turn_id=turn_id,
            reason=f"dc {dc} is outside {_MIN_DC}-{_MAX_DC}",
        )
        raise InvalidDcError(dc)

    try:
        consumed = await _consume_roll(
            db, run_id=run.id, roll_id=roll_id, kind=kind, turn_id=turn_id
        )
    except RollNotUsableError:
        await _refuse_roll(
            db,
            run_id=run.id,
            name=name,
            roll_id=roll_id,
            dc=dc,
            turn_id=turn_id,
            reason="roll already spent, from another turn, or of another kind",
        )
        raise

    total = consumed.payload["total"]
    success = total >= dc
    await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": name,
            "args": {"rollId": roll_id, "dc": dc},
            "roll_ids": [roll_id],
            "result": "ok",
            "outcome": {"total": total, "dc": dc, "success": success},
        },
    )
    await db.commit()
    return success


async def resolve_check(
    db: AsyncSession, *, user_id: str, roll_id: str, dc: int, turn_id: str | None = None
) -> bool:
    """Spends an `ability_check` roll against `dc`, appending the pass/fail
    outcome on its own `tool_call` (WI1, AC3). See `_resolve_roll_outcome`
    for the shared gate order, refusal recording and consumption rule."""
    return await _resolve_roll_outcome(
        db,
        user_id=user_id,
        roll_id=roll_id,
        dc=dc,
        kind="ability_check",
        name="resolve_check",
        turn_id=turn_id,
    )


async def resolve_save(
    db: AsyncSession, *, user_id: str, roll_id: str, dc: int, turn_id: str | None = None
) -> bool:
    """Spends a `saving_throw` roll against `dc`, appending the pass/fail
    outcome on its own `tool_call` (WI1, AC3). See `_resolve_roll_outcome`
    for the shared gate order, refusal recording and consumption rule."""
    return await _resolve_roll_outcome(
        db,
        user_id=user_id,
        roll_id=roll_id,
        dc=dc,
        kind="saving_throw",
        name="resolve_save",
        turn_id=turn_id,
    )


async def _refuse_exit(
    db: AsyncSession, *, run_id: str, actor_id: str, exit_id: str, reason: str
) -> None:
    """Records the refusal where only the DM sees it (AC2, ← D11) and
    commits it alone -- the exit check runs before any other state change,
    so nothing else is pending, and this commit writes exactly that one
    row. `append_event` only flushes; without this commit, a rollback
    anywhere between here and the caller would erase the record before the
    caller returns a typed refusal.
    """
    await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        payload={
            "name": "use_exit",
            "args": {"actorId": actor_id, "exitId": exit_id},
            "roll_ids": [],
            "result": "refused",
            "outcome": {"reason": reason},
        },
    )
    await db.commit()


async def use_exit(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    exit_id: str,
    turn_id: str | None = None,
) -> MutationResult:
    """Moves `actor_id` through `exit_id`, or -- on an `adventure_end`
    exit -- completes its adventure and, when that adventure is the pinned
    campaign's last, finishes the whole game (WI1, AC2/AC3; sprint 011/03,
    WI1: typed result, `turn_id`).

    Loads the object by `actor_id` alone (`GameObjectNotFoundError` if none
    answers), then `_require_member(run_id=obj.campaign_run_id, ...)` so a
    foreign actor answers identically to an unknown one, `_require_writable`,
    and the run's status must be `ready` or `active`
    (`InvalidRunStatusError` otherwise) -- the same gate order every other
    write in this module uses.

    The actor's current scene is read through
    `content.service.load_scene` for the run's **pinned** `content_version`,
    and `exit_id` is matched among that scene's own exits. `Exit.condition`
    is never read here -- it is prose the agent weighs before ever calling
    this tool, not something the mechanic enforces (← D8). An actor with no
    scene at all (`scene_id` is `None`) never reaches `load_scene`; it
    falls straight through to the same refusal as an unmatched `exit_id` --
    one error class for both (← D11).

    The check runs before any state change. On failure, `_refuse_exit`
    records and commits the refusal, and this function returns a typed
    refusal rather than raising -- an unmatched exit is an expected
    mechanic refusal (← research), not a programming error.

    `kind='scene'` rewrites the actor's `scene_id` to `exit.to`
    (`adventure_run_id` untouched -- an exit only ever changes where within
    an adventure someone stands) and appends `scene_entered` at `player`,
    carrying the destination's own pinned `sceneTitle` (sprint 010/04, I2:
    read through `content_service.load_scene`, never a tool argument).
    `kind='adventure_end'` completes the actor's adventure run -- `status`
    and `completed_at` set together on the one loaded row, so they reach
    the database in the same UPDATE and never violate the CHECK that ties
    them -- and appends `adventure_completed` at `player`; when that
    adventure is the last id the pinned campaign declares (read from the
    pinned content, never the `adventure_runs` table), the campaign run
    itself finishes through `finish_run(outcome="authored")` (sprint
    011/03, WI2) rather than this function writing `status` itself. No
    position is touched either way: nobody is moved or cleared away when
    an adventure ends. Either outcome then also appends a successful
    `tool_call` at `dm` (← D11; unlike `enter_adventure`, which is a route
    rather than a tool) before the one commit that closes the call.

    `facts`: `{"kind": "scene"|"adventure_end", "sceneId": str|None,
    "runFinished": bool}`.
    """
    obj = await _get_game_object(db, actor_id)
    await _require_member(db, run_id=obj.campaign_run_id, user_id=user_id)
    run = await _get_run(db, obj.campaign_run_id)
    _require_writable(run)

    if run.status not in ("ready", "active"):
        raise InvalidRunStatusError(run.id)

    exit_ = None
    if obj.scene_id is not None:
        scene = content_service.load_scene(run.campaign_id, run.content_version, obj.scene_id)
        exit_ = next((candidate for candidate in scene.exits if candidate.id == exit_id), None)

    if exit_ is None:
        reason = (
            "actor has no current scene"
            if obj.scene_id is None
            else f"exit '{exit_id}' is not on the actor's current scene"
        )
        await _refuse_exit(db, run_id=run.id, actor_id=actor_id, exit_id=exit_id, reason=reason)
        return MutationResult(status="refused", reason=reason)

    run_finished = False
    if exit_.kind == "scene":
        obj.scene_id = exit_.to
        destination = content_service.load_scene(run.campaign_id, run.content_version, obj.scene_id)
        await append_event(
            db,
            run_id=run.id,
            type="scene_entered",
            visibility="player",
            turn_id=turn_id,
            payload={
                "adventure_run_id": obj.adventure_run_id,
                "scene_id": obj.scene_id,
                "scene_title": destination.title,
            },
        )
    else:
        adventure_run_result = await db.execute(
            select(AdventureRun).where(AdventureRun.id == obj.adventure_run_id)
        )
        adventure_run = adventure_run_result.scalar_one()
        adventure_run.status = "completed"
        adventure_run.completed_at = func.now()
        await append_event(
            db,
            run_id=run.id,
            type="adventure_completed",
            visibility="player",
            turn_id=turn_id,
            payload={"adventure_run_id": adventure_run.id},
        )

        loaded = content_service.load_campaign(run.campaign_id, run.content_version)
        if adventure_run.adventure_id == loaded.campaign.adventures[-1]:
            await append_event(
                db,
                run_id=run.id,
                type="tool_call",
                visibility="dm",
                turn_id=turn_id,
                payload={
                    "name": "use_exit",
                    "args": {"actorId": actor_id, "exitId": exit_id},
                    "roll_ids": [],
                    "result": "ok",
                    "outcome": {},
                },
            )
            await db.commit()
            finish_result = await finish_run(
                db, user_id=user_id, run_id=run.id, outcome="authored", turn_id=turn_id
            )
            return MutationResult(
                status="ok",
                event_ids=list(finish_result.event_ids),
                facts={"kind": "adventure_end", "sceneId": None, "runFinished": True},
            )

    await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "use_exit",
            "args": {"actorId": actor_id, "exitId": exit_id},
            "roll_ids": [],
            "result": "ok",
            "outcome": {},
        },
    )
    await db.commit()
    return MutationResult(
        status="ok",
        facts={
            "kind": "scene" if exit_.kind == "scene" else "adventure_end",
            "sceneId": obj.scene_id if exit_.kind == "scene" else None,
            "runFinished": run_finished,
        },
    )


async def _refuse_interact(
    db: AsyncSession,
    *,
    run_id: str,
    actor_id: str,
    object_id: str,
    action: str,
    roll_id: str | None,
    turn_id: str | None,
    reason: str,
) -> None:
    """Records an `interact` refusal where only the DM sees it (← D11) and
    commits it alone -- `_refuse_exit`'s and `_refuse_roll`'s own pattern:
    `append_event` only flushes, and the caller's rollback on the way to
    raising would erase the record. `rollId` is named in `args` only when
    one was given (WI1, I2), matching what a successful call itself
    records.
    """
    args: dict[str, Any] = {"actorId": actor_id, "objectId": object_id, "action": action}
    if roll_id is not None:
        args["rollId"] = roll_id
    await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "interact",
            "args": args,
            "roll_ids": [roll_id] if roll_id is not None else [],
            "result": "refused",
            "outcome": {"reason": reason},
        },
    )
    await db.commit()


async def interact(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    object_id: str,
    action: str,
    roll_id: str | None = None,
    turn_id: str | None = None,
) -> MutationResult:
    """Applies the fixture at `object_id`'s own authored `FixtureCheck` for
    `action` -- passing on an `ability_check` roll `>= dc`, or, with no
    roll, on an item the actor already carries that the check's own
    `bypassed_by` names (WI1, AC1; sprint 011/03, WI1: typed result, and a
    successful check now opens the fixture *durably*).

    Gate order, shared by every acting mechanic in this module:
    `_resolve_actor_and_run` first, exactly `use_exit`'s own gate (an
    unknown or foreign actor, an archived run, a run outside `ready`/
    `active` each raise before anything else runs) -- then this
    mechanic's own checks, then the write, then a `tool_call` `ok`, then
    one commit. The one-action-per-turn scan is retired (← research):
    every acting mechanic may be called freely within a turn.

    `object_id` is loaded with no run filter first, the same way
    `use_exit` loads its actor -- an object on a foreign run answers
    identically to an unknown one (← D12), `GameObjectNotFoundError`
    either way, before any refusal can be recorded. A `kind` other than
    `fixture` -- or a `fixture` with no `template_id`, which cannot
    happen for seeded content but is guarded against here regardless --
    is a typed refusal, indistinguishable from an unmatched `action`:
    neither has an authored check to weigh. `action` matches a
    `FixtureCheck.action` by exact string equality only (phase 8's tool
    layer offers the authored strings verbatim); no match is the same
    refusal.

    With `roll_id` given, it is consumed through `_consume_roll` at
    `kind="ability_check"` -- 07b's one implementation, never a second one
    -- so an unknown roll surfaces as `NOT_FOUND` before any refusal is
    recorded (exactly `resolve_check`/`resolve_save`'s own precedent, ←
    D12), while a wrong-kind or already-spent roll is refused and
    committed (`RollNotUsableError`, mapped to `ROLL_NOT_USABLE`) before
    being re-raised -- roll errors keep raising (← research). Its `total`
    decides `success` against the check's `dc`; a failed check is still
    `ok`, not a refusal (the world simply does not open).

    With no `roll_id`, the check's own `bypassed_by` is consulted -- never
    otherwise -- for a `GameObject` this actor owns
    (`owner_object_id = actor.id`) whose `template_id` is named there; a
    match passes with no roll, its id reported as `facts.bypassedBy`. No
    match is a typed refusal (missing bypass item, ← research).

    Sprint 010/04, I2: `success` alone also appends `way_opened` at
    `player` visibility, before the `dm`-only `tool_call` -- naming the
    actor, the object and `action` verbatim (authored content, never the
    model's own words). A failed check changed nothing in the world and
    leaves no such row, though its `tool_call` still records `ok`.

    Sprint 011/03, WI1, AC1: `success` alone also persists
    `obj.state["fixture_outcomes"][action] = {"success": <the authored
    success prose>, "turnId": turn_id}` -- reassigning `obj.state` whole
    so SQLAlchemy sees the change (the module's own JSONB house rule). A
    present key means the fixture stays open across reloads; a failed
    check writes nothing, so a later, successful attempt at the same
    `action` can still open it.

    `facts`: `{"success": bool, "dc": int, "total": int|None,
    "bypassedBy": str|None, "outcome": str}`.
    """
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)

    obj = await _get_game_object(db, object_id)
    if obj.campaign_run_id != run.id:
        raise GameObjectNotFoundError(object_id)

    if obj.kind != "fixture" or obj.template_id is None:
        reason = "object is not a fixture"
        await _refuse_interact(
            db,
            run_id=run.id,
            actor_id=actor_id,
            object_id=object_id,
            action=action,
            roll_id=roll_id,
            turn_id=turn_id,
            reason=reason,
        )
        return MutationResult(status="refused", reason=reason)

    template = content_service.load_object_template(
        run.campaign_id, run.content_version, obj.template_id
    )
    check = next((candidate for candidate in template.checks if candidate.action == action), None)
    if check is None:
        reason = f"no check answers action {action!r}"
        await _refuse_interact(
            db,
            run_id=run.id,
            actor_id=actor_id,
            object_id=object_id,
            action=action,
            roll_id=roll_id,
            turn_id=turn_id,
            reason=reason,
        )
        return MutationResult(status="refused", reason=reason)

    total: int | None = None
    bypassed_by: str | None = None

    if roll_id is not None:
        try:
            consumed = await _consume_roll(
                db, run_id=run.id, roll_id=roll_id, kind="ability_check", turn_id=turn_id
            )
        except RollNotUsableError:
            await _refuse_interact(
                db,
                run_id=run.id,
                actor_id=actor_id,
                object_id=object_id,
                action=action,
                roll_id=roll_id,
                turn_id=turn_id,
                reason="roll already spent, from another turn, or of another kind",
            )
            raise
        total = consumed.payload["total"]
        success = total >= check.dc
    else:
        if check.bypassed_by:
            bypass_result = await db.execute(
                select(GameObject.id).where(
                    GameObject.owner_object_id == actor.id,
                    GameObject.template_id.in_(check.bypassed_by),
                )
            )
            bypassed_by = bypass_result.scalars().first()
        if bypassed_by is None:
            reason = "the check needs a roll and nothing carried bypasses it"
            await _refuse_interact(
                db,
                run_id=run.id,
                actor_id=actor_id,
                object_id=object_id,
                action=action,
                roll_id=roll_id,
                turn_id=turn_id,
                reason=reason,
            )
            return MutationResult(status="refused", reason=reason)
        success = True

    outcome: dict[str, Any] = {"action": action, "dc": check.dc}
    if total is not None:
        outcome["total"] = total
    if bypassed_by is not None:
        outcome["bypassedBy"] = bypassed_by
    outcome["success"] = success

    args: dict[str, Any] = {"actorId": actor_id, "objectId": object_id, "action": action}
    if roll_id is not None:
        args["rollId"] = roll_id

    if success:
        await append_event(
            db,
            run_id=run.id,
            type="way_opened",
            visibility="player",
            turn_id=turn_id,
            payload={
                "actor_id": actor_id,
                "actor_name": actor.name,
                "object_id": object_id,
                "object_name": obj.name,
                "action": action,
            },
        )
        fixture_outcomes = dict(obj.state.get("fixture_outcomes", {}))
        fixture_outcomes[action] = {"success": check.success, "turnId": turn_id}
        obj.state = {**obj.state, "fixture_outcomes": fixture_outcomes}

    tool_call_event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "interact",
            "args": args,
            "roll_ids": [roll_id] if roll_id is not None else [],
            "result": "ok",
            "outcome": outcome,
        },
    )
    await db.commit()
    return MutationResult(
        status="ok",
        event_ids=[tool_call_event.id],
        facts={
            "success": success,
            "dc": check.dc,
            "total": total,
            "bypassedBy": bypassed_by,
            "outcome": "success" if success else "failure",
        },
    )


async def _item_reachable(db: AsyncSession, *, actor: GameObject, item: GameObject) -> bool:
    """Whether `item` lies somewhere `actor` could pick it up from right
    now (WI1, AC2/AC5) -- consulted by `take` alone.

    An actor with no current scene reaches nothing, checked first so it
    can never be fooled by an also-unpositioned item (both `scene_id`
    columns `None` would otherwise compare equal by accident). An unowned
    item is reachable exactly when it shares the actor's own
    `adventure_run_id` and `scene_id`. An owned item is reachable only
    through this sprint's widening (AC5): its owner must itself be a
    *non-creature* object -- a container such as `wool-sack` -- standing
    in the actor's scene; an item another *creature* carries, anywhere,
    stays unreachable. One `owner_object_id` hop only, matching the
    schema's own carried/positioned split -- no nested containers.
    """
    if actor.scene_id is None:
        return False

    if item.owner_object_id is None:
        return item.adventure_run_id == actor.adventure_run_id and item.scene_id == actor.scene_id

    owner = await _get_game_object(db, item.owner_object_id)
    if owner.kind == "creature":
        return False
    return owner.adventure_run_id == actor.adventure_run_id and owner.scene_id == actor.scene_id


async def _load_run_object(db: AsyncSession, object_id: str, *, run_id: str) -> GameObject:
    """`_get_game_object`, then the same foreign-run check `interact` runs
    against `object_id` (← D12): a row belonging to another run answers
    identically to no row at all, before any refusal can be recorded.
    Shared by every WI1 mechanic that loads an item or a second actor by
    id."""
    obj = await _get_game_object(db, object_id)
    if obj.campaign_run_id != run_id:
        raise GameObjectNotFoundError(object_id)
    return obj


async def _refuse_move(
    db: AsyncSession,
    *,
    run_id: str,
    name: str,
    args: dict[str, Any],
    turn_id: str | None,
    reason: str,
) -> None:
    """Records a `take`/`drop`/`give` refusal where only the DM sees it
    (← D11) and commits it alone -- `_refuse_interact`'s and
    `_refuse_exit`'s own pattern, generalised across the mechanics this
    file adds: `append_event` only flushes, and the caller's rollback
    on the way to raising would erase the record. `args` is exactly what
    the matching successful call would have recorded (WI1, I3)."""
    await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": name,
            "args": args,
            "roll_ids": [],
            "result": "refused",
            "outcome": {"reason": reason},
        },
    )
    await db.commit()


async def take(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    item_id: str,
    turn_id: str | None = None,
) -> MutationResult:
    """Picks `item_id` up: sets its `owner_object_id` to `actor_id` and
    clears its position (WI1, AC2), from either the floor of the actor's
    own scene or -- this sprint's widening -- a non-creature container
    standing there too (AC5, `_item_reachable`).

    Gate order shared with `interact`: `_resolve_actor_and_run` ->
    reachability -> the write -> a `tool_call` `ok` -> one commit
    (sprint 011/03, WI1: the one-action check is retired, ← research).
    `item_id` is loaded with no run filter first, exactly `object_id` in
    `interact` (← D12): unknown and foreign both raise
    `GameObjectNotFoundError` before any refusal is recorded. An
    unreachable item -- another scene, carried by another creature, or
    the actor standing nowhere -- is a typed refusal, recorded and
    committed first (← research).

    Sprint 010/04, I2: a successful move also appends `item_moved` at
    `player` visibility, before the `dm`-only `tool_call` -- `movement:
    "taken"`, naming the actor and the item by their stored `name`s, never
    a tool argument (AC4). The refusal paths above are unchanged.
    """
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    args = {"actorId": actor_id, "itemId": item_id}

    item = await _load_run_object(db, item_id, run_id=run.id)

    if not await _item_reachable(db, actor=actor, item=item):
        reason = "item is not reachable from the actor's current scene"
        await _refuse_move(
            db,
            run_id=run.id,
            name="take",
            args=args,
            turn_id=turn_id,
            reason=reason,
        )
        return MutationResult(status="refused", reason=reason)

    item.owner_object_id = actor.id
    item.adventure_run_id = None
    item.scene_id = None

    await append_event(
        db,
        run_id=run.id,
        type="item_moved",
        visibility="player",
        turn_id=turn_id,
        payload={
            "movement": "taken",
            "actor_id": actor_id,
            "actor_name": actor.name,
            "item_id": item_id,
            "item_name": item.name,
        },
    )
    tool_call_event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={"name": "take", "args": args, "roll_ids": [], "result": "ok", "outcome": {}},
    )
    await db.commit()
    return MutationResult(status="ok", event_ids=[tool_call_event.id])


async def drop(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    item_id: str,
    turn_id: str | None = None,
) -> MutationResult:
    """Puts `item_id` down: clears its `owner_object_id` and positions it
    into the actor's own scene and adventure run (WI1, AC2).

    Gate order: `_resolve_actor_and_run`, then straight to the mechanic's
    own check -- **no one-action check**, dropping is free either way (←
    I2, the product owner's ruling, `decisions/mechanics.md`; 08a's
    action set already excludes `drop`, unchanged here). `item_id` is
    loaded with no run filter first, exactly `take`'s own
    `_load_run_object` (← D12). A typed refusal when the item is not
    currently carried by this actor, or the actor has no current scene to
    drop it into -- recorded and committed first (← research).

    Sprint 010/04, I2: a successful move also appends `item_moved` at
    `player` visibility (`movement: "dropped"`), before the `dm`-only
    `tool_call` -- unchanged on the refusal path.
    """
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    args = {"actorId": actor_id, "itemId": item_id}

    item = await _load_run_object(db, item_id, run_id=run.id)

    if item.owner_object_id != actor.id or actor.scene_id is None:
        reason = "item is not carried by the actor, or the actor has no current scene"
        await _refuse_move(
            db,
            run_id=run.id,
            name="drop",
            args=args,
            turn_id=turn_id,
            reason=reason,
        )
        return MutationResult(status="refused", reason=reason)

    item.owner_object_id = None
    item.adventure_run_id = actor.adventure_run_id
    item.scene_id = actor.scene_id

    await append_event(
        db,
        run_id=run.id,
        type="item_moved",
        visibility="player",
        turn_id=turn_id,
        payload={
            "movement": "dropped",
            "actor_id": actor_id,
            "actor_name": actor.name,
            "item_id": item_id,
            "item_name": item.name,
        },
    )
    tool_call_event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={"name": "drop", "args": args, "roll_ids": [], "result": "ok", "outcome": {}},
    )
    await db.commit()
    return MutationResult(status="ok", event_ids=[tool_call_event.id])


async def give(
    db: AsyncSession,
    *,
    user_id: str,
    from_id: str,
    to_id: str,
    item_id: str,
    turn_id: str | None = None,
) -> MutationResult:
    """Re-owns `item_id` from `from_id` to `to_id` -- one carrier handing
    something to another (WI1, AC2). Recorded `args` name the giver
    `actorId`, so one key always names the actor (I3).

    Gate order shared with `take`: `_resolve_actor_and_run` on the giver ->
    the mechanic's own checks -> the write -> a `tool_call` `ok` -> one
    commit (sprint 011/03, WI1: the one-action check is retired, ←
    research). Both `item_id` and `to_id` are loaded with no run filter
    first, exactly `take`'s own `_load_run_object` (← D12): unknown or
    foreign either way raises `GameObjectNotFoundError` before any
    refusal is recorded.

    A typed refusal -- recorded and committed first (← research) --
    unless the item is currently carried by the giver *and* the receiver
    is a creature sharing the giver's own scene: give never reaches
    across scenes, never hands over something the giver does not itself
    carry, and never hands to anything but another creature.

    Sprint 010/04, I2: a successful move also appends `item_moved` at
    `player` visibility (`movement: "given"`, `toId`/`toName` naming the
    receiver -- the only case either is set), before the `dm`-only
    `tool_call` -- unchanged on the refusal path.
    """
    giver, run = await _resolve_actor_and_run(db, actor_id=from_id, user_id=user_id)
    args = {"actorId": from_id, "toId": to_id, "itemId": item_id}

    item = await _load_run_object(db, item_id, run_id=run.id)
    receiver = await _load_run_object(db, to_id, run_id=run.id)

    reachable = (
        item.owner_object_id == giver.id
        and receiver.kind == "creature"
        and giver.scene_id is not None
        and receiver.adventure_run_id == giver.adventure_run_id
        and receiver.scene_id == giver.scene_id
    )
    if not reachable:
        reason = (
            "item is not carried by the giver, or the receiver is not a creature "
            "sharing the giver's scene"
        )
        await _refuse_move(
            db,
            run_id=run.id,
            name="give",
            args=args,
            turn_id=turn_id,
            reason=reason,
        )
        return MutationResult(status="refused", reason=reason)

    item.owner_object_id = receiver.id

    await append_event(
        db,
        run_id=run.id,
        type="item_moved",
        visibility="player",
        turn_id=turn_id,
        payload={
            "movement": "given",
            "actor_id": from_id,
            "actor_name": giver.name,
            "item_id": item_id,
            "item_name": item.name,
            "to_id": to_id,
            "to_name": receiver.name,
        },
    )
    tool_call_event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={"name": "give", "args": args, "roll_ids": [], "result": "ok", "outcome": {}},
    )
    await db.commit()
    return MutationResult(status="ok", event_ids=[tool_call_event.id])


async def _refuse_attack(
    db: AsyncSession,
    *,
    run_id: str,
    actor_id: str,
    target_id: str,
    item_id: str | None,
    roll_id: str,
    turn_id: str | None,
    reason: str,
) -> None:
    """Records an `attack` refusal where only the DM sees it (← D11) and
    commits it alone -- `_refuse_interact`'s own pattern: `append_event`
    only flushes, and the caller's rollback on the way to raising would
    erase the record. `itemId` is named in `args` only when one was given
    (a monster's attack from its own stat block never carries one);
    `rollId` is always named, `roll_id` being a required argument of
    `attack` itself, unlike `interact`'s optional one.
    """
    args: dict[str, Any] = {"actorId": actor_id, "targetId": target_id}
    if item_id is not None:
        args["itemId"] = item_id
    args["rollId"] = roll_id
    await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "attack",
            "args": args,
            "roll_ids": [roll_id],
            "result": "refused",
            "outcome": {"reason": reason},
        },
    )
    await db.commit()


async def attack(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    target_id: str,
    item_id: str | None = None,
    roll_id: str,
    turn_id: str | None = None,
) -> AttackResult:
    """Measures an `attack` roll against `target_id`'s own armour class,
    appending the outcome on a `tool_call` -- never a row (WI1, AC1):
    nothing about a swing landing or missing changes any `objects` row,
    only `damage` ever does that.

    `item_id` is optional: a monster's attack is read from its own stat
    block (`dice.derive_formula`'s own rule), never from an item it
    carries, so `_attacks_for` was already given `context["item_id"] =
    None` when the roll this call consumes was made.

    Gate order, this module's own shared shape: `_resolve_actor_and_run`
    -> `target_id` and, when given, `item_id` loaded with
    no run filter first, exactly `take`'s own `_load_run_object` (← D12):
    unknown or foreign either way raises `GameObjectNotFoundError` before
    any refusal is recorded -> neither actor nor target down (sprint
    011/02, WI3, I3 -- `OBJECT_NOT_REACHABLE`, a downed actor or target
    treated exactly like an unreachable one) -> both actor and target
    sharing one scene (`OBJECT_NOT_REACHABLE` otherwise) -> the item, when
    named, carried by the actor (`OBJECT_NOT_REACHABLE` otherwise) -> the
    roll consumed at
    `kind="attack"` (`ROLL_NOT_USABLE` on a wrong kind, another turn, or
    one already spent). Each of those three refusals is recorded and
    committed before the matching error is raised (← D11).

    A roll's own `faces` are always exactly one die -- `derive_formula`
    only ever hands an attack a single `1d20{+-K}` -- so a **natural 20**
    is legible as `faces == [20]` alone, with no re-roll: it crits
    regardless of what the total would otherwise say against the target's
    armour class. Otherwise a `hit` when the total reaches the target's
    `armour_class`, else a `miss`. `tool_call` `ok`: `args {actorId,
    targetId, itemId?, rollId}`, `roll_ids [roll_id]`, `outcome {outcome,
    total, natural, armourClass}` -- the stored `outcome` string stays
    `hit`/`crit`/`miss` (`_consume_hit`'s own check), the returned
    `AttackResult.status` spells the third one out as `critical` (WI2,
    I2).

    Returns an `AttackResult` naming the `tool_call` event's own id as
    `hit_id` on `hit`/`critical`, `None` on a `miss` -- there is nothing
    for `damage` to consume when nothing landed, and no more scanning the
    transcript for the newest event to guess it (← finding, WI2).
    """
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)

    target = await _load_run_object(db, target_id, run_id=run.id)
    item = None
    if item_id is not None:
        item = await _load_run_object(db, item_id, run_id=run.id)

    if is_down(actor):
        await _refuse_attack(
            db,
            run_id=run.id,
            actor_id=actor_id,
            target_id=target_id,
            item_id=item_id,
            roll_id=roll_id,
            turn_id=turn_id,
            reason="actor is down",
        )
        raise ObjectNotReachableError(actor_id)

    if is_down(target):
        await _refuse_attack(
            db,
            run_id=run.id,
            actor_id=actor_id,
            target_id=target_id,
            item_id=item_id,
            roll_id=roll_id,
            turn_id=turn_id,
            reason="target is down",
        )
        raise ObjectNotReachableError(target_id)

    same_scene = (
        actor.scene_id is not None
        and actor.adventure_run_id == target.adventure_run_id
        and actor.scene_id == target.scene_id
    )
    if not same_scene:
        await _refuse_attack(
            db,
            run_id=run.id,
            actor_id=actor_id,
            target_id=target_id,
            item_id=item_id,
            roll_id=roll_id,
            turn_id=turn_id,
            reason="target is not in the actor's current scene",
        )
        raise ObjectNotReachableError(target_id)

    if item is not None and item.owner_object_id != actor.id:
        await _refuse_attack(
            db,
            run_id=run.id,
            actor_id=actor_id,
            target_id=target_id,
            item_id=item_id,
            roll_id=roll_id,
            turn_id=turn_id,
            reason="item is not carried by the actor",
        )
        raise ObjectNotReachableError(item_id)

    try:
        consumed = await _consume_roll(
            db, run_id=run.id, roll_id=roll_id, kind="attack", turn_id=turn_id
        )
    except RollNotUsableError:
        await _refuse_attack(
            db,
            run_id=run.id,
            actor_id=actor_id,
            target_id=target_id,
            item_id=item_id,
            roll_id=roll_id,
            turn_id=turn_id,
            reason="roll already spent, from another turn, or of another kind",
        )
        raise

    natural = consumed.payload["faces"][0]
    total = consumed.payload["total"]
    armour_class = target.armour_class
    if natural == 20:
        outcome_name = "crit"
    elif total >= armour_class:
        outcome_name = "hit"
    else:
        outcome_name = "miss"

    args: dict[str, Any] = {"actorId": actor_id, "targetId": target_id}
    if item_id is not None:
        args["itemId"] = item_id
    args["rollId"] = roll_id

    hit_event = await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "attack",
            "args": args,
            "roll_ids": [roll_id],
            "result": "ok",
            "outcome": {
                "outcome": outcome_name,
                "total": total,
                "natural": natural,
                "armourClass": armour_class,
            },
        },
    )
    await db.commit()
    return AttackResult(
        status="critical" if outcome_name == "crit" else outcome_name,  # type: ignore[arg-type]
        hit_id=hit_event.id if outcome_name in ("hit", "crit") else None,
        total=total,
        natural=natural,
        armour_class=armour_class,
    )


async def _consume_hit(
    db: AsyncSession, *, run_id: str, hit_id: str, target_id: str, turn_id: str | None
) -> Event:
    """Decides whether `hit_id` -- an `attack` `tool_call`'s own event id --
    may be spent by `damage` (WI1, I2). Unlike `_consume_roll`'s split
    between "does not exist" (`RollNotFoundError`) and "exists but is not
    usable" (`RollNotUsableError`), every one of a hit's failure modes
    collapses into the one new `HitNotUsableError`: a `hit_id` naming
    nothing, or naming something that is not a `tool_call` at all, is no
    more usable than one that names a real `attack` from another run, a
    `miss`, another turn, a mismatched target, or one already spent --
    there is no resource here to have "not found" independently of being
    unusable.

    In order: the event exists and belongs to `run_id`; it is `name ==
    "attack"`, `result == "ok"` and `outcome.outcome` is `hit` or `crit` --
    a `miss` fails here; its `turn_id` equals `turn_id` (`None` counts as
    equal to `None`, `_consume_roll`'s own rule); its own recorded
    `args["targetId"]` equals `target_id` -- the argument is only ever
    checked against the entry's recorded target, never trusted on its own
    (WI1); and no earlier *successful* `damage` this turn already named it
    Hit identity alone decides usability -- no scan for an earlier
    `damage` naming the same `hit_id` (the damaged-hit scan is retired,
    ← research); returns the `tool_call` event when every condition
    holds, never touches the transcript itself.
    """
    result = await db.execute(select(Event).where(Event.id == hit_id))
    event = result.scalar_one_or_none()
    if (
        event is None
        or event.type != "tool_call"
        or event.campaign_run_id != run_id
        or event.payload["name"] != "attack"
        or event.payload["result"] != "ok"
        or event.payload["outcome"]["outcome"] not in ("hit", "crit")
        or event.turn_id != turn_id
        or event.payload["args"].get("targetId") != target_id
    ):
        raise HitNotUsableError(hit_id)
    return event


async def _refuse_damage(
    db: AsyncSession,
    *,
    run_id: str,
    target_id: str,
    roll_id: str,
    hit_id: str,
    turn_id: str | None,
    reason: str,
) -> None:
    """Records a `damage` refusal where only the DM sees it (← D11) and
    commits it alone -- `_refuse_attack`'s own pattern."""
    await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "damage",
            "args": {"targetId": target_id, "rollId": roll_id, "hitId": hit_id},
            "roll_ids": [roll_id],
            "result": "refused",
            "outcome": {"reason": reason},
        },
    )
    await db.commit()


async def damage(
    db: AsyncSession,
    *,
    user_id: str,
    target_id: str,
    roll_id: str,
    hit_id: str,
    turn_id: str | None = None,
    critical: bool = False,
) -> DamageResult:
    """Applies the hit `hit_id` named -- an `attack` `tool_call`'s own
    event id -- to `target_id`, clamped so hit points never fall below 0
    (WI1, AC2). Returns a `DamageResult` naming the hit points actually
    applied.

    `critical=True` (WI2, I2, intent §1.4) doubles the consumed roll's own
    dice -- never the flat modifier: `applied` is derived from `2 *
    sum(faces) + modifier`, not the roll's own `total`. The `damage` roll
    is normally requested and rolled before `attack` settles hit/miss/
    critical, so its own formula is never crit-aware (`dice.derive_
    formula`'s `context={"critical": True}` doubling is for a caller that
    requests the roll already knowing the hit was critical); doubling here
    instead, from the roll's own `faces`/`modifier`, applies the same rule
    -- double the dice, the modifier once -- without discarding an
    already-spent roll or rolling a second one.

    No `actor_id`: unlike every other mechanic in this module, `damage` is
    anchored on the *target* it wounds, not on whoever struck it (that
    creature already spent its turn's action on `attack`, and `damage`
    is not an acting mechanic in its own right). `run`
    is therefore resolved the same way `use_exit` resolves its own: load
    `target_id` with no run filter first (`GameObjectNotFoundError` if
    unknown, before any refusal can be recorded, ← D12), then gate the run
    it belongs to (`_require_ready_or_active_run`).

    `hit_id` is then consumed through `_consume_hit`, which alone decides
    whether it is a landed `attack` of this run and this turn, recorded
    against this same `target_id`, not already spent -- `HitNotUsableError`
    / `HIT_NOT_USABLE` on any failure, recorded and committed before
    re-raising (← D11). Only once the hit itself is usable is `roll_id`
    consumed at `kind="damage"` (`RollNotUsableError` / `ROLL_NOT_USABLE`
    on a wrong kind, another turn, or one already spent, recorded and
    committed the same way).

    The hit points applied are `min(total, current_hp)` -- never more than
    the target had left. At 0: a creature with no member (`member_id is
    None`) becomes `is_alive = False`; a character (`member_id` set) stays
    alive and its `state` is reassigned **whole** from `CharacterState`
    with `down=True` -- plain JSONB tracks no in-place key set, so the
    column must be written entire, never mutated. `tool_call` `ok`: `args
    {targetId, rollId, hitId}`, `roll_ids [roll_id]`, `outcome {rolled,
    applied, currentHp, isAlive, down}` -- `down` is always present,
    `False` for anything that is not a character.

    Sprint 010/04, I2: also appends `hp_changed` at `player` visibility,
    before the `dm`-only `tool_call` -- `before`/`after` bracket the hit
    points actually applied, alongside `maxHp` and the same `alive`/`down`
    flags the `tool_call` itself records. Only reached past both refusals
    above, which stay unchanged.
    """
    target = await _get_game_object(db, target_id)
    run = await _require_ready_or_active_run(db, run_id=target.campaign_run_id, user_id=user_id)

    try:
        await _consume_hit(db, run_id=run.id, hit_id=hit_id, target_id=target_id, turn_id=turn_id)
    except HitNotUsableError:
        await _refuse_damage(
            db,
            run_id=run.id,
            target_id=target_id,
            roll_id=roll_id,
            hit_id=hit_id,
            turn_id=turn_id,
            reason="hit is not a landed attack of this run and turn, or was already damaged",
        )
        raise

    try:
        consumed = await _consume_roll(
            db, run_id=run.id, roll_id=roll_id, kind="damage", turn_id=turn_id
        )
    except RollNotUsableError:
        await _refuse_damage(
            db,
            run_id=run.id,
            target_id=target_id,
            roll_id=roll_id,
            hit_id=hit_id,
            turn_id=turn_id,
            reason="roll already spent, from another turn, or of another kind",
        )
        raise

    total = consumed.payload["total"]
    if critical:
        total = 2 * sum(consumed.payload["faces"]) + consumed.payload["modifier"]
    before_hp = target.current_hp
    applied = min(total, target.current_hp)
    target.current_hp -= applied

    if target.current_hp == 0:
        if target.member_id is None:
            target.is_alive = False
        else:
            new_state = CharacterState.model_validate(target.state).model_copy(
                update={"down": True}
            )
            target.state = new_state.model_dump()

    # Not `is_down(target)`: this `down` means "a character stayed alive but
    # hit zero", the narrower fact `DamageResult`/`hp_changed`/`tool_call`
    # have always reported -- `False` for a dead, memberless creature, which
    # `is_down` (the broader read-side eligibility rule, sprint 011/02, WI3)
    # would instead call down. Both already agree on the one case that
    # matters for a mutation: a downed member's own `state.down`.
    down = target.member_id is not None and bool(target.state.get("down", False))

    await append_event(
        db,
        run_id=run.id,
        type="hp_changed",
        visibility="player",
        turn_id=turn_id,
        payload={
            "target_id": target_id,
            "target_name": target.name,
            "before": before_hp,
            "after": target.current_hp,
            "max_hp": target.max_hp,
            "alive": target.is_alive,
            "down": down,
        },
    )
    await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": "damage",
            "args": {"targetId": target_id, "rollId": roll_id, "hitId": hit_id},
            "roll_ids": [roll_id],
            "result": "ok",
            "outcome": {
                "rolled": total,
                "applied": applied,
                "currentHp": target.current_hp,
                "isAlive": target.is_alive,
                "down": down,
            },
        },
    )
    await db.commit()
    return DamageResult(
        applied=applied,
        current_hp=target.current_hp,
        max_hp=target.max_hp,
        is_alive=target.is_alive,
        down=down,
    )


async def append_event(
    db: AsyncSession,
    *,
    run_id: str,
    type: str,
    visibility: str,
    payload: BaseModel | dict[str, Any],
    turn_id: str | None = None,
    actor_member_id: str | None = None,
    usage: Usage | None = None,
) -> Event:
    """The only writer of `events` (AC1) -- every other module reaches the
    transcript through this function, never through `Event(...)` directly
    (guarded by `tests/playthrough/test_only_event_writer.py`).

    `payload` is validated against `EVENT_PAYLOADS[type]` (`schemas.py`):
    either a dict (its own field names or their camelCase aliases, both
    accepted -- `CamelModel.populate_by_name`) or already an instance of
    that exact model. An unknown `type`, an unknown `visibility`, or a
    payload that fails its model raises `InvalidEventPayloadError` --
    nothing is added or flushed first, so a refused call leaves no partial
    row. `usage.cost_usd` (`float | None`) is converted via `Decimal(str(...))`,
    never `Decimal(float)`, so the stored value is exact.

    `add` + `flush` only -- the id exists on return, but there is **no
    commit**: the caller owns the transaction, the way every mechanic in
    later sprints will use this alongside its own state changes. Performs
    **no membership check** of its own: every caller is already gated
    (`_require_member` or equivalent) before it reaches here, and this
    function must not add a second, redundant gate.

    `narration` (AC2-AC4): a non-blank `text` is embedded through the core
    `embed_texts()` seam (`llm_service.embed_texts`, off the event loop via
    `asyncio.to_thread` -- the seam is synchronous and its retry sleeps
    real time) before the row is built. On a right-width success, the
    vector and `get_settings().embedding_model` are stored and the
    embedding's own `usage` is added on top of the caller's `prompt_tokens`
    /`cost_usd` (each summed only where present; `completion_tokens` stays
    the caller's alone). Any exception from the seam, or a vector of the
    wrong width, leaves both columns `NULL`, logs one `warning` and never
    raises -- a lost embedding must never lose the narration itself (D4).
    Every other event type takes none of this: no call, no columns set.
    """
    model_cls = EVENT_PAYLOADS.get(type)
    if model_cls is None:
        raise InvalidEventPayloadError(f"unknown event type: {type}")
    if visibility not in _EVENT_VISIBILITIES:
        raise InvalidEventPayloadError(f"unknown event visibility: {visibility}")

    if isinstance(payload, model_cls):
        validated = payload
    elif isinstance(payload, dict):
        try:
            validated = model_cls.model_validate(payload)
        except ValidationError as exc:
            raise InvalidEventPayloadError(
                f"invalid payload for event type '{type}': {exc}"
            ) from exc
    else:
        raise InvalidEventPayloadError(
            f"payload for event type '{type}' must be a dict or {model_cls.__name__}, "
            f"got {payload.__class__.__name__}"
        )

    embedding_vector: list[float] | None = None
    embedding_model: str | None = None
    embedding_usage: Usage | None = None
    if type == "narration" and validated.text.strip():
        try:
            result = await asyncio.to_thread(llm_service.embed_texts, [validated.text])
        except Exception as exc:  # noqa: BLE001 - AC4: never let this reach the caller
            logger.warning("narration_embedding_failed", run_id=run_id, error=str(exc))
        else:
            vector = result.vectors[0]
            if len(vector) == EMBEDDING_WIDTH:
                embedding_vector = vector
                embedding_model = get_settings().embedding_model
                embedding_usage = result.usage
            else:
                logger.warning(
                    "narration_embedding_failed",
                    run_id=run_id,
                    error=f"embedding width {len(vector)} != {EMBEDDING_WIDTH}",
                )

    event = Event(
        campaign_run_id=run_id,
        actor_member_id=actor_member_id,
        turn_id=turn_id,
        type=type,
        visibility=visibility,
        payload=validated.model_dump(by_alias=True),
        embedding=embedding_vector,
        embedding_model=embedding_model,
    )

    prompt_token_parts = [u.prompt_tokens for u in (usage, embedding_usage) if u is not None]
    if prompt_token_parts:
        event.prompt_tokens = sum(prompt_token_parts)
    if usage is not None:
        event.completion_tokens = usage.completion_tokens
    cost_parts = [
        Decimal(str(u.cost_usd))
        for u in (usage, embedding_usage)
        if u is not None and u.cost_usd is not None
    ]
    if cost_parts:
        event.cost_usd = sum(cost_parts)

    db.add(event)
    await db.flush()
    return event


async def record_rule_lookup(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    topic: str,
    turn_id: str | None = None,
) -> Event:
    """Records a matched rule lookup, visible to the player (sprint 010/04,
    I3). `topic` is the best match's own `heading_path`, supplied by the
    `lookup_rule` tool only when its search matched something -- the
    module's ordinary mechanic shape: `_require_member`, append, commit.
    No refusal path: a lookup that matched nothing never calls this at
    all (AC3), so there is nothing here to refuse.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    event = await append_event(
        db,
        run_id=run_id,
        type="rule_looked_up",
        visibility="player",
        turn_id=turn_id,
        payload={"topic": topic},
    )
    await db.commit()
    return event


async def record_player_action(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    text: str,
    turn_id: str,
    answers_question_id: str | None = None,
) -> Event:
    """Records the player's own free-text turn -- a submitted action, or an
    answer to an in-turn question when `answers_question_id` is given
    (sprint 011/03, WI3). This is the module's own `player_action` write;
    the game module used to write this row itself and no longer may.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    event = await append_event(
        db,
        run_id=run_id,
        type="player_action",
        visibility="player",
        turn_id=turn_id,
        payload={"text": text, "answersQuestionId": answers_question_id},
    )
    await db.commit()
    return event


async def record_answer(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    text: str,
    question_id: str,
    turn_id: str,
) -> Event:
    """Records the player's answer to a pending `question` interrupt
    (sprint 011/03, WI3) -- the same `player_action` shape
    `record_player_action` writes, `answers_question_id` always given here
    since answering a question is exactly what this call is for.
    """
    return await record_player_action(
        db,
        user_id=user_id,
        run_id=run_id,
        text=text,
        turn_id=turn_id,
        answers_question_id=question_id,
    )


async def record_narration(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    text: str,
    turn_id: str,
    usage: Usage | None = None,
) -> Event:
    """Records the DM's own narration for the turn (sprint 011/03, WI3),
    then -- matching the game module's own former behaviour exactly --
    activates a `ready` run into `active` on its first narration, never on
    any later one (`activate_campaign_run` is itself a no-op once
    `active`).
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    event = await append_event(
        db,
        run_id=run_id,
        type="narration",
        visibility="player",
        turn_id=turn_id,
        payload={"text": text},
        usage=usage,
    )
    await db.commit()

    run = await get_campaign_run(db, user_id=user_id, run_id=run_id)
    if run.status == "ready":
        await activate_campaign_run(db, user_id=user_id, run_id=run_id)

    return event


async def record_outcome(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    name: str,
    args: dict[str, Any],
    outcome: dict[str, Any],
    turn_id: str | None = None,
    roll_ids: Sequence[str] = (),
) -> Event:
    """Records one mechanic invocation as a `dm`-visible `tool_call`
    (sprint 011/03, WI3) -- the same shape every mechanic in this module
    already writes for itself. `result` is derived from `outcome`, not a
    separate argument: an `outcome` carrying a `"reason"` key is the
    module's own refusal convention (e.g. `set_hostility`'s non-creature
    actor), everything else is `"ok"`.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    result = "refused" if "reason" in outcome else "ok"
    event = await append_event(
        db,
        run_id=run_id,
        type="tool_call",
        visibility="dm",
        turn_id=turn_id,
        payload={
            "name": name,
            "args": args,
            "roll_ids": list(roll_ids),
            "result": result,
            "outcome": outcome,
        },
    )
    await db.commit()
    return event


async def list_events(
    db: AsyncSession,
    *,
    user_id: str,
    run_id: str,
    after: str | None = None,
    limit: int = 200,
) -> list[Event]:
    """The caller's `player`-visible transcript for `run_id`, oldest first.

    `_require_member` first, exactly like every other function that takes a
    `run_id` -- a foreign or unknown run raises `CampaignRunNotFoundError`
    before anything else runs. Ordered by `id` alone (safe today because one
    process mints every id -- README.md, `docs/modules/playthrough.md`
    §9); `after`, when given, is exclusive. `dm`-visible rows are filtered
    out of the query itself, not merely absent from what the caller renders.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)

    stmt = (
        select(Event)
        .where(Event.campaign_run_id == run_id, Event.visibility == "player")
        .order_by(Event.id)
        .limit(limit)
    )
    if after is not None:
        stmt = stmt.where(Event.id > after)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_latest_event_id(db: AsyncSession, *, run_id: str) -> str | None:
    """The newest event id for `run_id`, or None if no events exist yet."""
    await _get_run(db, run_id)
    stmt = (
        select(Event.id).where(Event.campaign_run_id == run_id).order_by(Event.id.desc()).limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_all_events(
    db: AsyncSession,
    *,
    run_id: str,
    after_id: str | None = None,
    limit: int | None = None,
) -> list[Event]:
    """Every event for `run_id` (both player- and dm-visible), oldest first."""
    await _get_run(db, run_id)
    stmt = select(Event).where(Event.campaign_run_id == run_id).order_by(Event.id)
    if after_id is not None:
        stmt = stmt.where(Event.id > after_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_awaiting(db: AsyncSession, *, user_id: str, run_id: str) -> str:
    """What the game is waiting for right now, if anything (WI2, AC4b) --
    `"none"`, a roll the player has been asked for and has not answered
    (`"roll:<requestId>"`), or a question put to the player and not yet
    answered (`"answer:<questionId>"`). Derived fresh from the transcript
    every time this is called -- no stored cursor (← D9) -- so it can
    never fall out of step with `events` itself.

    `_require_member` first, exactly like every other function that takes
    a `run_id`: a foreign or unknown run raises `CampaignRunNotFoundError`
    before anything else runs. The "open turn" is whichever `turn_id` the
    most recently written event for `run_id` carries (`None` is a turn of
    its own, exactly as `_consume_roll` treats it); only that turn's own
    events are then read back, oldest first: the newest `roll_requested`
    with no `roll` naming it in `requestId` yet **and whose own actor is
    one of the party's own characters** -- else the newest `question` with
    no `player_action` written after it, else `"none"`.

    The actor check (sprint 010/11 round 4, Fault A -- ← finding) exists
    because `roll`/`roll_dice` write `roll_requested` and its own `roll`
    as two separate rows, not one -- a session-level race (Fault A's own
    concurrency fix aside, an old row written before that fix, or any
    other way the pair falls out of sync) can leave a *monster's* attack
    roll dangling with no matching `roll`. `awaiting` is read by the
    player's own turn route and rendered as a roll button; a monster has
    no player to press it, so a dangling monster roll must never surface
    here -- it is skipped, not returned, and `get_awaiting` falls through
    to the next candidate exactly as if that row did not exist.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)

    stmt = select(Event).where(Event.campaign_run_id == run_id).order_by(Event.id)
    result = await db.execute(stmt)
    all_events = list(result.scalars().all())
    if not all_events:
        return "none"

    open_turn_id = all_events[-1].turn_id
    events = [event for event in all_events if event.turn_id == open_turn_id]

    answered_request_ids = {
        event.payload.get("requestId")
        for event in events
        if event.type == "roll" and event.payload.get("requestId") is not None
    }
    unanswered_requests = [
        event
        for event in events
        if event.type == "roll_requested" and event.id not in answered_request_ids
    ]
    if unanswered_requests:
        actor_ids = {
            RollRequestedPayload.model_validate(event.payload).actor_id
            for event in unanswered_requests
        }
        actors_result = await db.execute(
            select(GameObject.id, GameObject.member_id).where(GameObject.id.in_(actor_ids))
        )
        member_id_by_actor = dict(actors_result.all())
        for event in reversed(unanswered_requests):
            actor_id = RollRequestedPayload.model_validate(event.payload).actor_id
            if member_id_by_actor.get(actor_id) is not None:
                return f"roll:{event.id}"

    question_events = [event for event in events if event.type == "question"]
    if question_events:
        newest_question = question_events[-1]
        answered_after = any(
            event.type == "player_action" and event.id > newest_question.id for event in events
        )
        if not answered_after:
            return f"answer:{newest_question.id}"

    return "none"


async def open_turn_id(db: AsyncSession, *, user_id: str, run_id: str) -> str | None:
    """The id of `run_id`'s open turn -- whichever `turn_id` the newest
    event for this run carries, `None` when the run has no event yet or
    the newest one carries no turn at all (sprint 010/03, I3). The same
    "open turn" `get_awaiting` reads back from (its own newest event's
    `turn_id`); this is that id alone, with no read of the events it
    contains.

    `_require_member` first, exactly like every other function that takes
    a `run_id`: a foreign or unknown run raises `CampaignRunNotFoundError`
    before anything else runs.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)

    stmt = (
        select(Event.turn_id)
        .where(Event.campaign_run_id == run_id)
        .order_by(Event.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def run_cost(db: AsyncSession, *, user_id: str, run_id: str) -> RunCost:
    """What `run_id` has cost, whole and by turn (WI1, AC3) -- for its
    owner alone, exact to the last digit, and reachable only as
    `app playthrough cost` (never a route, ← D14).

    `_require_member` first, exactly like every other function that takes
    a `run_id`: a foreign or unknown run raises `CampaignRunNotFoundError`
    before the sum ever runs. Grouped by `turn_id`, the `NULL` turn (events
    written with no turn) sorted last -- `turn_id.is_(None)` orders `False`
    (a real turn) before `True` (no turn), so `ORDER BY` alone puts it
    there without a second pass in Python. `SUM(cost_usd)` over a group
    whose events all carry no cost is SQL `NULL`, not `0`; that, and a run
    with no events at all (no groups, so no rows), both normalise to the
    exact `Decimal("0.000000")` here rather than leaking `None` into the
    result. `total` is the sum of every turn's total, including the
    untagged one -- never a second query against `events`.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)

    stmt = (
        select(Event.turn_id, func.sum(Event.cost_usd))
        .where(Event.campaign_run_id == run_id)
        .group_by(Event.turn_id)
        .order_by(Event.turn_id.is_(None), Event.turn_id)
    )
    result = await db.execute(stmt)

    turns = [
        TurnCost(turn_id=turn_id, total=total if total is not None else _ZERO_COST)
        for turn_id, total in result.all()
    ]
    total = sum((turn.total for turn in turns), _ZERO_COST)
    return RunCost(total=total, turns=turns)


async def latest_event_id(db: AsyncSession, *, user_id: str, run_id: str) -> str | None:
    """The id of the most recently written event for `run_id`, or `None`
    when it has none yet -- the whole of the SSE stream's per-tick signal
    (AC4, WI2). Ids sort in write order (research.md "Id ordering"), so
    `max(id)` alone tells the stream route whether anything is new; the
    signal carries no content (← D10) -- a changed id means the caller
    refetches the transcript through `list_events`, never a second way of
    reading it.

    `_require_member` first, exactly like every other function that takes a
    `run_id`: a foreign or unknown run raises `CampaignRunNotFoundError`
    before the query runs. This doubles as the route's membership gate,
    checked once before the stream opens and again on every poll.

    Rolls back on the way out of a successful call: this function is
    polled for as long as the stream stays open (up to
    `sse_max_lifetime_seconds`), and a read-only transaction left open
    between polls would pin a connection idle for that whole span.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)

    stmt = select(func.max(Event.id)).where(Event.campaign_run_id == run_id)
    result = await db.execute(stmt)
    current_id = result.scalar_one_or_none()
    await db.rollback()
    return current_id


async def recap(db: AsyncSession, *, run_id: str, n: int = 5) -> list[NarrationRead]:
    """The run's `n` most recent `narration` events, oldest first -- no
    question asked (AC2, sprint 006/02 WI2).

    An operator read, gated on the run's existence alone (`_get_run`
    first, no `user_id`, no membership check) -- unlike every function
    above. Picks the newest `n` in SQL (`ORDER BY id DESC LIMIT n`, ids
    sort in write order the same way `latest_event_id` relies on) and
    flips them to chronological order in Python, so the newest `n` is
    always the set returned even when the run has more narration than
    `n`. No `embedding IS NOT NULL` filter: recency does not care whether
    a line was encoded, and this makes no embedding call at all. A run
    with no narration returns `[]`. Neither commits nor rolls back.
    """
    await _get_run(db, run_id)

    stmt = (
        select(Event.id, Event.created_at, Event.payload)
        .where(Event.campaign_run_id == run_id, Event.type == "narration")
        .order_by(Event.id.desc())
        .limit(n)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        NarrationRead(id=event_id, created_at=created_at, text=payload.get("text", ""))
        for event_id, created_at, payload in reversed(rows)
    ]


async def recall(db: AsyncSession, *, run_id: str, query: str, k: int = 5) -> list[NarrationRead]:
    """The `k` narration events from anywhere in the run whose meaning is
    closest to `query`, closest first -- an answer to a question asked of
    the whole campaign run, never scoped to whichever adventure is
    current (AC1, sprint 006/02 WI1).

    An operator read, gated on the run's existence alone (`_get_run`
    first, no `user_id`, no membership check), exactly like `recap`.

    Embeds `query` exactly once through the core `embed_texts()` seam,
    off the event loop the same way `append_event`'s own narration
    encoding is (`asyncio.to_thread`, `llm_service.embed_texts` as a
    module attribute, never a name import -- AGENTS.md). Any exception
    from the seam propagates unchanged: unlike a write, where a lost
    embedding must never lose the narration itself (D4), an operator read
    that silently answered "no memories" while the encoder is down would
    be worse than surfacing the failure.

    Orders `narration` events by cosine distance to the query vector
    (`Event.embedding.cosine_distance`, the `<=>` operator the
    `ix_events_embedding_narration` partial index serves) and returns the
    closest `k`. The `where` predicates match that index's own
    (`type = 'narration' AND embedding IS NOT NULL`) verbatim, so a row
    that failed to be encoded is never a candidate. No relevance floor:
    the closest `k` come back regardless of how distant they are.
    `Event` itself is never selected -- only `id`, `created_at` and
    `payload` cross out of SQL, so no 1536-float vector ever crosses the
    wire. A run with no narration returns `[]`. Neither commits nor rolls
    back.
    """
    await _get_run(db, run_id)

    result = await asyncio.to_thread(llm_service.embed_texts, [query])
    vector = result.vectors[0]

    stmt = (
        select(Event.id, Event.created_at, Event.payload)
        .where(
            Event.campaign_run_id == run_id,
            Event.type == "narration",
            Event.embedding.is_not(None),
        )
        .order_by(Event.embedding.cosine_distance(vector))
        .limit(k)
    )
    result_rows = await db.execute(stmt)
    rows = result_rows.all()

    return [
        NarrationRead(id=event_id, created_at=created_at, text=payload.get("text", ""))
        for event_id, created_at, payload in rows
    ]


async def recall_history(
    db: AsyncSession, *, user_id: str, run_id: str, query: str, limit: int = 3
) -> list[situation_types.RecalledTurn]:
    """Semantic narration matches, each expanded to the turn it belongs to
    (sprint 011/04, WI2, I2, intent §2.4).

    Membership-gated, unlike `recall` itself (`_require_member` first --
    every run-scoped read opens with it, ← research). Anchors come from
    `recall` unchanged, closest first, so this function's own ordering
    follows the anchors' rank rather than re-deriving it. `recall` itself
    returns `NarrationRead` (`id, createdAt, text`) with no `turn_id`, so
    one extra query reads each anchor's own `turn_id` back by id before
    any turn can be expanded.

    One extra query per *distinct* `turn_id` among the anchors -- never
    once per anchor -- selecting every `visibility='player'` event of that
    turn, ordered by `id` (the same visibility filter and ordering
    `list_events` applies to a whole transcript). An anchor whose own
    event has no `turn_id` never joins a shared query: it yields a
    `RecalledTurn` holding only its own narration row, since there is no
    turn to expand into.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)

    anchors = await recall(db, run_id=run_id, query=query, k=limit)
    if not anchors:
        return []

    anchor_ids = [anchor.id for anchor in anchors]
    turn_by_anchor_id = dict(
        (await db.execute(select(Event.id, Event.turn_id).where(Event.id.in_(anchor_ids)))).all()
    )

    turn_ids = sorted({turn_id for turn_id in turn_by_anchor_id.values() if turn_id is not None})
    events_by_turn: dict[str, list[situation_types.RecentEvent]] = {}
    if turn_ids:
        stmt = (
            select(Event.id, Event.turn_id, Event.type, Event.payload, Event.created_at)
            .where(
                Event.campaign_run_id == run_id,
                Event.turn_id.in_(turn_ids),
                Event.visibility == "player",
            )
            .order_by(Event.id)
        )
        result = await db.execute(stmt)
        for event_id, turn_id, event_type, payload, created_at in result.all():
            events_by_turn.setdefault(turn_id, []).append(
                situation_types.RecentEvent(
                    id=event_id,
                    turn_id=turn_id,
                    type=event_type,
                    payload=payload,
                    created_at=created_at,
                )
            )

    recalled_turns = []
    for anchor in anchors:
        anchor_turn_id = turn_by_anchor_id.get(anchor.id)
        if anchor_turn_id is None:
            events = (
                situation_types.RecentEvent(
                    id=anchor.id,
                    turn_id=None,
                    type="narration",
                    payload={"text": anchor.text},
                    created_at=anchor.created_at,
                ),
            )
        else:
            events = tuple(events_by_turn.get(anchor_turn_id, ()))
        recalled_turns.append(
            situation_types.RecalledTurn(
                turn_id=anchor_turn_id, anchor_event_id=anchor.id, events=events
            )
        )
    return recalled_turns
