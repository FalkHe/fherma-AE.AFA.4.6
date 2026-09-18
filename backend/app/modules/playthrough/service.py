"""Starting, listing and reading a campaign run.

Imported as a module (`from app.modules.playthrough import service`) and
called `service.f(...)` -- never import the functions by name, the test
suite's monkeypatching depends on it (AGENTS.md).
"""

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SAWarning
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import ID_LENGTH, generate_id
from app.modules.content import service as content_service
from app.modules.content.errors import ContentNotFoundError
from app.modules.content.schemas import LoadedCampaign, ObjectTemplate
from app.modules.playthrough.errors import (
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject


def _campaign_run_id(*, user_id: str, campaign_id: str) -> str:
    """The run's own id, deterministic rather than random.

    A user starting the same campaign a second time reuses the identical
    id, so the second attempt's rows collide with the first's on the
    `(campaign_run_id, instance_key)` unique constraint (and on the run's
    own primary key) -- the repeat is refused by that key alone, with no
    pre-check needed (I5).
    """
    digest = hashlib.sha256(f"{user_id}:{campaign_id}".encode()).hexdigest()
    return digest[:ID_LENGTH]


def _build_object(
    *,
    campaign_run_id: str,
    template: ObjectTemplate,
    instance_key: str,
    source_adventure_id: str,
    source_scene_id: str,
) -> GameObject:
    """One `objects` row for a placed or carried instance of `template`.

    Position (`adventure_run_id`, `scene_id`) and `member_id` all stay
    NULL -- nothing is positioned at start (← D3). The id is generated here
    rather than left to the column default, because a placement's carried
    children need it (`owner_object_id`) before the placement row has gone
    through a flush.
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

    run = CampaignRun(
        id=_campaign_run_id(user_id=user_id, campaign_id=campaign_id),
        campaign_id=campaign_id,
        content_version=content_version,
    )

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
    except (IntegrityError, SAWarning) as exc:
        # `IntegrityError` is the constraint itself; `SAWarning` is what a
        # *session already holding* the deterministic id raises the moment
        # `db.add(run)` sees a second, distinct object claim it (identity
        # map conflict, promoted to an exception by the suite's
        # `filterwarnings = ["error"]`) -- a session reused across two
        # starts hits this before either statement reaches Postgres, but
        # the meaning is the same repeat start, so it is translated the
        # same way.
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


async def get_campaign_run(db: AsyncSession, *, user_id: str, run_id: str) -> CampaignRun:
    """One run, gated by membership -- a foreign or unknown id both raise
    `CampaignRunNotFoundError` out of `_require_member`.
    """
    await _require_member(db, run_id=run_id, user_id=user_id)
    result = await db.execute(select(CampaignRun).where(CampaignRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise CampaignRunNotFoundError(run_id)
    return run
