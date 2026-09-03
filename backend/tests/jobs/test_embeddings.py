"""`embeddings.rebuild` — the operation lifecycle of a catalogue-wide re-embed.

Neither Redis nor PostgreSQL nor OpenRouter is involved: the task's session
factory is replaced with the in-memory `FakeAsyncSession`, the embeddings client
with a stub, and the decorated task is called directly (taskiq's decorator keeps
the original coroutine callable). What is under test is the job's own
contract — start, progress in documents processed, and which outcome closes the
operation how.
"""

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.config import get_settings
from app.db.models.chunk import Chunk
from app.db.models.operation import Operation, OperationStatus
from app.db.models.source_document import SourceType
from app.jobs import embeddings as job
from app.llm import embeddings as llm_embeddings
from app.llm.models import MissingApiKeyError
from app.services import document_service, embedding_service, operation_service, product_service
from tests.services.conftest import FakeAsyncSession

FETCHED_AT = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)

ARTICLE = "# Suzuki GSR600\n\nA naked motorcycle.\n"


class StubEmbeddings:
    """Answers every batch with correctly sized vectors."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[0.25] * get_settings().embedding_dimensions for _ in texts]


class WorkerSession(FakeAsyncSession):
    """The fake session plus the `rollback` a worker calls before bookkeeping.

    Nothing is undone: every service commits its own writes, so a failed task
    has no open transaction to discard — the call only has to exist.
    """

    async def rollback(self) -> None:
        pass


class _Sessionmaker:
    """Hands the task the one fake session, as an async context manager."""

    def __init__(self, session: FakeAsyncSession) -> None:
        self.session = session

    def __call__(self) -> "_Sessionmaker":
        return self

    async def __aenter__(self) -> FakeAsyncSession:
        return self.session

    async def __aexit__(self, *_exception: Any) -> bool:
        return False


@pytest.fixture
def fake_session() -> WorkerSession:
    """The service tests' in-memory session; their conftest is out of scope here."""
    return WorkerSession()


@pytest.fixture(autouse=True)
def worker_session(fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the task its session without a database."""
    monkeypatch.setattr(job, "get_sessionmaker", lambda: _Sessionmaker(fake_session))


@pytest.fixture
def stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> StubEmbeddings:
    client = StubEmbeddings()
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: client)
    return client


@pytest.fixture
def settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Return a setter for the settings the embedding service reads."""

    def override(**environment: object) -> None:
        for key, value in environment.items():
            monkeypatch.setenv(key, str(value))
        get_settings.cache_clear()

    yield override
    get_settings.cache_clear()


@pytest.fixture
def milestones(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Record every `(progress, message)` the job reports, in order."""
    recorded: list[tuple[int, str]] = []
    real_advance = operation_service.advance

    async def spy(session: Any, operation: Operation, progress: int, message: str | None = None):
        recorded.append((progress, message or ""))
        return await real_advance(session, operation, progress, message)

    monkeypatch.setattr(operation_service, "advance", spy)
    return recorded


def _operation(session: FakeAsyncSession) -> Operation:
    """The `queued` operation row `app embeddings rebuild` created."""
    return asyncio.run(operation_service.create(session, embedding_service.REBUILD_OPERATION_TYPE))


def _catalogue(session: FakeAsyncSession, *documents_per_model: int) -> None:
    """Create one catalogue entry per argument, with that many documents."""
    for index, count in enumerate(documents_per_model):
        motorbike = asyncio.run(product_service.create_backlog(session, f"Test Model {index}"))
        for number in range(count):
            document = asyncio.run(
                document_service.create_document(
                    session,
                    motorbike.id,
                    source_type=SourceType.WIKIPEDIA,
                    source_title=f"Doc {number}",
                    raw_path=f"sources/{motorbike.id}/{number}.html",
                    content_markdown=ARTICLE,
                    fetched_at=FETCHED_AT,
                )
            )
            document.created_at = FETCHED_AT


def test_rebuild_embeds_the_whole_catalogue_and_succeeds(
    fake_session: FakeAsyncSession, stub_embeddings: StubEmbeddings
) -> None:
    _catalogue(fake_session, 2, 1)
    operation = _operation(fake_session)

    asyncio.run(job.rebuild(operation.id))

    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.progress == 100
    assert operation.error is None
    assert operation.started_at is not None
    chunks = fake_session.rows(Chunk)
    assert chunks
    assert all(chunk.embedding is not None for chunk in chunks)
    assert all(chunk.embedding_model == get_settings().embedding_model for chunk in chunks)


def test_rebuild_reports_progress_in_documents_processed(
    fake_session: FakeAsyncSession,
    stub_embeddings: StubEmbeddings,
    milestones: list[tuple[int, str]],
) -> None:
    _catalogue(fake_session, 2, 1)
    operation = _operation(fake_session)

    asyncio.run(job.rebuild(operation.id))

    assert milestones == [
        (0, job.START_MESSAGE),
        (33, "Generating embeddings (1/3)"),
        (66, "Generating embeddings (2/3)"),
        (99, "Generating embeddings (3/3)"),
    ]


def test_rebuild_of_an_empty_catalogue_succeeds_without_a_request(
    fake_session: FakeAsyncSession, stub_embeddings: StubEmbeddings
) -> None:
    _catalogue(fake_session, 0)
    operation = _operation(fake_session)

    asyncio.run(job.rebuild(operation.id))

    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.message == job.EMPTY_MESSAGE
    assert stub_embeddings.batches == []


def test_rebuild_without_a_key_fails_the_operation(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rebuild has nothing else to accomplish, so a missing key is fatal here.

    (The ingestion stage treats the same failure as a warning: it still has a
    model to hand to review.)
    """
    _catalogue(fake_session, 1)
    operation = _operation(fake_session)

    def raise_missing_key(model: str | None = None) -> object:
        raise MissingApiKeyError

    monkeypatch.setattr(llm_embeddings, "get_embeddings", raise_missing_key)

    asyncio.run(job.rebuild(operation.id))

    assert operation.status is OperationStatus.FAILED
    assert operation.error == embedding_service.MISSING_KEY_DETAIL
    assert operation.finished_at is not None
    # The chunks were rewritten even so; only their vectors are missing.
    assert fake_session.rows(Chunk)
    assert all(chunk.embedding is None for chunk in fake_session.rows(Chunk))


def test_rebuild_fails_loudly_on_a_dimension_mismatch(
    fake_session: FakeAsyncSession,
    stub_embeddings: StubEmbeddings,
    settings_override: Callable[..., None],
) -> None:
    _catalogue(fake_session, 1)
    operation = _operation(fake_session)
    settings_override(EMBEDDING_DIMENSIONS=768)

    with pytest.raises(embedding_service.DimensionMismatchError):
        asyncio.run(job.rebuild(operation.id))

    assert operation.status is OperationStatus.FAILED
    assert operation.error is not None
    assert "alembic upgrade head" in operation.error
    # Nothing was rewritten: the guard runs before the first document.
    assert fake_session.rows(Chunk) == []
    assert stub_embeddings.batches == []


def test_rebuild_of_an_unknown_operation_does_nothing(
    fake_session: FakeAsyncSession, stub_embeddings: StubEmbeddings
) -> None:
    _catalogue(fake_session, 1)

    asyncio.run(job.rebuild("0" * 26))

    assert fake_session.rows(Chunk) == []
    assert stub_embeddings.batches == []
