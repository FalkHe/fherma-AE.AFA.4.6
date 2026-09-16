import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path

import httpx
import tiktoken
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.modules.srd.errors import SrdCorpusEmptyError, SrdSourceError, SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule
from app.modules.srd.schemas import CorpusStatus, RuleChunk

SRD_ROOT: Path = Path(__file__).resolve().parents[3] / "content" / "srd"
SOURCE_URL = "https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md"
SOURCE_VERSION = "v1"
SOURCE_FILENAME = "SRD_CC_v5.1.md"

_FETCH_TIMEOUT_SECONDS = 30.0


def check_vector_width() -> None:
    """Compares the configured embedding width against the width the
    `srd_rules.embedding` column was migrated with, and fails before any
    query touches the table rather than truncating or padding a vector that
    does not fit (AC3)."""
    configured = get_settings().embedding_dimensions
    if configured != EMBEDDING_WIDTH:
        raise SrdVectorWidthError(
            f"configured embedding width {configured} does not match the "
            f"srd_rules column width {EMBEDDING_WIDTH}"
        )


async def corpus_status(db: AsyncSession) -> CorpusStatus:
    """What is currently ingested. Checks the vector width first (← D5,
    AC3), so a misconfigured width is reported before any row is read."""
    check_vector_width()

    rule_count = await db.scalar(select(func.count()).select_from(SrdRule))
    rule_count = rule_count or 0
    if rule_count == 0:
        return CorpusStatus(
            rule_count=0, source_version=None, embedding_model=None, ingested_at=None
        )

    latest = await db.scalar(select(SrdRule).order_by(SrdRule.created_at.desc()).limit(1))
    return CorpusStatus(
        rule_count=rule_count,
        source_version=latest.source_version,
        embedding_model=latest.embedding_model,
        ingested_at=latest.created_at,
    )


async def require_corpus(db: AsyncSession) -> None:
    """Guards any caller that needs a non-empty corpus (e.g. playthrough
    creation, ← D5). Raises `SrdCorpusEmptyError` when the corpus holds no
    rows, returns `None` otherwise (AC4)."""
    rule_count = await db.scalar(select(func.count()).select_from(SrdRule))
    if not rule_count:
        raise SrdCorpusEmptyError("the SRD corpus holds no rules; run `app srd ingest` first")


def fetch_source(*, version: str = SOURCE_VERSION) -> Path:
    """Downloads the SRD source document and stores it at
    `SRD_ROOT/<version>/SOURCE_FILENAME`, overwriting whatever was there
    (AC3). Called through the module reference (`from app.modules.srd import
    service`, then `service.fetch_source(...)`) so tests can monkeypatch
    `service.httpx` at the network boundary, same as `build_sdk_client` in
    `core/llm/service.py`.

    Raises `SrdSourceError` on a non-200 response, a timeout/connection
    failure, an empty body, or a body that does not parse into at least one
    citable rules section -- and never touches the destination file until a
    full, valid, chunkable body is in hand: the download is written to a
    temporary file in the destination directory first, checked by running
    it through `chunk_source` (the same parser `ingest` would use), and only
    then moved into place with `os.replace`. A failed fetch, at any of
    these stages, leaves an existing stored copy byte-identical (AC5)."""
    try:
        response = httpx.get(SOURCE_URL, timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=True)
    except Exception as exc:
        raise SrdSourceError(f"could not reach SRD source {SOURCE_URL}: {exc}") from exc

    if response.status_code != 200:
        raise SrdSourceError(f"SRD source {SOURCE_URL} returned status {response.status_code}")

    content = response.content
    if not content:
        raise SrdSourceError(f"SRD source {SOURCE_URL} returned an empty body")

    dest_dir = SRD_ROOT / version
    dest_path = dest_dir / SOURCE_FILENAME
    dest_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=dest_dir, prefix=f".{SOURCE_FILENAME}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(content)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise SrdSourceError(f"could not store SRD source at {dest_path}: {exc}") from exc

    try:
        chunks = chunk_source(tmp_path)
    except SrdSourceError:
        tmp_path.unlink(missing_ok=True)
        raise

    if not chunks:
        tmp_path.unlink(missing_ok=True)
        raise SrdSourceError(
            f"SRD source {SOURCE_URL} does not parse into any citable rules section "
            "-- the body is not a usable rules document"
        )

    try:
        os.replace(tmp_path, dest_path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise SrdSourceError(f"could not store SRD source at {dest_path}: {exc}") from exc

    return dest_path


# `text-embedding-3-small` (the default `EMBEDDING_MODEL`) resolves to the
# `cl100k_base` BPE encoding (research.md, "`tiktoken` is not a dependency").
# `EMBEDDING_WINDOW_TOKENS` is the model's own input limit; `MAX_CHUNK_TOKENS`
# is deliberately far below it so an oversized section actually splits and
# citations stay short enough to be useful (research.md, "Consequence for
# AC4" -- do not raise this toward the window).
EMBEDDING_WINDOW_TOKENS = 8192
MAX_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 100

_ENCODING_NAME = "cl100k_base"

# A markdown ATX heading, level 1-6, e.g. "## Cover" or "### Half Cover {#half-cover}".
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# The `{#anchor}` suffix some headings carry, stripped so the citable path
# never leaks markdown syntax (124 headings in the shipped document).
_ANCHOR_SUFFIX_RE = re.compile(r"\s*\{#[^}]*\}\s*$")

HEADING_PATH_SEPARATOR = " › "


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """Loads the `cl100k_base` BPE table once per process. `tiktoken` would
    otherwise download it over HTTPS on first use; the image pre-warms
    `TIKTOKEN_CACHE_DIR` at build time (`docker/backend.Dockerfile`) so this
    never touches the network at test or run time."""
    return tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text: str) -> int:
    """How many `cl100k_base` tokens `text` encodes to -- the unit both
    `MAX_CHUNK_TOKENS` and `EMBEDDING_WINDOW_TOKENS` are measured in."""
    return len(_encoding().encode(text))


def _clean_heading_text(raw: str) -> str:
    """Strips a trailing `{#anchor}` suffix so the citable heading path
    never carries markdown-anchor syntax (AC2)."""
    return _ANCHOR_SUFFIX_RE.sub("", raw).strip()


def _sections(text: str) -> list[tuple[str, str]]:
    """Splits `text` into `(heading_path, body)` pairs, one per markdown
    heading in document order. `heading_path` is the ` › `-joined trail of
    headings the line sits under, anchor-free (AC2); `body` is the raw text
    directly under that heading, up to (not including) the next heading at
    any level, stripped of leading/trailing blank lines. Text before the
    first heading has no heading path to carry and is discarded."""
    stack: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_body: list[str] | None = None

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            heading_text = _clean_heading_text(match.group(2))
            stack = [*stack[: level - 1], heading_text]
            current_body = []
            sections.append((HEADING_PATH_SEPARATOR.join(stack), current_body))
            continue
        if current_body is not None:
            current_body.append(line)

    return [(heading_path, "\n".join(body_lines).strip()) for heading_path, body_lines in sections]


def _split_section(heading_path: str, body: str) -> list[RuleChunk]:
    """One `RuleChunk` per `MAX_CHUNK_TOKENS`-token window of `body`, sharing
    `heading_path` and gaining ascending ordinals from 0, each window
    overlapping the previous by `CHUNK_OVERLAP_TOKENS` tokens so a citation
    at a split boundary still reads in context (AC4). A section within the
    cap yields exactly one chunk."""
    tokens = _encoding().encode(body)
    total = len(tokens)
    if total <= MAX_CHUNK_TOKENS:
        return [RuleChunk(heading_path=heading_path, ordinal=0, text=body, token_count=total)]

    step = MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS
    chunks: list[RuleChunk] = []
    start = 0
    ordinal = 0
    while start < total:
        end = min(start + MAX_CHUNK_TOKENS, total)
        window = tokens[start:end]
        chunks.append(
            RuleChunk(
                heading_path=heading_path,
                ordinal=ordinal,
                text=_encoding().decode(window),
                token_count=len(window),
            )
        )
        if end == total:
            break
        ordinal += 1
        start += step

    return chunks


def chunk_source(path: Path) -> list[RuleChunk]:
    """Reads the stored SRD document at `path` and splits it into citable
    `RuleChunk`s: one per heading section, further split on token
    boundaries when a section exceeds `MAX_CHUNK_TOKENS` (AC2, AC4). A
    heading with no body text (72 of them in the shipped document) yields
    no chunk -- an empty citation would not be usable; merging it into a
    neighbour would blur which heading the text actually belongs to
    (research.md, "Open questions").

    A `path` that cannot be read, or whose bytes are not valid UTF-8 text
    (a damaged stored file, however it got that way), raises
    `SrdSourceError` rather than letting `OSError`/`UnicodeDecodeError`
    escape as a raw traceback (AC5)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SrdSourceError(f"could not read stored SRD source at {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SrdSourceError(f"stored SRD source at {path} is not valid UTF-8 text: {exc}") from exc
    chunks: list[RuleChunk] = []
    for heading_path, body in _sections(text):
        if not body:
            continue
        chunks.extend(_split_section(heading_path, body))
    return chunks
