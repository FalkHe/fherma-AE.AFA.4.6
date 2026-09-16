from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.modules.srd.errors import SrdCorpusEmptyError, SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule
from app.modules.srd.schemas import CorpusStatus


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
