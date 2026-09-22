import asyncio
import contextlib
import os
import re
import tempfile
from collections.abc import Callable
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

# `content/srd/` sits alongside `content/campaigns/` (see
# `modules/content/service.py`'s `CONTENT_ROOT`), one level up from
# `content/srd/<version>/` -- fetched sources are versioned so a future
# SRD revision does not overwrite this one in place.
SRD_ROOT: Path = Path(__file__).resolve().parents[3] / "content" / "srd"

SOURCE_URL: str = "https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md"
SOURCE_VERSION: str = "v1"
SOURCE_FILENAME: str = "SRD_CC_v5.1.md"

# A chunk this size comfortably fits a retrieval prompt's context budget;
# the overlap keeps a rule that straddles a split boundary findable from
# either side of it.
MAX_CHUNK_TOKENS: int = 1000
CHUNK_OVERLAP_TOKENS: int = 100

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_ANCHOR_RE = re.compile(r"\{#[^}]*\}")

_encoding: tiktoken.Encoding | None = None


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


def build_http_client() -> httpx.Client:
    """Module-level so tests can monkeypatch `service.build_http_client` to
    return one wired to `httpx.MockTransport` -- the injection seam for a
    non-2xx response or a transport failure, per `core/llm/service.py`'s
    `build_sdk_client` precedent."""
    return httpx.Client(timeout=30.0)


def fetch_source(*, version: str = SOURCE_VERSION) -> Path:
    """Download `SOURCE_URL` and write it to `SRD_ROOT/<version>/SOURCE_FILENAME`,
    overwriting whatever was there. Written atomically (temp file in the
    same directory, then `os.replace`) so a failed fetch -- unreachable
    host, non-2xx response, or an unwritable target -- leaves an existing
    file byte-identical rather than half-written."""
    target_dir = SRD_ROOT / version
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / SOURCE_FILENAME

    client = build_http_client()
    try:
        response = client.get(SOURCE_URL)
    except httpx.HTTPError as exc:
        raise SrdSourceError(f"unable to reach {SOURCE_URL}: {exc}") from exc
    finally:
        client.close()

    if response.status_code // 100 != 2:
        raise SrdSourceError(f"{SOURCE_URL} responded with status {response.status_code}")

    tmp_name: str | None = None
    try:
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=target_dir, prefix=f".{SOURCE_FILENAME}.", suffix=".tmp"
        )
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(response.content)
        os.replace(tmp_name, target)
    except OSError as exc:
        if tmp_name is not None:
            with contextlib.suppress(OSError):
                os.remove(tmp_name)
        raise SrdSourceError(f"unable to write {target}: {exc}") from exc

    return target


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    """`cl100k_base` token count. The encoding is loaded lazily (first call
    only) and cached module-wide; module-level so tests can monkeypatch
    `service.count_tokens` to a cheap stand-in and never trigger tiktoken's
    BPE download."""
    return len(_get_encoding().encode(text))


def _clean_heading_title(raw: str) -> str:
    return _ANCHOR_RE.sub("", raw).strip()


def _parse_sections(markdown: str) -> list[tuple[str, str]]:
    """Walk `#`..`####` headings in document order with an open heading
    stack. The stack closes by heading level -- pushing a heading pops every
    open entry at or below its level first -- so a source that skips levels
    (e.g. `##` followed directly by `####`) still yields siblings instead of
    nesting later siblings under the first one. Returns one
    `(heading_path, body)` pair per heading, where body is the raw text
    between that heading and the next heading of any level (not yet
    stripped of surrounding whitespace)."""
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = []

    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match is None:
            if sections:
                sections[-1][1].append(line)
            continue

        level = len(match.group(1))
        title = _clean_heading_title(match.group(2))
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        sections.append((" › ".join(t for _, t in stack), []))

    return [(heading_path, "\n".join(body_lines)) for heading_path, body_lines in sections]


def _greedy_piece_end(words: list[str], start: int, limit: int) -> int:
    """Largest `end` such that `" ".join(words[start:end])` counts at most
    `limit` tokens, found by binary search so splitting a large section
    costs O(log n) token counts per piece rather than one per word."""
    n = len(words)
    lo, hi = start + 1, n
    best = start + 1  # a single word always stays, even if it alone exceeds limit
    while lo <= hi:
        mid = (lo + hi) // 2
        if count_tokens(" ".join(words[start:mid])) <= limit:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _overlap_start(words: list[str], floor: int, end: int, limit: int) -> int:
    """Smallest start (no lower than `floor`) such that the words up to
    `end` count at most `limit` tokens -- the start of the next piece,
    repeating the tail of this one."""
    lo, hi = floor, end - 1
    best = end
    while lo <= hi:
        mid = (lo + hi) // 2
        if count_tokens(" ".join(words[mid:end])) <= limit:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return best


def _split_body(body: str) -> list[str]:
    """One chunk when `body` already fits `MAX_CHUNK_TOKENS`; otherwise a
    sequence of pieces, each at most `MAX_CHUNK_TOKENS` tokens, where every
    piece after the first repeats the last `CHUNK_OVERLAP_TOKENS` tokens of
    the previous one."""
    if count_tokens(body) <= MAX_CHUNK_TOKENS:
        return [body]

    words = body.split()
    n = len(words)
    pieces: list[str] = []
    start = 0
    while start < n:
        end = _greedy_piece_end(words, start, MAX_CHUNK_TOKENS)
        pieces.append(" ".join(words[start:end]))
        if end >= n:
            break
        next_start = _overlap_start(words, start, end, CHUNK_OVERLAP_TOKENS)
        # Guarantee forward progress even for a degenerate (e.g. tiny
        # monkeypatched) overlap limit that would otherwise repeat `start`.
        start = next_start if next_start > start else end
    return pieces


def chunk_source(path: Path) -> list[RuleChunk]:
    """Split the SRD source markdown at `path` into citable `RuleChunk`s,
    one per heading-path section (further split when oversized). Raises
    `SrdSourceError` when the file cannot be read or holds no `#`..`####`
    heading at all."""
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SrdSourceError(f"unable to read {path}: {exc}") from exc

    sections = _parse_sections(markdown)
    if not sections:
        raise SrdSourceError(f"{path} contains no markdown headings to chunk")

    chunks: list[RuleChunk] = []
    for heading_path, raw_body in sections:
        body = raw_body.strip()
        if not body:
            continue
        for ordinal, piece in enumerate(_split_body(body)):
            chunks.append(
                RuleChunk(
                    heading_path=heading_path,
                    ordinal=ordinal,
                    text=piece,
                    token_count=count_tokens(piece),
                )
            )
    return chunks


def _restore_previous_source(dest_path: Path, previous_bytes: bytes | None) -> None:
    """Puts the stored SRD source back to how it was before this `ingest`
    call's `fetch_source` replaced it: byte-for-byte when there was a
    previous file, removed entirely when there was not. A failure here is
    logged and swallowed, never raised -- the caller is already unwinding a
    real failure (a fetch/embed/db error) and a second, unrelated
    filesystem error must not replace or hide that original one."""
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


# The gateway's own per-request cap is 300,000 tokens; a chunk caps at
# `MAX_CHUNK_TOKENS` (1000), so 256 * 1000 = 256,000 stays comfortably
# under it.
EMBED_BATCH_SIZE = 256


async def ingest(
    db: AsyncSession,
    *,
    version: str = SOURCE_VERSION,
    on_batch: Callable[[int, int], None] | None = None,
) -> IngestReport:
    """Fetches, stores, chunks, embeds and stores the SRD corpus, replacing
    it wholesale.

    Checks the embedding width first (AC3), before `fetch_source` spends a
    gateway request. Every chunk is embedded, in `EMBED_BATCH_SIZE`-sized
    batches, before any row is written -- `llm_service.embed_texts` is
    called attribute-style so tests can monkeypatch it, and its `LlmError`
    travels out unwrapped, so the write never runs when a batch fails.
    `on_batch(chunks_done, chunks_total)` fires after each batch, for a
    caller that wants progress; this function itself never prints.

    The write is one short transaction: delete every existing row, insert
    the newly embedded ones, commit -- never opened until every vector is
    in hand, so it is never held across a gateway call. A failure during
    the write rolls back before the exception is re-raised.

    `cost_usd` sums every batch's reported cost; `cost_complete` is `False`
    when the gateway priced only some of the batches (a known lower bound,
    not the true total). `cost_usd` is `None` only when no batch reported a
    cost at all.

    `fetch_source` already leaves an existing stored copy untouched on its
    own failure; the window this function still has to guard is the one
    *after* that store succeeds -- a failure in chunking, embedding or the
    write below restores the file back to what it held before this call,
    byte-for-byte (no file at all when there was none), before the
    exception is re-raised. Caught as `BaseException`, not `Exception`: an
    operator's `KeyboardInterrupt` partway through a minute-long embed run
    must restore the file exactly like any other failure here.
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
            result = llm_service.embed_texts(
                [f"{chunk.heading_path}\n\n{chunk.text}" for chunk in batch],
                model=embedding_model,
            )
            vectors.extend(result.vectors)
            if result.usage.cost_usd is None:
                any_batch_unpriced = True
            else:
                cost_total += result.usage.cost_usd
                any_batch_priced = True
            if on_batch is not None:
                on_batch(len(vectors), total)

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


# A handful of passages, best first, is enough context for a DM's
# narration or rules check; callers that need more can pass `limit`.
DEFAULT_LIMIT = 5

# Measured against the real ingested corpus (openai/text-embedding-3-small,
# 1,750 rules, heading trail + body embedded, sprint 06 measurement table
# in README.md "Relevance floor"): the worst in-corpus best-match distance
# was 0.515 ("how does half cover work"), the best out-of-corpus best-match
# distance was 0.686 ("how do I reload a plasma rifle"). 0.60 sits in that
# gap with a 0.085 margin on both sides -- every measured in-corpus
# question stays answered, every measured out-of-corpus one is rejected.
# `score` is a cosine DISTANCE (lower is closer), so this is a MAXIMUM: a
# row with `distance > RELEVANCE_FLOOR` is not a relevant match.
RELEVANCE_FLOOR: float = 0.60


async def search_rules(
    db: AsyncSession, query: str, *, limit: int = DEFAULT_LIMIT
) -> list[RuleMatch]:
    """Answers `query` with up to `limit` closest `SrdRule` passages, best
    (closest) first, every one of them at or below `RELEVANCE_FLOOR`
    (AC2, AC4, AC5).

    Checks the embedding width first (AC3), then `require_corpus` -- an
    empty corpus raises `SrdCorpusEmptyError` before `query` is ever sent
    to the embedding gateway, so a spent gateway call for an unusable
    corpus never happens (AC6). `query` is embedded through
    `llm_service.embed_texts`, called attribute-style
    (`llm_service.embed_texts(...)`) so tests can monkeypatch it, run off
    the event loop via `asyncio.to_thread` since the call is blocking, same
    as `recall` (`playthrough/service.py`).

    The nearest-neighbour query orders by `SrdRule.embedding.
    cosine_distance(vector)` *with* the `LIMIT` applied in the same
    statement -- that combination is what lets Postgres use the `hnsw`
    index (`ix_srd_rules_embedding`) instead of a full sequential scan plus
    sort; the distance expression is selected alongside each row, once, so
    it does not have to be recomputed to derive `score`. `score` is the raw
    cosine distance (pgvector's `<=>`), 0..2, lower is closer.

    `RELEVANCE_FLOOR` is applied *after* that query returns, in Python, on
    the already-ordered, already-limited rows -- never as a SQL `WHERE` on
    the distance, so the `LIMIT`+`ORDER BY` combination above still lets
    the planner reach for the HNSW index instead of falling back to a
    sequential scan plus sort. A row past the floor is dropped outright,
    never returned with a warning and never as a best effort (AC4): a
    query whose every match falls past the floor returns an empty list,
    not a lower-confidence guess.

    Consequence of filtering after the `LIMIT` rather than before it:
    `limit` (`DEFAULT_LIMIT` when the caller does not pass one) caps what
    *may* come back, not a count of what *will* -- some, or all, of the
    `limit` rows the query fetched can still fall past the floor and be
    dropped, and the result can be shorter than `limit`, including empty.
    Nothing commits; errors travel unwrapped.
    """
    check_vector_width()
    await require_corpus(db)

    embedding_model = get_settings().embedding_model
    embedded = await asyncio.to_thread(llm_service.embed_texts, [query], model=embedding_model)
    query_vector = embedded.vectors[0]

    distance = SrdRule.embedding.cosine_distance(query_vector).label("distance")
    result = await db.execute(
        select(SrdRule.heading_path, SrdRule.ordinal, SrdRule.text, distance)
        .order_by(distance)
        .limit(limit)
    )

    matches = [
        RuleMatch(heading_path=heading_path, ordinal=ordinal, text=text, score=rule_distance)
        for heading_path, ordinal, text, rule_distance in result.all()
    ]
    return [match for match in matches if match.score <= RELEVANCE_FLOOR]
