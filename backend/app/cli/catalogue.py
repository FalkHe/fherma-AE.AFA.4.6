"""`app catalogue` — deterministic corrections to an existing catalogue entry.

No LLM, no network: every command here does exactly what its arguments say, so
it is safe to run against the live catalogue.

- `app catalogue set-manufacturer` (step 2b.2) assigns a brand to one model,
  creating the `manufacturers` row when the brand is new. It is the backfill
  tool for entries that were ingested before extraction filled the brand, and
  the only manual correction path until an admin surface exists. Nothing else is
  touched — in particular no documents, chunks or embeddings, which is why the
  backfill goes through this command instead of a re-ingestion.
- `app catalogue render-name` (step 6.11) is a debugging aid for
  `naming_service.render_name`: no write, no LLM, no network. It prints the
  same row's name at both `MODEL` and `YEAR_RANGE` min-levels, using any
  `--context` ids supplied as the ambiguity set.
- `app catalogue set-identity` (step 6.12) writes a full identity onto one
  catalogue entry through `product_service.assign_identity` — the single
  writer of that block (D2) — and prints the row's (possibly recomputed)
  slug. It is the first caller of `assign_identity`; 6.18's backfill and the
  admin PATCH (6.20) call the same service function later.
- `app catalogue backfill-identity` (step 6.18) is the deterministic,
  never-re-ingestion backfill of `model_name` (the 2b rule: a fresh ingestion
  run would delete that bike's documents and embeddings). For every row whose
  `model_name IS NULL` and `manufacturer_id IS NOT NULL` it derives
  `model_name` mechanically — the FK'd manufacturer's name stripped as a
  case-insensitive prefix of `query_name`, verbatim `query_name` otherwise —
  and writes it through `assign_identity`, unchanged `buildingline`/
  `year_from`/`year_to`/`type_codes`/`variants`. Never reads `suggestion`
  (D6). Then prints the pinned gap table of every row still missing a year
  range, approved ones flagged (OQ-6/D4). `--dry-run` writes nothing.

Follows the CLI async pattern of `app.cli.ingest`: the Typer command body stays
synchronous and calls `asyncio.run(...)`.
"""

import asyncio
import json
from typing import Annotated, NoReturn

import typer
from sqlalchemy import select

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.session import get_sessionmaker
from app.services import manufacturer_service, naming_service, product_service

app = typer.Typer(
    help="Correct one catalogue entry, deterministically.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("set-manufacturer")
def set_manufacturer(
    slug: Annotated[
        str,
        typer.Argument(help='Slug of an existing catalogue entry, e.g. "suzuki-gsr600".'),
    ],
    name: Annotated[str, typer.Argument(help='Brand name only, e.g. "Suzuki".')],
) -> None:
    """Assign a manufacturer to one catalogue entry, creating the brand if new.

    The brand's identity is its slug, so `"BMW"`, `"bmw"` and `"  BMW "` all
    reuse the same row; the display name stays the one first stored. Running the
    command again with the same brand changes nothing but the announcement.
    """
    manufacturer = asyncio.run(_set_manufacturer(slug, name))
    typer.echo(f"{slug} now belongs to manufacturer {manufacturer.name!r} ({manufacturer.id}).")


async def _set_manufacturer(slug: str, name: str) -> Manufacturer:
    """Async half of `set-manufacturer`: one session, two service calls.

    The catalogue entry is resolved first, so an unknown slug reports itself
    before a manufacturer row is created for nothing.
    """
    async with get_sessionmaker()() as session:
        motorbike = await product_service.get_by_slug(session, slug)
        if motorbike is None:
            _fail(f"No catalogue entry with slug {slug!r}.")
        try:
            manufacturer = await manufacturer_service.get_or_create(session, name)
        except ValueError as error:
            _fail(str(error))
        await product_service.assign_manufacturer(session, motorbike, manufacturer.id)
        return manufacturer


@app.command("render-name")
def render_name(
    motorbike_id: Annotated[str, typer.Argument(help="Id of the catalogue entry to render.")],
    context: Annotated[
        list[str] | None,
        typer.Option(
            "--context", help="Additional id(s) to render alongside, as the ambiguity set."
        ),
    ] = None,
) -> None:
    """Print `motorbike_id`'s name at both the `MODEL` and `YEAR_RANGE` levels.

    `--context` supplies the other rows to check for a collision against, the
    way a real caller's `context` set would (data-model doc §5's per-caller
    table). An unknown `motorbike_id` reports itself and exits non-zero;
    unknown `--context` ids are silently absent, exactly as
    `naming_service.load_name_parts` documents.
    """
    for line in asyncio.run(_render_name(motorbike_id, context or [])):
        typer.echo(line)


async def _render_name(motorbike_id: str, context_ids: list[str]) -> list[str]:
    async with get_sessionmaker()() as session:
        parts = await naming_service.load_name_parts(session, [motorbike_id, *context_ids])
        target = parts.get(motorbike_id)
        if target is None:
            _fail(f"No catalogue entry with id {motorbike_id!r}.")
        context = [p for id_, p in parts.items() if id_ != motorbike_id]
        model = naming_service.render_name(
            target, context=context, min_level=naming_service.NameLevel.MODEL
        )
        year_range = naming_service.render_name(
            target, context=context, min_level=naming_service.NameLevel.YEAR_RANGE
        )
        return [f"MODEL: {model}", f"YEAR_RANGE: {year_range}"]


@app.command("set-identity")
def set_identity(
    slug: Annotated[
        str,
        typer.Argument(help='Slug of an existing catalogue entry, e.g. "suzuki-gsr600".'),
    ],
    manufacturer: Annotated[
        str,
        typer.Option("--manufacturer", help='Brand name, e.g. "BMW". Created if new.'),
    ],
    model_name: Annotated[
        str,
        typer.Option("--model-name", help='Structured model name, e.g. "R 1250 GS".'),
    ],
    year_from: Annotated[
        int, typer.Option("--year-from", help="First model year of this generation.")
    ],
    year_to: Annotated[
        int | None,
        typer.Option("--year-to", help="Last model year; omit for an open-ended range."),
    ] = None,
    buildingline: Annotated[
        str | None, typer.Option("--buildingline", help='Model family, e.g. "GS".')
    ] = None,
    type_code: Annotated[
        list[str] | None,
        typer.Option("--type-code", help="Manufacturer type code, e.g. K50. May repeat."),
    ] = None,
    variants_json: Annotated[
        str,
        typer.Option("--variants-json", help="JSON list of trim objects."),
    ] = "[]",
) -> None:
    """Assign a full identity to `slug`'s catalogue entry and recompute its slug.

    Resolves the row by `slug` first (an unknown one reports itself), then
    gets-or-creates the manufacturer brand, then calls
    `product_service.assign_identity` — the single writer of the identity
    block (D2). A recomputed slug that collides with another row is reported
    instead of applied.
    """
    new_slug = asyncio.run(
        _set_identity(
            slug,
            manufacturer,
            model_name,
            year_from,
            year_to,
            buildingline,
            type_code or [],
            variants_json,
        )
    )
    typer.echo(f"{slug} now has slug {new_slug!r}.")


async def _set_identity(
    slug: str,
    manufacturer_name: str,
    model_name: str,
    year_from: int,
    year_to: int | None,
    buildingline: str | None,
    type_codes: list[str],
    variants_json: str,
) -> str:
    """Async half of `set-identity`: parse input, resolve the row, write it."""
    try:
        variants = json.loads(variants_json)
    except json.JSONDecodeError as error:
        _fail(f"Invalid --variants-json: {error}")
    if not isinstance(variants, list):
        _fail("--variants-json must be a JSON list.")

    async with get_sessionmaker()() as session:
        motorbike = await product_service.get_by_slug(session, slug)
        if motorbike is None:
            _fail(f"No catalogue entry with slug {slug!r}.")
        try:
            manufacturer = await manufacturer_service.get_or_create(session, manufacturer_name)
        except ValueError as error:
            _fail(str(error))
        try:
            updated = await product_service.assign_identity(
                session,
                motorbike,
                manufacturer_id=manufacturer.id,
                buildingline=buildingline,
                model_name=model_name,
                year_from=year_from,
                year_to=year_to,
                type_codes=type_codes,
                variants=variants,
            )
        except product_service.DuplicateModelError as error:
            _fail(f"A catalogue entry with slug {error.args[0]!r} already exists.")
        return updated.slug


@app.command("backfill-identity")
def backfill_identity(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print what would change; write nothing."),
    ] = False,
) -> None:
    """Derive `model_name` for every FK'd row that still lacks one.

    Strips the FK'd manufacturer's name as a case-insensitive prefix of
    `query_name` (`"BMW S 1000 XR"` − `"BMW"` → `"S 1000 XR"`), falling back
    to `query_name` verbatim when it does not start with the manufacturer's
    name. Writes through `product_service.assign_identity` (D2), passing the
    row's current `buildingline`/`year_from`/`year_to`/`type_codes`/`variants`
    unchanged — deterministic, never re-ingestion (the 2b rule), never reads
    `suggestion` (D6). A recomputed-slug collision (`DuplicateModelError`) is
    printed and the row is left unchanged, never deleted. Rows without a
    `manufacturer_id` are listed as skipped, never touched. Finishes by
    printing every row still missing a year range (`year_from IS NULL`),
    flagging approved ones (OQ-6/D4). `--dry-run` prints what would be set and
    writes nothing.
    """
    for line in asyncio.run(_backfill_identity(dry_run=dry_run)):
        typer.echo(line)


async def _backfill_identity(*, dry_run: bool) -> list[str]:
    lines: list[str] = []
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Motorbike).where(Motorbike.model_name.is_(None)))
        candidates = sorted(result.scalars().all(), key=lambda motorbike: motorbike.slug)

        fk_rows = [motorbike for motorbike in candidates if motorbike.manufacturer_id is not None]
        skipped_rows = [motorbike for motorbike in candidates if motorbike.manufacturer_id is None]
        manufacturers = await manufacturer_service.get_by_ids(
            session, [motorbike.manufacturer_id for motorbike in fk_rows]
        )

        for motorbike in fk_rows:
            manufacturer = manufacturers[motorbike.manufacturer_id]
            model_name = _strip_manufacturer_prefix(motorbike.query_name, manufacturer.name)
            if dry_run:
                lines.append(f"WOULD SET {motorbike.slug}: model_name={model_name!r}")
                continue
            try:
                updated = await product_service.assign_identity(
                    session,
                    motorbike,
                    manufacturer_id=motorbike.manufacturer_id,
                    buildingline=motorbike.buildingline,
                    model_name=model_name,
                    year_from=motorbike.year_from,
                    year_to=motorbike.year_to,
                    type_codes=motorbike.type_codes or [],
                    variants=motorbike.variants or [],
                )
            except product_service.DuplicateModelError as error:
                lines.append(
                    f"COLLISION {motorbike.slug}: recomputed slug {error.args[0]!r} already "
                    "exists, left unchanged"
                )
                continue
            lines.append(f"SET {motorbike.slug}: model_name={model_name!r} (slug {updated.slug!r})")

        for motorbike in skipped_rows:
            lines.append(f"SKIPPED {motorbike.slug}: no manufacturer_id")

        lines.append("--- Rows still missing a year range ---")
        gap_result = await session.execute(select(Motorbike).where(Motorbike.year_from.is_(None)))
        gap_rows = sorted(gap_result.scalars().all(), key=lambda motorbike: motorbike.slug)
        if not gap_rows:
            lines.append("(none)")
        for motorbike in gap_rows:
            flag = " [APPROVED]" if motorbike.status is MotorbikeStatus.APPROVED else ""
            lines.append(f"{motorbike.slug} ({motorbike.status.value}){flag}")
    return lines


def _strip_manufacturer_prefix(query_name: str, manufacturer_name: str) -> str:
    """Return `query_name` minus `manufacturer_name`'s case-insensitive prefix.

    `"BMW S 1000 XR"` − `"BMW"` → `"S 1000 XR"`. When `query_name` does not
    start with `manufacturer_name` (case-insensitively), or stripping it would
    leave nothing behind, `query_name` is kept verbatim (never an empty
    `model_name`).
    """
    if query_name.lower().startswith(manufacturer_name.lower()):
        stripped = query_name[len(manufacturer_name) :].strip()
        if stripped:
            return stripped
    return query_name


def _fail(message: str) -> NoReturn:
    """Report why nothing was changed on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
