"""Rendering catalogue names — the one module that turns parts into a string.

Per `docs/roadmap/stage-01/phase-6/shared-knowledge.md` D5: the database stores parts
(`manufacturer`, `buildingline`, `model_name`, a year range), never a
pre-built display string, and exactly one module — this one — turns those
parts into text, on the server, so every surface (tools, API, CLI) renders
identically and the frontend never formats a name. See
`docs/roadmap/model-naming-data-model.md` §5 for the algorithm this module
implements verbatim, and `docs/model-naming.md` ("Rendering rule", "Year
range instead of a single year") for the domain rules behind it.

Escalation is exactly three levels (buildingline → model → model + year
range): under D2 a row has no variant name of its own, and under D5 a type
code is internal and has no single value to print, so both the domain doc's
level 2 (`+ Variant`) and level 4 (`+ Type code`) are skipped. Trims and type
codes are rendered as their own UI elements elsewhere, never inside a name.

`render_name` **never queries the database** and caches nothing — "ambiguous
in the target context" is the caller's `context` set, not a catalogue-wide
uniqueness check (D5 explicitly forbids both). `load_name_parts` is the only
function here that touches a session, and it is a batched read: no writes, no
commits.

Frozen rendered spellings (pin these — 6.19/6.20/QA assert against them):

* year range, both years known: ``(2019–2023)`` — an en dash, no spaces
  around it;
* year range, open end (``year_to is None``): ``(from 2023)``;
* no year range at all (``year_from is None``): the year segment is omitted
  entirely, not rendered as an empty pair of parentheses;
* the last-resort id suffix, for a genuine data bug (two rows sharing
  manufacturer, model *and* year range): the escalated name, a space, then the
  last 6 characters of the id in square brackets — e.g.
  ``"BMW R 1250 GS (2019–2023) [a1b2c3]"`` — alongside a
  ``logger.warning``.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike

logger = logging.getLogger(__name__)

# The em/en dash used to join a closed year range. Pinned — see module docstring.
_YEAR_RANGE_DASH = "–"


class NameLevel(IntEnum):
    """How much of a name to render. Higher levels are more specific."""

    BUILDINGLINE = 0  # never returned by `render_name`; headings/facets only
    MODEL = 1  # "BMW R 1300 GS"
    YEAR_RANGE = 2  # "BMW R 1250 GS (2019–2023)" — the highest level there is


@dataclass(frozen=True, slots=True)
class NameParts:
    """Everything `render_name` needs for one catalogue row, batched by `load_name_parts`."""

    motorbike_id: str
    manufacturer: str | None
    buildingline: str | None
    model_name: str | None
    year_from: int | None
    year_to: int | None
    query_name: str


async def load_name_parts(
    session: AsyncSession, motorbike_ids: Sequence[str]
) -> dict[str, NameParts]:
    """Return `NameParts` for every id in `motorbike_ids` that exists.

    Two selects, no ORM relationships (per the schema's convention): the
    motorbike rows by id, then the referenced manufacturers' names by the
    `manufacturer_id`s collected from those rows. An unknown id is simply
    absent from the result — never an error.
    """
    if not motorbike_ids:
        return {}

    result = await session.execute(select(Motorbike).where(Motorbike.id.in_(list(motorbike_ids))))
    motorbikes = list(result.scalars().all())

    manufacturer_ids = {
        motorbike.manufacturer_id
        for motorbike in motorbikes
        if motorbike.manufacturer_id is not None
    }
    manufacturer_names: dict[str, str] = {}
    if manufacturer_ids:
        manufacturer_result = await session.execute(
            select(Manufacturer).where(Manufacturer.id.in_(list(manufacturer_ids)))
        )
        manufacturer_names = {
            manufacturer.id: manufacturer.name
            for manufacturer in manufacturer_result.scalars().all()
        }

    return {
        motorbike.id: NameParts(
            motorbike_id=motorbike.id,
            manufacturer=(
                manufacturer_names.get(motorbike.manufacturer_id)
                if motorbike.manufacturer_id is not None
                else None
            ),
            buildingline=motorbike.buildingline,
            model_name=motorbike.model_name,
            year_from=motorbike.year_from,
            year_to=motorbike.year_to,
            query_name=motorbike.query_name,
        )
        for motorbike in motorbikes
    }


def render_name(
    parts: NameParts,
    *,
    context: Sequence[NameParts] = (),
    min_level: NameLevel = NameLevel.MODEL,
) -> str:
    """Render `parts` at the shortest level that is unambiguous in `context`.

    The six-step algorithm of `docs/roadmap/model-naming-data-model.md` §5,
    verbatim:

    1. `model_name is None` → return `query_name` verbatim. Nothing structured
       exists; never invent a name — this fallback is load-bearing (it is what
       keeps rows with no identity yet rendering something sensible).
    2. Start at `max(MODEL, min_level)`; render.
    3. Ambiguous? — another member of `context` with a different
       `motorbike_id` renders the *same string at the current level*.
       Not ambiguous → return.
    4. Escalate to `+ year range` and re-test, against the colliding subset
       only.
    5. The year range renders `(2019–2023)`, `(from 2023)` when
       `year_to is None`, and is skipped entirely when `year_from is None`.
    6. Still colliding after the year range (a data bug: identical
       manufacturer, model and year range on two rows) → append the last 6
       characters of the id, deterministic, and `logger.warning`.
    """
    if parts.model_name is None:
        return parts.query_name

    level = max(NameLevel.MODEL, min_level)
    rendered = _render_at(parts, level)

    colliding = [
        other
        for other in context
        if other.motorbike_id != parts.motorbike_id and _render_at(other, level) == rendered
    ]
    if not colliding:
        return rendered

    rendered = _render_at(parts, NameLevel.YEAR_RANGE)
    colliding = [
        other for other in colliding if _render_at(other, NameLevel.YEAR_RANGE) == rendered
    ]
    if not colliding:
        return rendered

    suffix = parts.motorbike_id[-6:]
    logger.warning(
        "naming_service: %r still collides with %d row(s) after the year range "
        "(%s); appending id suffix %r.",
        parts.motorbike_id,
        len(colliding),
        rendered,
        suffix,
    )
    return f"{rendered} [{suffix}]"


def render_names(
    parts: Sequence[NameParts], *, min_level: NameLevel = NameLevel.MODEL
) -> dict[str, str]:
    """Render every member of `parts`, each using the others as its `context`."""
    return {p.motorbike_id: render_name(p, context=parts, min_level=min_level) for p in parts}


def render_buildingline(parts: NameParts) -> str | None:
    """Render the level-0 group heading ("BMW GS"), for headings/facets only.

    Returns `None` when there is no buildingline to show — this is never a
    machine's name and is never returned by `render_name`.
    """
    if parts.buildingline is None:
        return None
    manufacturer = parts.manufacturer or ""
    return f"{manufacturer} {parts.buildingline}".strip()


def _render_at(parts: NameParts, level: NameLevel) -> str:
    """Render `parts` at exactly `level` (MODEL or YEAR_RANGE)."""
    manufacturer = parts.manufacturer or ""
    base = f"{manufacturer} {parts.model_name}".strip()
    if level < NameLevel.YEAR_RANGE:
        return base

    year_range = _render_year_range(parts.year_from, parts.year_to)
    return f"{base} {year_range}" if year_range else base


def _render_year_range(year_from: int | None, year_to: int | None) -> str:
    """Render the `(2019–2023)` / `(from 2023)` segment, or `""` when unknown."""
    if year_from is None:
        return ""
    if year_to is None:
        return f"(from {year_from})"
    return f"({year_from}{_YEAR_RANGE_DASH}{year_to})"
