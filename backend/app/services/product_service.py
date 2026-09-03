"""Catalogue entries: creation, the status workflow and specification writes.

This module owns its transactions and speaks no HTTP: callers translate the
exceptions raised here into status codes or exit codes.

Two rules are enforced here and nowhere else:

* the **legal transition matrices** — every status change goes through
  `transition` (catalogue rows) or `transition_image` (moderation of a
  downloaded picture), so an illegal one is impossible regardless of caller;
* **`verified` specifications are only ever promotions of a draft.** Approval
  copies the draft row and flips pending images in the same transaction, so a
  model can never be publicly visible with a half-applied review.

`start_ingestion` is the third rule: starting an ingestion is a status change,
an operation row and a queued task — in that order, each committed before the
next — so no caller can enqueue a job the admin UI cannot yet see.

Every public write here also publishes the pinned `product.updated` event
through `operation_service.notify` — **after** its commit, per the ordering rule
documented there. That event is what flips a backlog chip in a browser without
a reload, so a new write path that changes a row must announce it too.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.motorbike_spec import SPEC_FIELDS, MotorbikeSpec, SpecKind
from app.db.models.operation import Operation
from app.services import identity_validation, operation_service

logger = logging.getLogger(__name__)

# `operations.type` of an ingestion run — the admin backlog reads its progress
# cells from these rows.
INGESTION_OPERATION_TYPE = "ingestion"

# Which status may follow which. Anything absent from this map is rejected —
# including a no-op change to the current status.
LEGAL_TRANSITIONS: dict[MotorbikeStatus, frozenset[MotorbikeStatus]] = {
    # Admin add auto-starts ingestion; retry/start.
    MotorbikeStatus.BACKLOG: frozenset({MotorbikeStatus.INGESTING}),
    # Job success / job failure.
    MotorbikeStatus.INGESTING: frozenset({MotorbikeStatus.IN_REVIEW, MotorbikeStatus.BACKLOG}),
    MotorbikeStatus.IN_REVIEW: frozenset({MotorbikeStatus.APPROVED, MotorbikeStatus.REJECTED}),
    MotorbikeStatus.APPROVED: frozenset(),
    # `rejected` is not terminal: re-queueing means a fresh ingestion. The row
    # keeps its draft specification, documents and images either way.
    MotorbikeStatus.REJECTED: frozenset({MotorbikeStatus.INGESTING}),
}

# Which moderation state an image may move to. Approval of a whole model flips
# pending images through `_apply_approval`; an admin may also judge a single
# image, and rejection is final — a rejected picture is never shown again.
LEGAL_IMAGE_TRANSITIONS: dict[ImageStatus, frozenset[ImageStatus]] = {
    ImageStatus.PENDING: frozenset({ImageStatus.APPROVED, ImageStatus.REJECTED}),
    # Un-publishing an approved image stays possible.
    ImageStatus.APPROVED: frozenset({ImageStatus.REJECTED}),
    ImageStatus.REJECTED: frozenset(),
}

# A2 driving licence limits: at most 35 kW and at most 0.2 kW per kg.
A2_MAX_POWER_KW = Decimal("35")
A2_MAX_POWER_TO_WEIGHT = Decimal("0.2")

_NON_SLUG_CHARACTERS = re.compile(r"[^a-z0-9]+")


class DuplicateModelError(Exception):
    """Raised when a new catalogue entry collides with an existing slug."""


class InvalidTransitionError(Exception):
    """Raised when a requested status change is not in the transition matrix."""

    def __init__(self, current: MotorbikeStatus, requested: MotorbikeStatus) -> None:
        super().__init__(f"Cannot change status from '{current.value}' to '{requested.value}'.")
        self.current = current
        self.requested = requested


class InvalidImageTransitionError(Exception):
    """Raised when a requested image moderation change is not legal."""

    def __init__(self, current: ImageStatus, requested: ImageStatus) -> None:
        super().__init__(
            f"Cannot change image status from '{current.value}' to '{requested.value}'."
        )
        self.current = current
        self.requested = requested


class IncompleteIdentityError(Exception):
    """Raised when `approved` is requested on a row with no complete identity (D4).

    Carries the missing field names in its message, e.g. `"manufacturer_id,
    year_from"`.
    """

    def __init__(self, missing_fields: Sequence[str]) -> None:
        super().__init__(
            "Cannot approve: identity is incomplete, missing " + ", ".join(missing_fields) + "."
        )
        self.missing_fields = list(missing_fields)


def slugify(name: str) -> str:
    """Return the unique identity derived from a display name.

    Lowercase, every run of non-alphanumeric characters collapsed to a single
    hyphen, hyphens trimmed off both ends: `" Suzuki GSR 600 "` →
    `"suzuki-gsr-600"`.
    """
    return _NON_SLUG_CHARACTERS.sub("-", name.lower()).strip("-")


async def get_motorbike(session: AsyncSession, motorbike_id: str) -> Motorbike | None:
    """Return one catalogue entry, or `None` when the id is unknown."""
    result = await session.execute(select(Motorbike).where(Motorbike.id == motorbike_id))
    return result.scalar_one_or_none()


async def get_by_slug(session: AsyncSession, slug: str) -> Motorbike | None:
    """Return the catalogue entry with `slug`, or `None` when it is unknown."""
    result = await session.execute(select(Motorbike).where(Motorbike.slug == slug))
    return result.scalar_one_or_none()


async def normalise_buildingline(
    session: AsyncSession, manufacturer_id: str, name: str | None
) -> str | None:
    """Return the family name to store for `manufacturer_id`, or `None`.

    Trims and collapses inner whitespace; an empty result is `None`. The drift
    guard (§2.1): a case-insensitive match against `manufacturer_id`'s existing
    distinct `buildingline` values returns the value already on file, so the
    first writer's spelling wins and every later writer joins it — the same
    effect `get_or_create` has, without a row.

    Read-only: no write, no commit.
    """
    if name is None:
        return None
    collapsed = " ".join(name.split())
    if not collapsed:
        return None

    for existing in await list_buildinglines(session, manufacturer_id):
        if existing.casefold() == collapsed.casefold():
            return existing
    return collapsed


async def list_buildinglines(session: AsyncSession, manufacturer_id: str) -> list[str]:
    """Return `manufacturer_id`'s distinct non-NULL `buildingline` values, sorted.

    Backs the review form's `Autocomplete freeSolo` and
    `normalise_buildingline` itself. Read-only: no write, no commit.
    """
    result = await session.execute(
        select(Motorbike).where(
            Motorbike.manufacturer_id == manufacturer_id,
            Motorbike.buildingline.is_not(None),
        )
    )
    values = {motorbike.buildingline for motorbike in result.scalars().all()}
    return sorted(values)


async def list_motorbikes(
    session: AsyncSession,
    *,
    statuses: Sequence[MotorbikeStatus] | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Motorbike], int]:
    """Return one page of catalogue entries plus the unpaginated total.

    Newest first (`created_at` descending, id as tiebreaker so paging is stable
    for rows created in the same instant). `statuses` is the `filter[status]`
    set; `None` means unfiltered.
    """
    conditions = [] if not statuses else [Motorbike.status.in_(list(statuses))]

    total = await session.execute(select(func.count()).select_from(Motorbike).where(*conditions))
    page = await session.execute(
        select(Motorbike)
        .where(*conditions)
        .order_by(Motorbike.created_at.desc(), Motorbike.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(page.scalars().all()), total.scalar_one()


async def get_specs(
    session: AsyncSession, motorbike_ids: Sequence[str]
) -> dict[str, dict[SpecKind, MotorbikeSpec]]:
    """Return the specification rows of several motorbikes, grouped by id and kind.

    One query for a whole page of the catalogue: a motorbike without any
    specification is simply absent from the result.
    """
    if not motorbike_ids:
        return {}

    result = await session.execute(
        select(MotorbikeSpec).where(MotorbikeSpec.motorbike_id.in_(list(motorbike_ids)))
    )
    grouped: dict[str, dict[SpecKind, MotorbikeSpec]] = {}
    for spec in result.scalars().all():
        grouped.setdefault(spec.motorbike_id, {})[spec.kind] = spec
    return grouped


async def get_image(session: AsyncSession, image_id: str) -> MotorbikeImage | None:
    """Return one image row, or `None` when the id is unknown."""
    result = await session.execute(select(MotorbikeImage).where(MotorbikeImage.id == image_id))
    return result.scalar_one_or_none()


async def list_images(
    session: AsyncSession,
    *,
    motorbike_id: str | None = None,
    statuses: Sequence[ImageStatus] | None = None,
) -> list[MotorbikeImage]:
    """Return image rows, newest first; `motorbike_id` is the `filter[product]` set.

    Unpaginated on purpose: ingestion stores at most one image per run, so the
    result is a handful of rows per model and the review screen renders the
    newest one.

    `statuses` restricts the moderation states, the way `list_motorbikes` does
    for catalogue statuses: `None` (the default) means unfiltered — the admin
    review screen has to see pending pictures — while a customer-facing gallery
    passes `[ImageStatus.APPROVED]`, so an unreviewed picture cannot be shown by
    forgetting a filter downstream.
    """
    conditions = [] if motorbike_id is None else [MotorbikeImage.motorbike_id == motorbike_id]
    if statuses:
        conditions.append(MotorbikeImage.status.in_(list(statuses)))

    result = await session.execute(
        select(MotorbikeImage)
        .where(*conditions)
        .order_by(MotorbikeImage.created_at.desc(), MotorbikeImage.id.desc())
    )
    return list(result.scalars().all())


async def newest_approved_images(
    session: AsyncSession, motorbike_ids: Sequence[str]
) -> dict[str, MotorbikeImage]:
    """Return the newest approved image of each of `motorbike_ids`, keyed by model id.

    One statement for a whole catalogue page: `DISTINCT ON (motorbike_id)` with
    the matching `ORDER BY` lets PostgreSQL pick the winner per model, so the
    page costs one round trip instead of one per card. A model with no approved
    image is simply absent from the mapping — the caller renders a placeholder,
    it never falls back to a pending picture.

    Args:
        session: Session the statement runs on; nothing is written or committed.
        motorbike_ids: The models to look up. Empty returns `{}` without a round
            trip.
    """
    if not motorbike_ids:
        return {}

    result = await session.execute(_newest_approved_images_statement(motorbike_ids))
    return {image.motorbike_id: image for image in result.scalars().all()}


async def create_backlog(
    session: AsyncSession, name: str, *, suggestion: Mapping[str, Any] | None = None
) -> Motorbike:
    """Create a `backlog` entry for `name` and return it.

    `suggestion` is the unverified claim the entry was proposed with (year
    range, type codes, links — see `app.cli.suggestions`). It is stored as
    given and never promoted into the typed columns here: only research
    confirms those.

    Raises:
        DuplicateModelError: the derived slug is already in the catalogue.
    """
    slug = slugify(name)
    if await get_by_slug(session, slug) is not None:
        raise DuplicateModelError(slug)

    motorbike = Motorbike(
        query_name=name.strip(),
        slug=slug,
        status=MotorbikeStatus.BACKLOG,
        suggestion=dict(suggestion) if suggestion is not None else None,
    )
    session.add(motorbike)
    await session.commit()
    await _announce(session, motorbike.id)
    return motorbike


async def transition(
    session: AsyncSession, motorbike: Motorbike, new_status: MotorbikeStatus
) -> Motorbike:
    """Move `motorbike` to `new_status`, applying that status's side effects.

    Approval is the only status carrying side effects, and they land in the same
    transaction as the status change: the draft specification is promoted to a
    `verified` row and every `pending` image becomes `approved`.

    Raises:
        InvalidTransitionError: the change is not in `LEGAL_TRANSITIONS`.
        IncompleteIdentityError: `new_status` is `approved` and `manufacturer_id`,
            `model_name` or `year_from` is NULL (D4). Raised before the matrix's
            side effects run, so an `in_review` row is the only one that can ever
            see it — `LEGAL_TRANSITIONS` rejects every other starting status
            first.
    """
    if new_status not in LEGAL_TRANSITIONS[motorbike.status]:
        raise InvalidTransitionError(motorbike.status, new_status)

    if new_status is MotorbikeStatus.APPROVED:
        missing = [
            field
            for field, value in (
                ("manufacturer_id", motorbike.manufacturer_id),
                ("model_name", motorbike.model_name),
                ("year_from", motorbike.year_from),
            )
            if value is None
        ]
        if missing:
            raise IncompleteIdentityError(missing)

    motorbike_id = motorbike.id
    motorbike.status = new_status
    if new_status is MotorbikeStatus.APPROVED:
        await _apply_approval(session, motorbike_id)
    await session.commit()
    await _announce(session, motorbike_id)
    return motorbike


async def start_ingestion(session: AsyncSession, motorbike: Motorbike) -> Operation:
    """Move `motorbike` into `ingesting`, track the run and enqueue the job.

    The ordering is the pinned one and the reason this function exists: the
    status change commits, the `queued` operation row commits — so the admin UI
    shows the job the moment it is accepted — and only then is the task
    enqueued. A worker can therefore never pick up a job whose state is not yet
    visible.

    Raises:
        InvalidTransitionError: the row may not start an ingestion right now
            (only `backlog` and `rejected` may).
    """
    await transition(session, motorbike, MotorbikeStatus.INGESTING)
    operation = await operation_service.create(
        session,
        INGESTION_OPERATION_TYPE,
        entity_type=operation_service.MOTORBIKE_ENTITY_TYPE,
        entity_id=motorbike.id,
    )
    await enqueue_ingestion(motorbike.id, operation.id)
    return operation


async def enqueue_ingestion(motorbike_id: str, operation_id: str) -> None:
    """Push `ingestion.run` onto the queue — ids only, after both commits.

    The task module is imported here instead of at module import time on
    purpose: it pulls in the broker and, through the orchestration service,
    this module — a top-level import would be circular, and it would drag the
    Redis wiring into every importer of the catalogue service. This is also the
    seam the test suite replaces, so no test ever needs Redis.
    """
    from app.jobs.ingestion import run as ingestion_run

    await ingestion_run.kiq(motorbike_id, operation_id)


async def transition_image(
    session: AsyncSession, image: MotorbikeImage, new_status: ImageStatus
) -> MotorbikeImage:
    """Move `image` to `new_status` and announce its model as updated.

    The announcement is `product.updated`: images are part of a model's review
    state, and the admin screens refetch a product's images from there.

    Raises:
        InvalidImageTransitionError: the change is not in `LEGAL_IMAGE_TRANSITIONS`.
    """
    if new_status not in LEGAL_IMAGE_TRANSITIONS[image.status]:
        raise InvalidImageTransitionError(image.status, new_status)

    motorbike_id = image.motorbike_id
    image.status = new_status
    await session.commit()
    await _announce(session, motorbike_id)
    return image


async def assign_manufacturer(
    session: AsyncSession, motorbike: Motorbike, manufacturer_id: str | None
) -> Motorbike:
    """Point `motorbike` at a manufacturer row, or at none, and announce it.

    Callers resolve the brand first (`manufacturer_service.get_or_create`) and
    pass its id; `None` clears the reference. The announcement is
    `product.updated` because the admin backlog renders the brand name with the
    row.
    """
    motorbike.manufacturer_id = manufacturer_id
    await session.commit()
    await _announce(session, motorbike.id)
    return motorbike


async def assign_identity(
    session: AsyncSession,
    motorbike: Motorbike,
    *,
    manufacturer_id: str | None,
    buildingline: str | None,
    model_name: str | None,
    year_from: int | None,
    year_to: int | None,
    type_codes: Sequence[str],
    variants: Sequence[Mapping[str, Any]],
) -> Motorbike:
    """Write the whole identity block of `motorbike` and recompute its slug (D2).

    The **only** writer of `manufacturer_id`, `buildingline`, `model_name`,
    `year_from`, `year_to`, `type_codes` and `variants`: every field is a
    full-object replace, never a merge — a caller that wants to keep a stored
    value passes it back in (extraction's merge-before-call rule lives in
    `spec_extraction_service`, per D2b, not here). `buildingline` passes
    through `normalise_buildingline` first; `type_codes` and `variants` are
    re-validated through `identity_validation`, and each dropped entry becomes
    one `logger.warning` — a caller that needs those warnings on its own run
    (extraction, 6.15) validates first and passes the already-clean lists, so
    nothing is dropped silently on its side.

    Slug (D3): when `manufacturer_id`, `model_name` and `year_from` are all
    set, the slug becomes the canonical
    `{manufacturer.slug}/{slugify(model_name)}/{year_from}-{year_to or ''}`.
    With an incomplete identity the row's current slug is left untouched (a
    backlog row keeps `slugify(query_name)`). A collision with another row's
    slug is checked, and `DuplicateModelError` raised, **before** anything is
    written.

    Raises:
        ValueError: `manufacturer_id` is set but does not name a known
            manufacturer.
        DuplicateModelError: the recomputed slug collides with another row's.
    """
    normalised_buildingline = await normalise_buildingline(session, manufacturer_id, buildingline)

    kept_type_codes, type_code_warnings = identity_validation.normalize_type_codes(type_codes)
    kept_variants, variant_warnings = identity_validation.normalize_variants(variants)
    for warning in (*type_code_warnings, *variant_warnings):
        logger.warning("assign_identity(%s): %s", motorbike.id, warning)

    new_slug = motorbike.slug
    if manufacturer_id is not None and model_name is not None and year_from is not None:
        result = await session.execute(
            select(Manufacturer).where(Manufacturer.id == manufacturer_id)
        )
        manufacturer = result.scalar_one_or_none()
        if manufacturer is None:
            raise ValueError(f"Unknown manufacturer id {manufacturer_id!r}.")
        new_slug = f"{manufacturer.slug}/{slugify(model_name)}/{year_from}-{year_to or ''}"

    if new_slug != motorbike.slug:
        colliding = await get_by_slug(session, new_slug)
        if colliding is not None and colliding.id != motorbike.id:
            raise DuplicateModelError(new_slug)

    motorbike.manufacturer_id = manufacturer_id
    motorbike.buildingline = normalised_buildingline
    motorbike.model_name = model_name
    motorbike.year_from = year_from
    motorbike.year_to = year_to
    motorbike.type_codes = kept_type_codes
    motorbike.variants = kept_variants
    motorbike.slug = new_slug

    await session.commit()
    await _announce(session, motorbike.id)
    return motorbike


async def set_suggestion(
    session: AsyncSession, motorbike: Motorbike, suggestion: Mapping[str, Any] | None
) -> Motorbike:
    """Replace the unverified suggestion document of `motorbike` and announce it.

    Nothing else on the row is touched — in particular not the status and not
    the typed columns: a suggestion is a claim, and only research turns a claim
    into a catalogue fact.
    """
    motorbike.suggestion = dict(suggestion) if suggestion is not None else None
    await session.commit()
    await _announce(session, motorbike.id)
    return motorbike


async def upsert_draft_spec(
    session: AsyncSession, motorbike_id: str, values: Mapping[str, Any]
) -> MotorbikeSpec:
    """Replace the draft specification of `motorbike_id` and return the row.

    Full-object semantics: every field of the frozen column set that `values`
    omits is reset (to NULL, or `{}` for `extra`), and a missing draft row is
    created. `a2_eligible` is derived when the incoming value is NULL.

    Raises:
        ValueError: `values` contains a key outside the frozen column set.
    """
    spec = await _upsert_spec(session, motorbike_id, SpecKind.DRAFT, values)
    await session.commit()
    await _announce(session, motorbike_id)
    return spec


def _newest_approved_images_statement(
    motorbike_ids: Sequence[str],
) -> Select[tuple[MotorbikeImage]]:
    """Compose the one statement `newest_approved_images` issues.

    Split out so the SQL can be compiled in a test without a database. The
    `DISTINCT ON` expression must be the leading `ORDER BY` term — that is what
    makes "newest per model" well defined; `created_at DESC, id DESC` then picks
    the same winner the unpaginated `list_images` order would put first.
    """
    return (
        select(MotorbikeImage)
        .distinct(MotorbikeImage.motorbike_id)
        .where(
            MotorbikeImage.motorbike_id.in_(list(motorbike_ids)),
            MotorbikeImage.status == ImageStatus.APPROVED,
        )
        .order_by(
            MotorbikeImage.motorbike_id,
            MotorbikeImage.created_at.desc(),
            MotorbikeImage.id.desc(),
        )
    )


async def _apply_approval(session: AsyncSession, motorbike_id: str) -> None:
    """Promote the draft specification and approve pending images.

    Deliberately does **not** commit: `transition` owns the transaction so the
    status change and these side effects cannot come apart.
    """
    draft = await _get_spec(session, motorbike_id, SpecKind.DRAFT)
    if draft is not None:
        await _upsert_spec(session, motorbike_id, SpecKind.VERIFIED, _spec_values(draft))

    await session.execute(
        update(MotorbikeImage)
        .where(
            MotorbikeImage.motorbike_id == motorbike_id,
            MotorbikeImage.status == ImageStatus.PENDING,
        )
        .values(status=ImageStatus.APPROVED)
    )


async def _upsert_spec(
    session: AsyncSession, motorbike_id: str, kind: SpecKind, values: Mapping[str, Any]
) -> MotorbikeSpec:
    """Write `values` onto the (motorbike, kind) row **without committing**."""
    normalized = _normalize_spec_values(values)
    spec = await _get_spec(session, motorbike_id, kind)
    if spec is None:
        spec = MotorbikeSpec(motorbike_id=motorbike_id, kind=kind)
        session.add(spec)
    for field, value in normalized.items():
        setattr(spec, field, value)
    return spec


def _normalize_spec_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return the full frozen column set, defaults applied, `a2_eligible` resolved."""
    unknown = sorted(set(values) - set(SPEC_FIELDS))
    if unknown:
        raise ValueError(f"Unknown specification fields: {', '.join(unknown)}.")

    normalized = {field: values.get(field) for field in SPEC_FIELDS}
    # The column is NOT NULL; an omitted long tail is an empty one.
    normalized["extra"] = normalized["extra"] or {}
    normalized["a2_eligible"] = _resolve_a2_eligible(normalized)
    return normalized


def _resolve_a2_eligible(values: Mapping[str, Any]) -> bool | None:
    """Return the `a2_eligible` value to store.

    An explicit (admin-set) value always wins. Otherwise the A2 limits are
    applied when both inputs are known, and NULL stands for "cannot tell".
    """
    incoming = values.get("a2_eligible")
    if incoming is not None:
        return bool(incoming)

    power_kw = values.get("power_kw")
    wet_weight_kg = values.get("wet_weight_kg")
    if power_kw is None or wet_weight_kg is None:
        return None

    power = Decimal(str(power_kw))
    weight = Decimal(str(wet_weight_kg))
    if weight <= 0:
        # Not a weight; deriving from it would be arithmetic, not information.
        return None
    return power <= A2_MAX_POWER_KW and power / weight <= A2_MAX_POWER_TO_WEIGHT


def _spec_values(spec: MotorbikeSpec) -> dict[str, Any]:
    return {field: getattr(spec, field) for field in SPEC_FIELDS}


async def _announce(session: AsyncSession, motorbike_id: str) -> None:
    """Publish the pinned `product.updated` payload — ids only, after commit."""
    await operation_service.notify(session, {"event": "product.updated", "productId": motorbike_id})


async def _get_spec(
    session: AsyncSession, motorbike_id: str, kind: SpecKind
) -> MotorbikeSpec | None:
    result = await session.execute(
        select(MotorbikeSpec).where(
            MotorbikeSpec.motorbike_id == motorbike_id, MotorbikeSpec.kind == kind
        )
    )
    return result.scalar_one_or_none()
