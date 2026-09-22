import contextlib
import os
import re
import tempfile
from pathlib import Path

import httpx
import tiktoken
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.modules.srd.errors import SrdCorpusEmptyError, SrdSourceError, SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule
from app.modules.srd.schemas import CorpusStatus, RuleChunk

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
    stack. Returns one `(heading_path, body)` pair per heading, where body
    is the raw text between that heading and the next heading of any level
    (not yet stripped of surrounding whitespace)."""
    stack: list[str] = []
    sections: list[tuple[str, list[str]]] = []

    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match is None:
            if sections:
                sections[-1][1].append(line)
            continue

        level = len(match.group(1))
        title = _clean_heading_title(match.group(2))
        stack = stack[: level - 1]
        stack.append(title)
        sections.append((" › ".join(stack), []))

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
