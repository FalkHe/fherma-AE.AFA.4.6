"""Motorcycle brands: normalisation, get-or-create and the read companions.

This module owns its transactions and speaks no HTTP, like every service here.

One rule lives here and nowhere else: **the slug is a brand's identity.** Every
writer goes through `get_or_create`, which normalises the incoming display name,
derives the slug with the same rule `motorbikes.slug` uses and reuses the
existing row when that slug is already known — so "BMW ", "bmw" and "BMW" are
one manufacturer, whichever ingestion saw the brand first.

Nothing here announces an event: a manufacturer has no admin screen of its own
yet. The catalogue row that starts pointing at one is announced by
`product_service.assign_manufacturer`.

**D14 — known-marque normalisation.** After the trim/collapse/truncate above,
`normalize_name` matches the collapsed name case-insensitively against
`known_marques.KNOWN_MARQUES`, longest marque first, and maps an exact match or
a `"{marque} "` prefix match onto the marque's canonical spelling:
`"Kawasaki Motors"` → `"Kawasaki"`, `"Honda Motor"` → `"Honda"`, `"bmw"` →
`"BMW"`. A name that does not start with a known marque passes through
unchanged — this never invents a marque, so `"MV Agusta"` is untouched and
`"Big Honda Fan Club"` is untouched too (the marque must be the first word, not
merely present anywhere in the string). The intended, load-bearing consequence:
`get_or_create("Kawasaki Motors")` now resolves to the same row as
`get_or_create("Kawasaki")`, by construction, for every caller — extraction's
`_assign_identity`/`_resolve_manufacturer_id` and `app catalogue
set-manufacturer` included. Do not "fix" that into two rows again.
"""

import re
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.manufacturer import NAME_LENGTH, Manufacturer
from app.services.known_marques import KNOWN_MARQUES
from app.services.product_service import slugify

_WHITESPACE_RUN = re.compile(r"\s+")

# Longest marque first, so "Harley-Davidson" is tried before any shorter
# marque that could otherwise prefix-match a token inside it.
_MARQUES_LONGEST_FIRST = sorted(KNOWN_MARQUES, key=len, reverse=True)


def normalize_name(raw: str | None) -> str | None:
    """Return the display form to store, or `None` when there is no name.

    Trimmed, internal whitespace collapsed to single spaces and truncated to the
    column width: `"  suzuki   motor  "` → `"suzuki motor"`. Then matched
    case-insensitively against the known-marque list (D14, module docstring):
    an exact match or a `"{marque} "` prefix match is replaced by the marque's
    canonical spelling; anything else keeps the collapsed casing the first
    writer used.
    """
    if raw is None:
        return None
    collapsed = _WHITESPACE_RUN.sub(" ", raw).strip()[:NAME_LENGTH]
    if not collapsed:
        return None

    lowered = collapsed.lower()
    for marque in _MARQUES_LONGEST_FIRST:
        marque_lower = marque.lower()
        if lowered == marque_lower or lowered.startswith(marque_lower + " "):
            return marque
    return collapsed


async def get_or_create(session: AsyncSession, name: str) -> Manufacturer:
    """Return the manufacturer identified by `name`'s slug, creating it if new.

    The name is normalised first, so the stored display form and the derived
    slug cannot disagree. A concurrent ingestion may win the race between the
    lookup and the insert; the unique slug constraint catches that, and the row
    the other transaction committed is returned instead.

    Raises:
        ValueError: `name` normalises to nothing, or to a name without a single
            character the slug rule keeps — there is no identity to store.
    """
    display_name = normalize_name(name)
    slug = "" if display_name is None else slugify(display_name)
    if not slug:
        raise ValueError(f"Manufacturer name '{name}' has no slug characters.")

    existing = await _get_by_slug(session, slug)
    if existing is not None:
        return existing

    manufacturer = Manufacturer(name=display_name, slug=slug)
    session.add(manufacturer)
    try:
        await session.commit()
    except IntegrityError:
        # Someone else inserted the same slug between the lookup and the
        # insert: drop this transaction and take their row.
        await session.rollback()
        concurrent = await _get_by_slug(session, slug)
        if concurrent is None:
            raise
        return concurrent
    return manufacturer


async def get_by_ids(session: AsyncSession, ids: Sequence[str]) -> dict[str, Manufacturer]:
    """Return the manufacturers of several ids, keyed by id.

    One query for a whole page of the catalogue (the `get_specs` pattern): an id
    that is `None` upstream is simply not asked for, and an unknown id is absent
    from the result.
    """
    if not ids:
        return {}

    result = await session.execute(select(Manufacturer).where(Manufacturer.id.in_(list(ids))))
    return {manufacturer.id: manufacturer for manufacturer in result.scalars().all()}


async def list_manufacturers(
    session: AsyncSession, *, limit: int, offset: int
) -> tuple[list[Manufacturer], int]:
    """Return one page of manufacturers by name plus the unpaginated total.

    Alphabetical, not newest-first like the catalogue: this is a reference list.
    Paging is stable without a tiebreaker — two rows cannot carry the same name,
    because equal names derive the same (unique) slug.
    """
    total = await session.execute(select(func.count()).select_from(Manufacturer))
    page = await session.execute(
        select(Manufacturer).order_by(Manufacturer.name).limit(limit).offset(offset)
    )
    return list(page.scalars().all()), total.scalar_one()


async def _get_by_slug(session: AsyncSession, slug: str) -> Manufacturer | None:
    result = await session.execute(select(Manufacturer).where(Manufacturer.slug == slug))
    return result.scalar_one_or_none()
