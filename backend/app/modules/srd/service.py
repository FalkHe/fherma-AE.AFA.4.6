import os
import re
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import httpx
import structlog
import tiktoken
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import service as llm_service
from app.core.settings import get_settings
from app.modules.srd.errors import SrdCorpusEmptyError, SrdSourceError, SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule
from app.modules.srd.schemas import CorpusStatus, IngestReport, RuleChunk, RuleMatch

logger = structlog.get_logger()

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


def _restore_previous_source(dest_path: Path, previous_bytes: bytes | None) -> None:
    """Puts the stored SRD source back to how it was before this `ingest`
    call's `fetch_source` replaced it, called once `ingest` has failed
    somewhere after that replacement (AC4): `previous_bytes` byte-for-byte
    when there was a previous file, no file at all (`dest_path` removed)
    when there was not -- a failure must never leave a brand-new file
    behind that no earlier successful ingest ever produced.

    Restored the same temp-file-then-`os.replace` way `fetch_source` stores
    a download, so the restore is itself atomic and never leaves a
    half-written file in its place. Any failure while restoring is logged
    and swallowed rather than raised: the caller is already unwinding a
    real failure (a fetch/embed/db error), and a second, unrelated
    filesystem error here must not replace or hide that original one."""
    try:
        if previous_bytes is None:
            dest_path.unlink(missing_ok=True)
            return

        dest_dir = dest_path.parent
        fd, tmp_name = tempfile.mkstemp(
            dir=dest_dir, prefix=f".{dest_path.name}.", suffix=".restore.tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                tmp_file.write(previous_bytes)
            os.replace(tmp_path, dest_path)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise
    except OSError:
        logger.error("srd_source_restore_failed", dest_path=str(dest_path), exc_info=True)


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


# WI3: a passage's own name lives in its heading, never in its body -- a
# spell's "Casting Time / Range / Components" block reads the same for
# every spell. Joined once, blank-line-separated, ahead of the body it
# names -- the same shape the source markdown itself uses for a heading
# followed by its text -- so the embedder learns the name together with
# what it does, not the body alone (research: "Fire Bolt" ranked 47th
# without it). `SrdRule.text`/`RuleChunk.text` stay body-only throughout;
# this exists only to build what actually goes to `embed_texts`.
EMBED_TRAIL_SEPARATOR = "\n\n"


def _embed_text(heading_path: str, body: str) -> str:
    """The text actually handed to the embedder for one passage: `heading_path`
    joined once to `body` (WI3, see `EMBED_TRAIL_SEPARATOR`)."""
    return f"{heading_path}{EMBED_TRAIL_SEPARATOR}{body}"


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


def _split_section(heading_path: str, body: str, *, start_ordinal: int) -> list[RuleChunk]:
    """One `RuleChunk` per window of `body`, sharing `heading_path` and
    gaining ascending ordinals from `start_ordinal`, each window overlapping
    the previous by (up to) `CHUNK_OVERLAP_TOKENS` tokens so a citation at a
    split boundary still reads in context (AC4). A section within the cap
    yields exactly one chunk.

    `token_count` on every returned chunk is `count_tokens(_embed_text(
    heading_path, chunk.text))` -- what the trail-joined text actually sent
    to `embed_texts` encodes to (WI3), not `chunk.text` alone, so the figure
    stays honest about what gets embedded. A window's own body is therefore
    capped at `MAX_CHUNK_TOKENS` minus the heading trail's own token cost --
    not at `MAX_CHUNK_TOKENS` itself -- so the trail-joined text handed to
    the embedder never exceeds `MAX_CHUNK_TOKENS` either.

    The stride between windows (`step`) is `MAX_CHUNK_TOKENS -
    CHUNK_OVERLAP_TOKENS`, same as before the trail was counted, *unless*
    that would outrun the (now possibly smaller) window: `step` is clamped
    to never exceed `window_cap`, so a window can never start past where the
    previous one ended -- the one outcome that must be impossible is a gap
    that silently drops body text between two windows. Every heading trail
    in the shipped corpus is far short of `CHUNK_OVERLAP_TOKENS` (100)
    tokens, so the clamp never engages there and an already-oversized
    section still splits into exactly as many windows as it did before the
    trail was counted (real corpus regression: still 2,132 passages
    overall) -- it only guards a heading trail long enough to matter.

    `start_ordinal` lets `chunk_source` continue the numbering for a
    `heading_path` that a later markdown section shares -- e.g. two headings
    that collapse to the same anchor-stripped trail -- rather than letting
    every section restart at 0 and risk two passages claiming the same
    citation (AC2)."""
    prefix_tokens = count_tokens(_embed_text(heading_path, ""))
    window_cap = MAX_CHUNK_TOKENS - prefix_tokens
    if window_cap < 1:
        raise SrdSourceError(
            f"heading trail {heading_path!r} alone takes {prefix_tokens} tokens, leaving no "
            f"room for a body chunk under MAX_CHUNK_TOKENS ({MAX_CHUNK_TOKENS})"
        )

    tokens = _encoding().encode(body)
    total = len(tokens)
    if total <= window_cap:
        return [
            RuleChunk(
                heading_path=heading_path,
                ordinal=start_ordinal,
                text=body,
                token_count=count_tokens(_embed_text(heading_path, body)),
            )
        ]

    step = min(MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS, window_cap)
    chunks: list[RuleChunk] = []
    start = 0
    ordinal = start_ordinal
    while start < total:
        end = min(start + window_cap, total)
        window = tokens[start:end]
        window_text = _encoding().decode(window)
        chunks.append(
            RuleChunk(
                heading_path=heading_path,
                ordinal=ordinal,
                text=window_text,
                token_count=count_tokens(_embed_text(heading_path, window_text)),
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

    `ordinal` is the passage's position, from 0, among **all** passages that
    share its `heading_path` across the whole document -- not within one
    markdown section. Two headings that collapse to the same anchor-free
    trail (e.g. `{#fire-bolt}` / `{#fire-bolt-1}`) therefore continue one
    shared sequence instead of each restarting at 0, so `(heading_path,
    ordinal)` stays unique across the returned list by construction (AC2).

    A `path` that cannot be read, or whose bytes are not valid UTF-8 text
    (a damaged stored file, however it got that way), raises
    `SrdSourceError` rather than letting `OSError`/`UnicodeDecodeError`
    escape as a raw traceback (AC5).

    `token_count` on each returned chunk covers what actually gets sent to
    the embedder -- `heading_path` joined to `text`, not `text` alone (WI3,
    see `_split_section`) -- so it stays an honest figure even though `text`
    itself is body-only throughout."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SrdSourceError(f"could not read stored SRD source at {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise SrdSourceError(f"stored SRD source at {path} is not valid UTF-8 text: {exc}") from exc
    chunks: list[RuleChunk] = []
    next_ordinal: dict[str, int] = {}
    for heading_path, body in _sections(text):
        if not body:
            continue
        start_ordinal = next_ordinal.get(heading_path, 0)
        section_chunks = _split_section(heading_path, body, start_ordinal=start_ordinal)
        next_ordinal[heading_path] = start_ordinal + len(section_chunks)
        chunks.extend(section_chunks)
    return chunks


# The gateway's own per-request cap is 300,000 tokens; the text actually
# embedded per chunk -- heading trail joined to body (WI3) -- still caps at
# `MAX_CHUNK_TOKENS` (800), so 256 * 800 = 204,800 stays comfortably under it
# while 512 would not (decisions, "Decisions already made for you"). The
# shipped corpus -- 2,132 chunks / 529,572 tokens once the trail is counted
# -- takes 9 requests at this size.
EMBED_BATCH_SIZE = 256


async def ingest(
    db: AsyncSession,
    *,
    version: str = SOURCE_VERSION,
    on_batch: Callable[[int, int], None] | None = None,
) -> IngestReport:
    """Fetches, stores, chunks, embeds and stores the SRD corpus, replacing
    it wholesale (`module-structure.md` §2, §6).

    Checks the embedding width first (AC3): a mismatch between
    `EMBEDDING_DIMENSIONS` and the `srd_rules.embedding` column raises
    `SrdVectorWidthError` before `fetch_source` runs, so a misconfiguration
    never spends a gateway request. Every chunk is embedded, in
    `EMBED_BATCH_SIZE`-sized batches (each safely under the gateway's
    per-request token cap), before any row is written: `llm_service.
    embed_texts` is called attribute-style so tests can monkeypatch it, and
    its `LlmError` travels out unwrapped -- the write below never runs when
    a batch fails, so the corpus is left exactly as it was, never half-filled
    (AC4). `on_batch(chunks_done, chunks_total)` fires after each batch
    completes, for a caller that wants progress; this function itself never
    prints -- that is the command's job.

    What is actually sent to `embed_texts` is `_embed_text(chunk.heading_path,
    chunk.text)` -- the passage's heading trail joined to its body (WI3), not
    `chunk.text` alone: a spell's own name lives in its heading, never in its
    body, so leaving the trail out of what gets embedded makes every spell's
    "Casting Time / Range / Components" block embed as an interchangeable
    match for every other spell. The stored row's own `text` (below) stays
    `chunk.text` -- body only -- unchanged: that is what a citation quotes
    back, and it must never carry the heading a second time.

    The write is one short transaction: delete every existing row, insert
    the newly embedded ones, commit. It is never opened until every vector
    is already in hand, so it is never held across a gateway call -- that
    would pin a database connection for the ~minute a full embed run takes,
    for no benefit (← decisions). A failure during the write rolls the
    transaction back before the exception is re-raised, so a failed write
    leaves the previous corpus untouched rather than half-replaced.

    `cost_usd` on the returned report is the sum of every batch's reported
    cost, whether or not every batch actually reported one; `cost_complete`
    is `False` when the gateway priced only some of the batches, so
    `cost_usd` is a known lower bound rather than the true total -- the
    operator still sees "it cost at least this much" instead of nothing.
    `cost_usd` is `None` only when no batch reported a cost at all (there is
    then genuinely no figure to show), in which case `cost_complete` stays
    at its default `True`: nothing was left out of an empty sum.

    `fetch_source` already stores the new source atomically and leaves an
    existing stored copy untouched on its own failure (AC5); the window
    this function still has to guard is the one *after* that store
    succeeds -- if chunking, embedding or the write below then fails, the
    stored file would otherwise be the changed upstream source while the
    corpus still serves the old one. So a failure anywhere in that window
    restores the file `fetch_source` replaced back to what it held before
    this call, byte-for-byte, before the exception is re-raised -- no file
    at all when there was none to begin with (AC4). Caught as `BaseException`,
    not `Exception`: an operator's `KeyboardInterrupt` partway through a
    minute-long embed run must restore the file exactly like any other
    failure here, not skip it because it is not an `Exception` subclass.
    """
    check_vector_width()

    dest_path = SRD_ROOT / version / SOURCE_FILENAME
    previous_source_bytes = dest_path.read_bytes() if dest_path.exists() else None

    path = fetch_source(version=version)

    try:
        chunks = chunk_source(path)

        embedding_model = get_settings().embedding_model
        total = len(chunks)

        vectors: list[list[float]] = []
        cost_total = 0.0
        any_batch_priced = False
        any_batch_unpriced = False

        for start in range(0, total, EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            texts = [_embed_text(chunk.heading_path, chunk.text) for chunk in batch]
            result = llm_service.embed_texts(texts, model=embedding_model)
            vectors.extend(result.vectors)
            if result.usage.cost_usd is None:
                any_batch_unpriced = True
            else:
                cost_total += result.usage.cost_usd
                any_batch_priced = True
            if on_batch is not None:
                on_batch(len(vectors), total)

        # Incomplete only in the mixed case: some batches priced, some did
        # not. All-priced and none-priced both leave `cost_usd` telling the
        # whole story it can (a full sum, or nothing), so neither counts as
        # partial.
        cost_complete = not (any_batch_priced and any_batch_unpriced)

        rows = [
            SrdRule(
                source_version=version,
                heading_path=chunk.heading_path,
                ordinal=chunk.ordinal,
                text=chunk.text,
                token_count=chunk.token_count,
                embedding_model=embedding_model,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        try:
            await db.execute(delete(SrdRule))
            db.add_all(rows)
            await db.commit()
        except BaseException:
            await db.rollback()
            raise
    except BaseException:
        # `BaseException`, not `Exception`: a `KeyboardInterrupt` during a
        # minute-long embed run is a real operator action, not a
        # hypothetical, and it must restore the file exactly like any
        # other failure in this window (AC4) -- `_restore_previous_source`
        # itself only ever swallows its own `OSError`, so the interrupt
        # (or any other exception) still propagates unchanged below.
        _restore_previous_source(dest_path, previous_source_bytes)
        raise

    return IngestReport(
        source_version=version,
        source_bytes=path.stat().st_size,
        chunk_count=total,
        token_count=sum(chunk.token_count for chunk in chunks),
        cost_usd=cost_total if any_batch_priced else None,
        cost_complete=cost_complete,
    )


DEFAULT_LIMIT = 5


async def search_rules(
    db: AsyncSession, query: str, *, limit: int = DEFAULT_LIMIT
) -> list[RuleMatch]:
    """Answers `query` with the `limit` closest `SrdRule` passages, best
    first (AC2, AC5).

    `require_corpus` runs first, so an empty corpus raises
    `SrdCorpusEmptyError` before `query` is ever sent to the embedding
    gateway -- an empty corpus can never usefully answer anything, and a
    spent gateway call for it would be pure waste (AC6). `query` is then
    embedded through `llm_service.embed_texts`, called attribute-style
    (`from app.core.llm import service as llm_service`, then
    `llm_service.embed_texts(...)`) so tests can monkeypatch it, same as
    `ingest` above.

    The nearest-neighbour query orders by `SrdRule.embedding.
    cosine_distance(vector)` *with* the `LIMIT` applied in the same
    statement -- that combination is what lets Postgres use the `hnsw`
    index (`ix_srd_rules_embedding`) instead of a full sequential scan plus
    sort (research.md); the distance expression is selected alongside each
    row, once, so it does not have to be recomputed to derive `score`.
    `score = 1 - cosine_distance`: higher is a closer match. No relevance
    floor is applied here -- that is sprint 06's job; this returns whatever
    the `limit` gives back, in similarity order.
    """
    await require_corpus(db)

    embedding_model = get_settings().embedding_model
    embedded = llm_service.embed_texts([query], model=embedding_model)
    query_vector = embedded.vectors[0]

    distance = SrdRule.embedding.cosine_distance(query_vector).label("distance")
    result = await db.execute(select(SrdRule, distance).order_by(distance).limit(limit))

    return [
        RuleMatch(
            heading_path=rule.heading_path,
            ordinal=rule.ordinal,
            text=rule.text,
            score=1 - rule_distance,
        )
        for rule, rule_distance in result.all()
    ]
