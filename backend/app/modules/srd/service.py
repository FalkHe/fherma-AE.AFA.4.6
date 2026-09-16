import os
import tempfile
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.modules.srd.errors import SrdCorpusEmptyError, SrdSourceError, SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule
from app.modules.srd.schemas import CorpusStatus

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
    failure or an empty body, and never touches the destination file until
    a full, valid body is in hand: the download is written to a temporary
    file in the destination directory first, then moved into place with
    `os.replace`, so a failed fetch leaves an existing stored copy
    byte-identical (AC5)."""
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
        os.replace(tmp_path, dest_path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise SrdSourceError(f"could not store SRD source at {dest_path}: {exc}") from exc

    return dest_path
