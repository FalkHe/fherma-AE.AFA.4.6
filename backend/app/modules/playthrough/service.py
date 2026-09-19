"""Starting, listing and reading a campaign run; giving it its character;
renaming and archiving it.

Imported as a module (`from app.modules.playthrough import service`) and
called `service.f(...)` -- never import the functions by name, the test
suite's monkeypatching depends on it (AGENTS.md).
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.content.errors import ContentNotFoundError
from app.modules.content.schemas import LoadedCampaign, ObjectTemplate, SeedCharacter
from app.modules.playthrough.errors import (
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    CharacterExistsError,
    InvalidRunStatusError,
    RunArchivedError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject
from app.modules.playthrough.schemas import CharacterState


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


async def _get_run(db: AsyncSession, run_id: str) -> CampaignRun:
    """The run row itself, once membership is already confirmed -- an
    unknown id (only reachable if the run was deleted between the
    membership check and here) raises `CampaignRunNotFoundError` too.
    """
    result = await db.execute(select(CampaignRun).where(CampaignRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise CampaignRunNotFoundError(run_id)
    return run


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


async def create_character(
    db: AsyncSession, *, user_id: str, run_id: str, sheet: SeedCharacter | None = None
) -> GameObject:
    """The run's one player character, built from `sheet` -- or, when
    `sheet` is `None`, from the seed character the run's pinned campaign
    declares (← D4; phase 7 will pass a sheet of its own without changing
    this signature).

    Refuses a second character on this run (`CharacterExistsError`, a
    Stage-01 game rule, not a schema constraint -- ← 003-D13) and refuses
    an archived run (`RunArchivedError`). Builds the creature, flushes,
    builds one carried `item` row per inventory entry through the
    template-driven `_build_object`, flushes, moves the run to `ready`,
    and commits once. Appends no event. Catches nothing else: any other
    failure (a stat outside its check constraint, a bad foreign key) is a
    bug, not a domain error, and travels to the 500 envelope.
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
        state=CharacterState(
            abilities=sheet.abilities,
            race=sheet.race,
            character_class=sheet.character_class,
            background=sheet.background,
            appearance=sheet.appearance,
        ).model_dump(),
    )
    db.add(character)
    await db.flush()

    # `n` counts repeats of the same template within the pack -- greenhollow's
    # five entries are distinct, so every carried key here ends `:1`.
    ordinals: dict[str, int] = {}
    carried_rows: list[GameObject] = []
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
