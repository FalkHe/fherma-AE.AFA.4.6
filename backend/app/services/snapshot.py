"""Portable, committable snapshots of the curated catalogue — demo purpose only.

The catalogue is expensive: every row behind it cost web searches, LLM
extraction calls and embedding calls. A fresh clone of this repository has no
way to reproduce it, and `app seed demo` only re-runs the pipeline (money, API
keys, ten minutes per model, non-deterministic results). So the catalogue is
snapshotted into the repository and restored verbatim.

**This is a demo fixture, not a backup product.** It is deliberately not a
`pg_dump`: the archive must survive a schema migration (a new nullable column
appears, an old snapshot still loads), be reviewable in `git`, and carry the
on-disk payloads that live outside PostgreSQL. What it is *not* is
point-in-time-correct, transactional against a live instance, or a substitute
for real backups.

What travels
------------
Seven catalogue tables, in FK-safe insert order (`TABLE_ORDER`), plus the two
file trees the rows point at:

- `DATA_DIR` — the retained raw payload behind every `source_documents` row
  (`raw_path`), stored gzipped in the archive because it is HTML.
- `MEDIA_DIR` — every `motorbike_images` original *and* its three generated
  WebP variants, plus any `manufacturers.logo_path`. Stored verbatim: WebP and
  JPEG do not compress twice.

What does not travel: `users`, `sessions`, `chats`, `chat_messages`,
`chat_preferences`, `operations`. Accounts are created by `app users create`,
and conversations plus the ingestion audit log are per-instance runtime state —
restoring another instance's history would be misleading, not helpful.

The archive layout
------------------
    manifest.json                  # version, provenance, expected counts
    tables/<table>.jsonl.gz        # one JSON object per row, PK-ordered
    data/<DATA_DIR-relative>.gz    # retained raw source payloads
    media/<MEDIA_DIR-relative>     # image originals and variants, verbatim

One file per payload rather than a single tarball, on purpose: adding a model
to the catalogue then adds files to the commit instead of rewriting one
95 MB blob.

Why JSONL and not SQL
---------------------
Rows are encoded column-by-column from the SQLAlchemy table metadata, so the
codec follows the schema automatically. Import is tolerant in exactly one
direction: a column present in the schema but absent from an older archive
falls back to its database default, which is what makes a snapshot survive an
additive migration. A column present in the archive but *gone* from the schema
is a hard error — silently dropping data would be worse than refusing.

Type handling is explicit because JSON has fewer types than PostgreSQL:

- `Vector` (pgvector) → base64 of little-endian float32. The column is
  PostgreSQL `float4`, so float32 round-trips exactly, and base64 is ~2.7x
  smaller than a JSON array of decimal literals. Embeddings therefore restore
  byte-identically and **no embedding API call is needed to seed an instance**.
- `Numeric` → decimal string, never a JSON float, so `Decimal("48.5")` cannot
  become `48.499999999999996`.
- `DateTime(timezone=True)` → ISO 8601 with offset.
- `Enum` → its member *value* (the same string PostgreSQL stores).
- `Computed` columns (`chunks.text_tsv`) are skipped entirely: PostgreSQL
  regenerates them, and an insert may not write them.
"""

import base64
import gzip
import json
import logging
import shutil
import struct
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from pathlib import Path, PurePosixPath
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, Enum, Numeric, Table, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.chunk import Chunk
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike
from app.db.models.motorbike_image import MotorbikeImage
from app.db.models.motorbike_spec import MotorbikeSpec
from app.db.models.motorbike_used_price import MotorbikeUsedPrice
from app.db.models.source_document import SourceDocument
from app.services import image_service

logger = logging.getLogger(__name__)

# Bumped only for a change no importer can absorb; an archive from the future
# is refused rather than half-read.
SNAPSHOT_VERSION = 1

# Where `app snapshot save` writes and `app snapshot load` reads by default.
# `.../backend/app/services/snapshot.py` -> `.../backend/resources/catalogue`,
# which is `./backend` on the host — the bind mount means a snapshot written
# inside the container lands in the working tree, ready to commit.
DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "resources" / "catalogue-snapshot"

MANIFEST_NAME = "manifest.json"
TABLES_DIRECTORY = "tables"
DATA_DIRECTORY = "data"
MEDIA_DIRECTORY = "media"

# Gzip level for the JSONL tables and the retained HTML. 6 is the default
# trade-off; 9 buys ~2% here for several times the CPU.
GZIP_LEVEL = 6

# The archive's own suffix for a gzipped payload file.
GZIP_SUFFIX = ".gz"

# How many rows one INSERT carries. Keeps the parameter count per statement
# well inside PostgreSQL's 65535 limit even for the widest table.
INSERT_BATCH_ROWS = 250

# FK-safe insert order; deletion walks it backwards. Every table listed here is
# part of the catalogue and nothing else is.
TABLE_ORDER: tuple[Table, ...] = (
    Manufacturer.__table__,
    Motorbike.__table__,
    MotorbikeSpec.__table__,
    MotorbikeUsedPrice.__table__,
    SourceDocument.__table__,
    MotorbikeImage.__table__,
    Chunk.__table__,
)

# Marker key wrapping a base64 float32 payload, so an embedding is never
# mistaken for an ordinary JSON list.
VECTOR_KEY = "$f32"

# Marker distinguishing a JSON column holding the literal `null` from one
# holding SQL NULL. Both read back as Python `None`, but `IS NULL` tells them
# apart, so the archive must too.
JSON_NULL_KEY = "$jsonnull"


class SnapshotError(Exception):
    """The snapshot cannot be written or read. Carries a message for the CLI."""


@dataclass
class SnapshotReport:
    """What a save or load actually did, for the CLI's summary."""

    tables: dict[str, int] = field(default_factory=dict)
    data_files: int = 0
    media_files: int = 0
    # Rows pointing at a payload that is not on disk. Never fatal: a snapshot
    # of a catalogue whose media was pruned is still worth having.
    missing_files: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(self.tables.values())


# --------------------------------------------------------------------------
# Row codec. Pure functions — no session, no filesystem, no settings.
# --------------------------------------------------------------------------


def exported_columns(table: Table) -> tuple[Column[Any], ...]:
    """Return the columns a snapshot carries for `table`.

    Computed columns are excluded: PostgreSQL derives them (`chunks.text_tsv`
    from `chunks.text`) and rejects an insert that supplies one.
    """
    return tuple(column for column in table.columns if column.computed is None)


def encode_row(table: Table, row: Mapping[str, Any]) -> dict[str, Any]:
    """Project one database row onto its JSON-serialisable archive form.

    For a JSON column, `row` is expected to also carry the boolean produced by
    `sql_null_label(name)` — see `_read_table`. Without it a NULL JSON column
    is archived as SQL NULL, which is the safe reading for a hand-built row.
    """
    encoded: dict[str, Any] = {}
    json_columns = json_column_names(table)
    for column in exported_columns(table):
        value = row[column.name]
        if column.name in json_columns and value is None:
            # Two different database states arrive here as the same Python
            # `None`: SQL NULL, and the JSON literal `null` that SQLAlchemy's
            # JSON type writes for a Python `None` (both exist in the live
            # catalogue — `motorbikes.suggestion` has SQL NULLs,
            # `motorbike_specs.source_hints` has a JSON `null`). Only the
            # accompanying `IS NULL` flag can tell them apart, and they are not
            # interchangeable: `WHERE col IS NULL` matches one and not the
            # other. SQL NULL keeps the plain `null` encoding; a JSON `null`
            # gets the marker.
            is_sql_null = bool(row.get(sql_null_label(column.name), True))
            encoded[column.name] = None if is_sql_null else {JSON_NULL_KEY: True}
            continue
        encoded[column.name] = _encode(column, value)
    return encoded


def decode_row(table: Table, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Turn one archive row back into INSERT parameters for `table`.

    A column missing from `payload` is omitted from the result, so the database
    applies its own default — this is what lets an archive written before an
    additive migration still load. A key in `payload` that no longer maps to a
    column is an error: it is data the caller believes is being restored.

    A JSON column is the one place where an omitted key is *chosen* rather than
    inherited: see `encode_row`. A SQL NULL is restored by leaving the column
    out of the INSERT entirely (nothing else produces a real SQL NULL through
    SQLAlchemy's JSON type), and a JSON `null` by passing Python `None`.
    """
    columns = {column.name: column for column in exported_columns(table)}
    unknown = sorted(set(payload) - set(columns))
    if unknown:
        raise SnapshotError(
            f"Snapshot row for {table.name!r} carries column(s) {', '.join(unknown)} "
            "that no longer exist in the schema; the archive is too old to load."
        )

    json_columns = json_column_names(table)
    params: dict[str, Any] = {}
    for name, value in payload.items():
        if name in json_columns:
            if value is None:
                continue  # SQL NULL: let the column default apply.
            if _is_json_null_marker(value):
                params[name] = None  # SQLAlchemy renders this as JSON `null`.
                continue
        params[name] = _decode(columns[name], value)
    return params


def insert_groups(
    table: Table, payloads: Iterable[Mapping[str, Any]]
) -> list[list[dict[str, Any]]]:
    """Decode `payloads` into INSERT parameter dicts, grouped by their key set.

    `executemany` needs one uniform key set per statement, and `decode_row`
    legitimately produces rows with different key sets: a SQL NULL JSON column
    is expressed by omission, and so is a column an older archive predates.
    Grouping keeps the insert set-based — there are only a handful of distinct
    signatures per table, never one group per row.
    """
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for payload in payloads:
        params = decode_row(table, payload)
        groups.setdefault(tuple(sorted(params)), []).append(params)
    return list(groups.values())


def json_column_names(table: Table) -> frozenset[str]:
    """Names of `table`'s JSON-typed columns. `JSONB` subclasses `JSON`."""
    return frozenset(
        column.name for column in exported_columns(table) if isinstance(column.type, JSON)
    )


def sql_null_label(column_name: str) -> str:
    """Label of the helper column carrying `column_name`'s `IS NULL` result.

    Prefixed so it can never collide with a real column name.
    """
    return f"__sql_null__{column_name}"


def _is_json_null_marker(value: Any) -> bool:
    """True for `encode_row`'s "this was the JSON literal null" marker."""
    return isinstance(value, dict) and value.get(JSON_NULL_KEY) is True


def _encode(column: Column[Any], value: Any) -> Any:
    """Encode one column value. The inverse of `_decode`."""
    if value is None:
        return None
    if isinstance(column.type, Vector):
        return {VECTOR_KEY: _encode_vector(value)}
    if isinstance(column.type, Enum):
        # StrEnum members are already `str`; take `.value` so the archive never
        # depends on the member *name* matching the stored value.
        return value.value if isinstance(value, PyEnum) else value
    if isinstance(column.type, DateTime):
        return value.isoformat()
    if _is_decimal(column):
        return str(value)
    return value


def _decode(column: Column[Any], value: Any) -> Any:
    """Decode one archived column value. The inverse of `_encode`."""
    if value is None:
        return None
    if isinstance(column.type, Vector):
        return _decode_vector(value)
    if isinstance(column.type, Enum) and column.type.enum_class is not None:
        return column.type.enum_class(value)
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if _is_decimal(column):
        return Decimal(value)
    return value


def _is_decimal(column: Column[Any]) -> bool:
    """True for a `Numeric` column that hands back `Decimal`.

    `Float` subclasses `Numeric` in SQLAlchemy, hence the `asdecimal` check
    rather than a bare `isinstance`.
    """
    return isinstance(column.type, Numeric) and bool(column.type.asdecimal)


def _encode_vector(value: Iterable[float]) -> str:
    """Pack an embedding as base64 of little-endian float32.

    The source column is pgvector's `float4`, so no precision is lost. `value`
    may be a list or the numpy array pgvector returns; both iterate as floats.
    """
    floats = [float(element) for element in value]
    return base64.b64encode(struct.pack(f"<{len(floats)}f", *floats)).decode("ascii")


def _decode_vector(value: Any) -> list[float]:
    """Unpack `_encode_vector`'s form back into the list pgvector accepts."""
    if not isinstance(value, dict) or VECTOR_KEY not in value:
        raise SnapshotError(f"Malformed embedding in snapshot: expected a {VECTOR_KEY!r} object.")
    raw = base64.b64decode(value[VECTOR_KEY])
    if len(raw) % 4:
        raise SnapshotError("Malformed embedding in snapshot: payload is not a float32 sequence.")
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


# --------------------------------------------------------------------------
# Which payload files the exported rows point at. Pure, so it is testable
# without a database or a populated DATA_DIR/MEDIA_DIR.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PayloadPaths:
    """The `DATA_DIR`- and `MEDIA_DIR`-relative payload paths of a snapshot."""

    data: tuple[str, ...]
    media: tuple[str, ...]


def collect_payload_paths(rows_by_table: Mapping[str, Sequence[Mapping[str, Any]]]) -> PayloadPaths:
    """Derive every payload path referenced by already-encoded rows.

    Image variants are *computed*, not stored: `image_service.variant_path` is
    the single definition of that layout, so a snapshot cannot drift from what
    the API serves.
    """
    data_paths: list[str] = [
        row["raw_path"] for row in rows_by_table.get(SourceDocument.__tablename__, ())
    ]

    media_paths: list[str] = []
    for row in rows_by_table.get(MotorbikeImage.__tablename__, ()):
        media_paths.append(row["original_path"])
        media_paths.extend(
            image_service.variant_path(row["motorbike_id"], row["id"], variant)
            for variant in image_service.VARIANT_WIDTHS
        )
    media_paths.extend(
        row["logo_path"]
        for row in rows_by_table.get(Manufacturer.__tablename__, ())
        if row["logo_path"]
    )

    return PayloadPaths(data=tuple(dict.fromkeys(data_paths)), media=tuple(media_paths))


def _archive_relative(relative_path: str) -> PurePosixPath:
    """Validate an archived payload path and return it as a relative path.

    A snapshot is a file the user may have edited or received; an absolute path
    or a `..` segment in it must never be able to write outside DATA_DIR or
    MEDIA_DIR.
    """
    candidate = PurePosixPath(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SnapshotError(f"Refusing unsafe payload path in snapshot: {relative_path!r}")
    return candidate


# --------------------------------------------------------------------------
# Save
# --------------------------------------------------------------------------


async def save(session: AsyncSession, target: Path) -> SnapshotReport:
    """Write a full catalogue snapshot into `target`, creating it if needed.

    Reads every table in `TABLE_ORDER`, writes one gzipped JSONL file per
    table, then copies the payload files those rows reference. Purely a reader
    of the database.
    """
    report = SnapshotReport()
    rows_by_table: dict[str, list[dict[str, Any]]] = {}

    tables_directory = target / TABLES_DIRECTORY
    tables_directory.mkdir(parents=True, exist_ok=True)

    for table in TABLE_ORDER:
        rows = await _read_table(session, table)
        rows_by_table[table.name] = rows
        _write_jsonl(tables_directory / f"{table.name}.jsonl{GZIP_SUFFIX}", rows)
        report.tables[table.name] = len(rows)
        logger.info("Snapshot: exported %d row(s) from %s.", len(rows), table.name)

    paths = collect_payload_paths(rows_by_table)
    settings = get_settings()
    report.data_files = _copy_out(
        paths.data, settings.data_dir, target / DATA_DIRECTORY, compress=True, report=report
    )
    report.media_files = _copy_out(
        paths.media, settings.media_dir, target / MEDIA_DIRECTORY, compress=False, report=report
    )

    _write_manifest(target, report)
    return report


async def _read_table(session: AsyncSession, table: Table) -> list[dict[str, Any]]:
    """Stream one table in primary-key order and encode every row.

    Streamed rather than fetched whole because `chunks` carries a 1536-float
    embedding per row; PK order makes the archive stable across saves, so a
    re-save of an unchanged catalogue produces no diff.
    """
    columns = exported_columns(table)
    # One extra boolean per JSON column: psycopg cannot distinguish SQL NULL
    # from the JSON literal `null` (both arrive as `None`), so the distinction
    # is asked of PostgreSQL directly. See `encode_row`.
    null_flags = [
        column.is_(None).label(sql_null_label(column.name))
        for column in columns
        if column.name in json_column_names(table)
    ]
    statement = select(*columns, *null_flags).order_by(*table.primary_key.columns)
    result = await session.stream(statement)
    return [encode_row(table, row) async for row in result.mappings()]


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Write `rows` as gzipped JSONL — one compact JSON object per line.

    `mtime=0` keeps the gzip header byte-stable, so re-saving an unchanged
    table does not show up as a change in `git`.
    """
    with gzip.GzipFile(path, "wb", compresslevel=GZIP_LEVEL, mtime=0) as archive:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            archive.write(line.encode("utf-8") + b"\n")


def _copy_out(
    relative_paths: Sequence[str],
    source_root: Path,
    target_root: Path,
    *,
    compress: bool,
    report: SnapshotReport,
) -> int:
    """Copy referenced payloads out of `source_root` into the archive.

    A referenced file that is not on disk is recorded in `report.missing_files`
    and skipped: an image whose download failed, or a payload pruned by hand,
    must not make the whole snapshot unwritable.
    """
    written = 0
    for relative_path in relative_paths:
        source = source_root / _archive_relative(relative_path)
        if not source.is_file():
            report.missing_files.append(relative_path)
            continue
        destination = target_root / relative_path
        if compress:
            destination = destination.with_name(destination.name + GZIP_SUFFIX)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if compress:
            with (
                source.open("rb") as reader,
                gzip.GzipFile(destination, "wb", compresslevel=GZIP_LEVEL, mtime=0) as writer,
            ):
                shutil.copyfileobj(reader, writer)
        else:
            shutil.copyfile(source, destination)
        written += 1
    return written


def _write_manifest(target: Path, report: SnapshotReport) -> None:
    """Record what the archive contains, so a load can verify it up front."""
    settings = get_settings()
    manifest = {
        "snapshot_version": SNAPSHOT_VERSION,
        "created_at": datetime.now().astimezone().isoformat(),
        # Restoring embeddings into a differently-shaped `vector` column would
        # fail row by row; the load checks these two first instead.
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "tables": report.tables,
        "data_files": report.data_files,
        "media_files": report.media_files,
        "missing_files": sorted(report.missing_files),
    }
    (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------


def read_manifest(source: Path) -> dict[str, Any]:
    """Read and validate the archive's manifest before anything is written."""
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SnapshotError(f"No snapshot at {source} (missing {MANIFEST_NAME}).")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as error:
        raise SnapshotError(f"Corrupt {MANIFEST_NAME}: {error}") from error

    version = manifest.get("snapshot_version")
    if version != SNAPSHOT_VERSION:
        raise SnapshotError(
            f"Snapshot format v{version} cannot be read by this build (expects "
            f"v{SNAPSHOT_VERSION})."
        )

    dimensions = manifest.get("embedding_dimensions")
    configured = get_settings().embedding_dimensions
    if dimensions != configured:
        raise SnapshotError(
            f"Snapshot embeddings are {dimensions}-dimensional but this instance is "
            f"configured for {configured}; refusing to load."
        )
    return manifest


async def count_existing(session: AsyncSession) -> dict[str, int]:
    """Return the current row count of every catalogue table that is not empty."""
    counts: dict[str, int] = {}
    for table in TABLE_ORDER:
        total = await session.scalar(select(func.count()).select_from(table))
        if total:
            counts[table.name] = int(total)
    return counts


async def load(session: AsyncSession, source: Path, *, replace: bool) -> SnapshotReport:
    """Restore the snapshot at `source` into the database and onto disk.

    Refuses to run against a non-empty catalogue unless `replace` is set, in
    which case every catalogue row is deleted first — reverse `TABLE_ORDER`, so
    no foreign key is ever left dangling. Tables outside the catalogue
    (`users`, `chats`, `operations`) are never touched.

    One transaction: a failed load leaves the database exactly as it was. The
    payload files are copied *after* the commit, because a half-copied media
    tree only costs a missing picture, while a half-loaded catalogue would be
    incoherent.
    """
    manifest = read_manifest(source)

    existing = await count_existing(session)
    if existing and not replace:
        summary = ", ".join(f"{name}={total}" for name, total in existing.items())
        raise SnapshotError(
            f"The catalogue is not empty ({summary}). Re-run with --replace to delete "
            "these rows and restore the snapshot over them."
        )

    report = SnapshotReport()
    if existing:
        for table in reversed(TABLE_ORDER):
            await session.execute(delete(table))
        logger.info("Snapshot: cleared %d existing catalogue row(s).", sum(existing.values()))

    for table in TABLE_ORDER:
        rows = list(_read_jsonl(source / TABLES_DIRECTORY / f"{table.name}.jsonl{GZIP_SUFFIX}"))
        for group in insert_groups(table, rows):
            for batch in _batched(group, INSERT_BATCH_ROWS):
                await session.execute(table.insert(), list(batch))
        report.tables[table.name] = len(rows)
        logger.info("Snapshot: restored %d row(s) into %s.", len(rows), table.name)

    await session.commit()

    settings = get_settings()
    report.data_files = _copy_in(
        source / DATA_DIRECTORY, settings.data_dir, decompress=True, report=report
    )
    report.media_files = _copy_in(
        source / MEDIA_DIRECTORY, settings.media_dir, decompress=False, report=report
    )

    _warn_on_manifest_drift(manifest, report)
    return report


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the rows of one gzipped JSONL table file."""
    if not path.is_file():
        raise SnapshotError(f"Incomplete snapshot: {path.name} is missing.")
    with gzip.open(path, "rt", encoding="utf-8") as archive:
        for number, line in enumerate(archive, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise SnapshotError(f"Corrupt snapshot: {path.name} line {number}: {error}") from (
                    error
                )


def _batched(rows: Sequence[dict[str, Any]], size: int) -> Iterator[Sequence[dict[str, Any]]]:
    """Split `rows` into chunks of at most `size`."""
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _copy_in(
    source_root: Path,
    target_root: Path,
    *,
    decompress: bool,
    report: SnapshotReport,
) -> int:
    """Copy the archive's payload tree into DATA_DIR or MEDIA_DIR.

    Walks the archive rather than the restored rows, so a payload whose row was
    written by a newer schema still lands. Existing files are overwritten:
    paths are content-addressed by ULID, so the same path always means the same
    payload.
    """
    if not source_root.is_dir():
        return 0

    written = 0
    for source in sorted(source_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(source_root).as_posix()
        if decompress:
            if not relative.endswith(GZIP_SUFFIX):
                report.missing_files.append(relative)
                continue
            relative = relative[: -len(GZIP_SUFFIX)]
        destination = target_root / _archive_relative(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if decompress:
            with gzip.open(source, "rb") as reader, destination.open("wb") as writer:
                shutil.copyfileobj(reader, writer)
        else:
            shutil.copyfile(source, destination)
        written += 1
    return written


def _warn_on_manifest_drift(manifest: Mapping[str, Any], report: SnapshotReport) -> None:
    """Log any disagreement between what the manifest promised and what landed.

    Not an error: the manifest is provenance, and a hand-pruned archive is a
    legitimate thing to restore. But a silent difference would be a trap.
    """
    for name, expected in manifest.get("tables", {}).items():
        actual = report.tables.get(name)
        if actual != expected:
            logger.warning(
                "Snapshot manifest promised %d row(s) in %s but %s were restored.",
                expected,
                name,
                actual,
            )
