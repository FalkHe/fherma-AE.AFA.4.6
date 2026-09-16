"""WI2: corpus status reporting, the non-empty-corpus guard, and the
vector-width fail-fast check (AC3, AC4). Engine-free: `db` is a bare stub
whose `scalar()` is queued with the values the query would have returned,
per `backend/tests/conftest.py`'s ban on a real engine and the absence of
pytest-asyncio."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.core.settings import get_settings
from app.modules.srd import service
from app.modules.srd.errors import SrdCorpusEmptyError, SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH


@pytest.fixture
def embedding_width(monkeypatch):
    """Sets `settings.embedding_dimensions` for one test and restores the
    cached settings afterwards. The suite-wide pin in `tests/conftest.py`
    (width 4) never exercises the matching-width path on its own, so tests
    that need the widths to agree must set this explicitly."""

    def _set(value: int) -> None:
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", str(value))
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


class FakeScalarSession:
    """Stands in for `AsyncSession`: `corpus_status`/`require_corpus` only
    ever call `db.scalar(...)`, so this returns the queued values in order
    and records how many calls were made."""

    def __init__(self, *values):
        self._values = list(values)
        self.calls = 0

    async def scalar(self, _stmt):
        self.calls += 1
        return self._values.pop(0)


class _FakeRule:
    def __init__(self, source_version, embedding_model, created_at):
        self.source_version = source_version
        self.embedding_model = embedding_model
        self.created_at = created_at


def test_matching_widths_are_silent(embedding_width):
    embedding_width(EMBEDDING_WIDTH)

    assert service.check_vector_width() is None


def test_mismatched_width_names_both_widths(embedding_width):
    embedding_width(4)

    with pytest.raises(SrdVectorWidthError) as excinfo:
        service.check_vector_width()

    message = str(excinfo.value)
    assert "4" in message
    assert str(EMBEDDING_WIDTH) in message


def test_corpus_status_on_empty_corpus_reports_zero_and_no_source(embedding_width):
    embedding_width(EMBEDDING_WIDTH)
    db = FakeScalarSession(0)

    status = asyncio.run(service.corpus_status(db))

    assert status.rule_count == 0
    assert status.source_version is None
    assert status.embedding_model is None
    assert status.ingested_at is None


def test_corpus_status_on_populated_corpus_reports_the_latest_ingest(embedding_width):
    embedding_width(EMBEDDING_WIDTH)
    ingested_at = datetime(2026, 1, 1, tzinfo=UTC)
    db = FakeScalarSession(3, _FakeRule("v1", "test/embedding-model", ingested_at))

    status = asyncio.run(service.corpus_status(db))

    assert status.rule_count == 3
    assert status.source_version == "v1"
    assert status.embedding_model == "test/embedding-model"
    assert status.ingested_at == ingested_at


def test_corpus_status_checks_vector_width_before_querying(embedding_width):
    embedding_width(4)
    db = FakeScalarSession()

    with pytest.raises(SrdVectorWidthError):
        asyncio.run(service.corpus_status(db))

    assert db.calls == 0


def test_require_corpus_raises_on_empty_corpus():
    db = FakeScalarSession(0)

    with pytest.raises(SrdCorpusEmptyError):
        asyncio.run(service.require_corpus(db))


def test_require_corpus_returns_none_when_rows_exist():
    db = FakeScalarSession(3)

    assert asyncio.run(service.require_corpus(db)) is None
