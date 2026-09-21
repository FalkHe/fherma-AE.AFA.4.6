"""Starting, listing and reading a campaign run; giving it its character;
renaming and archiving it; appending to its transcript.

Imported as a module (`from app.modules.playthrough import service`) and
called `service.f(...)` -- never import the functions by name, the test
suite's monkeypatching depends on it (AGENTS.md).
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.core.llm.service import Usage
from app.modules.content import service as content_service
from app.modules.content.errors import ContentNotFoundError
from app.modules.content.schemas import LoadedCampaign, ObjectTemplate, SeedCharacter
from app.modules.playthrough import dice
from app.modules.playthrough.errors import (
    AdventureActiveError,
    AdventureExhaustedError,
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    CharacterExistsError,
    ExitNotAvailableError,
    GameObjectNotFoundError,
    InvalidDcError,
    InvalidEventPayloadError,
    InvalidRunStatusError,
    RollNotFoundError,
    RollNotUsableError,
    RollRequestNotFoundError,
    RunArchivedError,
)
from app.modules.playthrough.models import (
    AdventureRun,
    CampaignRun,
    CampaignRunMember,
    Event,
    GameObject,
)
from app.modules.playthrough.schemas import (
    EVENT_PAYLOADS,
    CharacterState,
    RollKind,
    RollRequestedPayload,
    RunCost,
    TurnCost,
)

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
    run's id, then one commit.
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

    await db.commit()
    await db.refresh(adventure_run)
    return adventure_run


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
    for)."""
    formula = dice.derive_formula(
        kind, actor, context, campaign_id=run.campaign_id, version=run.content_version
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
    (WI2, AC2)."""
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    event = await _append_roll_requested(
        db, run=run, actor=actor, kind=kind, context=context, visibility="player", turn_id=turn_id
    )
    await db.commit()
    await db.refresh(event)
    return event


async def resolve_roll_request(
    db: AsyncSession, *, user_id: str, request_id: str, turn_id: str | None = None
) -> Event:
    """Answers the `roll_requested` event named `request_id` with a `roll`,
    re-using its stored `formula`, `kind`, `actor_id` and `visibility`
    verbatim (WI2, AC2)."""
    request_event = await _get_roll_request_event(db, request_id)
    run = await _require_ready_or_active_run(
        db, run_id=request_event.campaign_run_id, user_id=user_id
    )
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


async def passive_check(
    db: AsyncSession,
    *,
    user_id: str,
    actor_id: str,
    ability: str,
    dc: int,
    turn_id: str | None = None,
) -> bool:
    """A passive score -- `10` plus the named ability's modifier, no die
    rolled at all -- against `dc`. Recorded as a `tool_call` at `dm`, never
    a `roll`: it has no faces and must never be consumable by a later
    sprint's check consumer (WI2, AC2)."""
    actor, run = await _resolve_actor_and_run(db, actor_id=actor_id, user_id=user_id)
    abilities = dice._actor_abilities(
        actor, campaign_id=run.campaign_id, version=run.content_version
    )
    modifier = dice._ability_modifier(getattr(abilities, ability))
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
            "args": {"actorId": actor_id, "ability": ability, "dc": dc},
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
    anywhere between here and the caller would erase the record along with
    the raised exception. The caller raises `ExitNotAvailableError` right
    after this returns.
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


async def use_exit(db: AsyncSession, *, user_id: str, actor_id: str, exit_id: str) -> None:
    """Moves `actor_id` through `exit_id`, or -- on an `adventure_end`
    exit -- completes its adventure and, when that adventure is the pinned
    campaign's last, finishes the whole game (WI1, AC2/AC3). No `turn_id`
    parameter: phase 8 adds one once a turn exists.

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
    records and commits the refusal, then this function raises
    `ExitNotAvailableError`.

    `kind='scene'` rewrites the actor's `scene_id` to `exit.to`
    (`adventure_run_id` untouched -- an exit only ever changes where within
    an adventure someone stands) and appends `scene_entered` at `player`.
    `kind='adventure_end'` completes the actor's adventure run -- `status`
    and `completed_at` set together on the one loaded row, so they reach
    the database in the same UPDATE and never violate the CHECK that ties
    them -- and appends `adventure_completed` at `player`; when that
    adventure is the last id the pinned campaign declares (read from the
    pinned content, never the `adventure_runs` table), the campaign run
    itself becomes `finished`. No position is touched either way: nobody is
    moved or cleared away when an adventure ends. Either outcome then also
    appends a successful `tool_call` at `dm` (← D11; unlike `enter_adventure`,
    which is a route rather than a tool) before the one commit that closes
    the call.
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
        raise ExitNotAvailableError(actor_id, exit_id)

    if exit_.kind == "scene":
        obj.scene_id = exit_.to
        await append_event(
            db,
            run_id=run.id,
            type="scene_entered",
            visibility="player",
            payload={"adventure_run_id": obj.adventure_run_id, "scene_id": obj.scene_id},
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
            payload={"adventure_run_id": adventure_run.id},
        )

        loaded = content_service.load_campaign(run.campaign_id, run.content_version)
        if adventure_run.adventure_id == loaded.campaign.adventures[-1]:
            run.status = "finished"

    await append_event(
        db,
        run_id=run.id,
        type="tool_call",
        visibility="dm",
        payload={
            "name": "use_exit",
            "args": {"actorId": actor_id, "exitId": exit_id},
            "roll_ids": [],
            "result": "ok",
            "outcome": {},
        },
    )
    await db.commit()


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

    event = Event(
        campaign_run_id=run_id,
        actor_member_id=actor_member_id,
        turn_id=turn_id,
        type=type,
        visibility=visibility,
        payload=validated.model_dump(by_alias=True),
    )
    if usage is not None:
        event.prompt_tokens = usage.prompt_tokens
        event.completion_tokens = usage.completion_tokens
        if usage.cost_usd is not None:
            event.cost_usd = Decimal(str(usage.cost_usd))

    db.add(event)
    await db.flush()
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
