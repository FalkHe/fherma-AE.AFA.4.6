"""`app/services/embedding_service.py` — batching, provenance and the guards.

The gateway is always a stub: no test here reaches OpenRouter, and none needs a
key. What is under test is everything around the one remote call — the loud
dimension guard, the batch size, the per-row provenance, the measure-before-write
rule, the bounded retry, and the typed failures the ingestion stage and the
rebuild job branch on.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.
"""

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest

from app.core.config import get_settings
from app.db.models import chunk as chunk_model
from app.db.models.chunk import Chunk
from app.db.models.source_document import SourceDocument, SourceType
from app.llm import embeddings as llm_embeddings
from app.llm.models import MissingApiKeyError
from app.services import document_service, embedding_service, product_service
from tests.services.conftest import FakeAsyncSession

FETCHED_AT = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)

ARTICLE = """# Suzuki GSR600

Introductory prose above the first sub-heading.

## Design

The GSR600 is a naked motorcycle.
"""


class StubEmbeddings:
    """Records the batches it was asked for and answers with sized vectors."""

    def __init__(self, dimensions: int | None = None, *, vectors_per_call: int | None = None):
        self.dimensions = dimensions
        self.vectors_per_call = vectors_per_call
        self.batches: list[list[str]] = []

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        width = get_settings().embedding_dimensions if self.dimensions is None else self.dimensions
        count = len(texts) if self.vectors_per_call is None else self.vectors_per_call
        return [[0.5] * width for _ in range(count)]


class BrokenEmbeddings:
    """Fails a configurable number of times before answering."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.attempts = 0

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError("OpenRouter answered 502")
        return [[0.5] * get_settings().embedding_dimensions for _ in texts]


@pytest.fixture(autouse=True)
def instant_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the bounded retry from actually sleeping."""
    monkeypatch.setattr(embedding_service, "TRANSIENT_RETRY_DELAY_SECONDS", 0)


@pytest.fixture
def settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Return a setter for the settings this service reads at call time."""

    def override(**environment: object) -> None:
        for key, value in environment.items():
            monkeypatch.setenv(key, str(value))
        get_settings.cache_clear()

    yield override
    get_settings.cache_clear()


def _document(
    session: FakeAsyncSession,
    motorbike_id: str,
    markdown: str,
    *,
    source_type: SourceType = SourceType.WIKIPEDIA,
) -> SourceDocument:
    """Store one source document and stamp `created_at` (a server default)."""
    document = asyncio.run(
        document_service.create_document(
            session,
            motorbike_id,
            source_type=source_type,
            source_title="Suzuki GSR600",
            raw_path=f"sources/{motorbike_id}/doc.html",
            content_markdown=markdown,
            fetched_at=FETCHED_AT,
        )
    )
    document.created_at = FETCHED_AT
    return document


def _chunks(session: FakeAsyncSession, count: int) -> list[Chunk]:
    """Add `count` unembedded chunk rows and return them in order."""
    chunks = [
        Chunk(
            source_document_id="0" * 26,
            motorbike_id="1" * 26,
            sequence=index,
            text=f"chunk {index}",
        )
        for index in range(count)
    ]
    for chunk in chunks:
        session.add(chunk)
    return chunks


# --- the dimension guard ------------------------------------------------------


def test_column_dimensions_reads_the_mapped_vector_column() -> None:
    assert embedding_service.column_dimensions() == chunk_model.EMBEDDING_DIMENSIONS


def test_the_configured_default_matches_the_column() -> None:
    """The shipped configuration is the one that needs no migration."""
    embedding_service.require_matching_dimensions()


def test_a_dimension_mismatch_fails_loudly_naming_the_migration(
    settings_override: Callable[..., None],
) -> None:
    settings_override(EMBEDDING_DIMENSIONS=768)

    with pytest.raises(embedding_service.DimensionMismatchError) as raised:
        embedding_service.require_matching_dimensions()

    message = str(raised.value)
    assert "EMBEDDING_DIMENSIONS is 768" in message
    assert f"vector({chunk_model.EMBEDDING_DIMENSIONS})" in message
    # The message is the instruction: which files, which command, and the
    # promise that nothing is silently resized to fit.
    assert "app/db/models/chunk.py" in message
    assert "alembic revision --autogenerate" in message
    assert "alembic upgrade head" in message
    assert "never truncated" in message
    assert (raised.value.configured, raised.value.column) == (
        768,
        chunk_model.EMBEDDING_DIMENSIONS,
    )


def test_embedding_refuses_to_run_at_all_on_a_mismatch(
    fake_session: FakeAsyncSession, settings_override: Callable[..., None]
) -> None:
    chunks = _chunks(fake_session, 1)
    client = StubEmbeddings()
    settings_override(EMBEDDING_DIMENSIONS=768)

    with pytest.raises(embedding_service.DimensionMismatchError):
        asyncio.run(embedding_service.embed_chunks(fake_session, chunks, embeddings=client))

    # Not one request was made and not one row was touched.
    assert client.batches == []
    assert chunks[0].embedding is None


# --- batching and provenance --------------------------------------------------


def test_embed_chunks_batches_sixty_four_texts_per_request(
    fake_session: FakeAsyncSession,
) -> None:
    chunks = _chunks(fake_session, 130)
    client = StubEmbeddings()

    written = asyncio.run(embedding_service.embed_chunks(fake_session, chunks, embeddings=client))

    assert embedding_service.BATCH_SIZE == 64
    assert [len(batch) for batch in client.batches] == [64, 64, 2]
    assert written == 130
    # Order is preserved, so vector n belongs to chunk n.
    assert [text for batch in client.batches for text in batch] == [c.text for c in chunks]
    # One commit per batch: a run that dies halfway keeps what it paid for.
    assert fake_session.commit_count == 3


def test_embed_chunks_records_the_model_and_the_size_on_every_row(
    fake_session: FakeAsyncSession,
) -> None:
    chunks = _chunks(fake_session, 3)
    settings = get_settings()

    asyncio.run(
        embedding_service.embed_chunks(
            fake_session, chunks, embeddings=StubEmbeddings(), model="openai/some-embedder"
        )
    )

    for chunk in chunks:
        assert chunk.embedding == [0.5] * settings.embedding_dimensions
        assert chunk.embedding_model == "openai/some-embedder"
        assert chunk.embedding_dimensions == settings.embedding_dimensions


def test_embed_chunks_of_nothing_makes_no_request(fake_session: FakeAsyncSession) -> None:
    client = StubEmbeddings()

    assert asyncio.run(embedding_service.embed_chunks(fake_session, [], embeddings=client)) == 0
    assert client.batches == []


def test_embed_chunks_without_a_configured_key_reports_configuration(
    fake_session: FakeAsyncSession, settings_override: Callable[..., None]
) -> None:
    settings_override(OPENROUTER_API_KEY="")
    chunks = _chunks(fake_session, 1)

    with pytest.raises(MissingApiKeyError):
        asyncio.run(embedding_service.embed_chunks(fake_session, chunks))


# --- measure before write -----------------------------------------------------


def test_a_wrong_sized_vector_is_never_written(fake_session: FakeAsyncSession) -> None:
    chunks = _chunks(fake_session, 2)

    with pytest.raises(embedding_service.UnexpectedVectorSizeError) as raised:
        asyncio.run(
            embedding_service.embed_chunks(
                fake_session, chunks, embeddings=StubEmbeddings(dimensions=8)
            )
        )

    assert (raised.value.expected, raised.value.received) == (
        get_settings().embedding_dimensions,
        8,
    )
    assert all(chunk.embedding is None for chunk in chunks)
    assert all(chunk.embedding_model is None for chunk in chunks)


def test_a_wrong_number_of_vectors_is_never_written(fake_session: FakeAsyncSession) -> None:
    chunks = _chunks(fake_session, 3)

    with pytest.raises(embedding_service.UnexpectedVectorSizeError):
        asyncio.run(
            embedding_service.embed_chunks(
                fake_session, chunks, embeddings=StubEmbeddings(vectors_per_call=2)
            )
        )

    assert all(chunk.embedding is None for chunk in chunks)


# --- the bounded retry --------------------------------------------------------


def test_a_failing_request_is_retried_before_it_is_reported(
    fake_session: FakeAsyncSession,
) -> None:
    chunks = _chunks(fake_session, 1)
    client = BrokenEmbeddings(failures=embedding_service.TRANSIENT_ATTEMPTS - 1)

    written = asyncio.run(embedding_service.embed_chunks(fake_session, chunks, embeddings=client))

    assert client.attempts == embedding_service.TRANSIENT_ATTEMPTS
    assert written == 1
    assert chunks[0].embedding is not None


def test_the_retry_is_bounded(fake_session: FakeAsyncSession) -> None:
    chunks = _chunks(fake_session, 1)
    client = BrokenEmbeddings(failures=99)

    with pytest.raises(RuntimeError, match="502"):
        asyncio.run(embedding_service.embed_chunks(fake_session, chunks, embeddings=client))

    assert client.attempts == embedding_service.TRANSIENT_ATTEMPTS


# --- rebuilding one catalogue entry ------------------------------------------


def test_rebuild_motorbike_chunks_and_embeds_every_document(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    _document(fake_session, motorbike.id, ARTICLE)
    _document(fake_session, motorbike.id, "## Reception\n\nReviewers praised it.")
    client = StubEmbeddings()
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: client)
    finished: list[int] = []

    async def on_document() -> None:
        finished.append(len(fake_session.rows(Chunk)))

    outcome = asyncio.run(
        embedding_service.rebuild_motorbike(fake_session, motorbike.id, on_document=on_document)
    )

    assert isinstance(outcome, embedding_service.EmbeddingResult)
    assert outcome.documents == 2
    assert outcome.chunks == len(fake_session.rows(Chunk))
    assert outcome.model == get_settings().embedding_model
    assert outcome.dimensions == get_settings().embedding_dimensions
    assert all(chunk.embedding is not None for chunk in fake_session.rows(Chunk))
    # The progress hook fires once per document, after it was written.
    assert len(finished) == 2


def test_rebuild_motorbike_without_documents_is_a_successful_no_op(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: StubEmbeddings())

    outcome = asyncio.run(embedding_service.rebuild_motorbike(fake_session, motorbike.id))

    assert outcome == embedding_service.EmbeddingResult(
        documents=0,
        chunks=0,
        model=get_settings().embedding_model,
        dimensions=get_settings().embedding_dimensions,
    )


def test_rebuild_motorbike_still_chunks_without_a_key(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chunks are cheap and correct without a gateway; the rebuild backfills."""
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    _document(fake_session, motorbike.id, ARTICLE)

    def raise_missing_key(model: str | None = None) -> object:
        raise MissingApiKeyError

    monkeypatch.setattr(llm_embeddings, "get_embeddings", raise_missing_key)

    outcome = asyncio.run(embedding_service.rebuild_motorbike(fake_session, motorbike.id))

    assert isinstance(outcome, embedding_service.EmbeddingFailure)
    assert outcome.reason is embedding_service.EmbeddingFailureReason.MISSING_API_KEY
    assert outcome.detail == embedding_service.MISSING_KEY_DETAIL
    assert (outcome.documents, outcome.chunks) == (1, 0)
    assert fake_session.rows(Chunk)
    assert all(chunk.embedding is None for chunk in fake_session.rows(Chunk))


def test_rebuild_motorbike_reports_a_gateway_failure_once_and_keeps_chunking(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    _document(fake_session, motorbike.id, ARTICLE)
    _document(fake_session, motorbike.id, "## Reception\n\nReviewers praised it.")
    client = BrokenEmbeddings(failures=99)
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: client)

    outcome = asyncio.run(embedding_service.rebuild_motorbike(fake_session, motorbike.id))

    assert isinstance(outcome, embedding_service.EmbeddingFailure)
    assert outcome.reason is embedding_service.EmbeddingFailureReason.MODEL_ERROR
    assert "OpenRouter answered 502" in outcome.detail
    assert outcome.documents == 2
    # The gateway is asked once (retries included), not again per document.
    assert client.attempts == embedding_service.TRANSIENT_ATTEMPTS
    # Both documents are chunked all the same.
    assert len({chunk.source_document_id for chunk in fake_session.rows(Chunk)}) == 2


def test_rebuild_motorbike_never_chunks_or_embeds_a_listing_document(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D12, second carve-out: dated asking prices never enter the RAG base."""
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    wikipedia_document = _document(fake_session, motorbike.id, ARTICLE)
    _document(
        fake_session,
        motorbike.id,
        "Asking 4200 EUR, low mileage.",
        source_type=SourceType.LISTING,
    )
    client = StubEmbeddings()
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: client)

    outcome = asyncio.run(embedding_service.rebuild_motorbike(fake_session, motorbike.id))

    assert isinstance(outcome, embedding_service.EmbeddingResult)
    # Only the Wikipedia document is counted, chunked and embedded.
    assert outcome.documents == 1
    chunks = fake_session.rows(Chunk)
    assert chunks
    assert {chunk.source_document_id for chunk in chunks} == {wikipedia_document.id}


def test_count_documents_counts_the_whole_catalogue(fake_session: FakeAsyncSession) -> None:
    first = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    second = asyncio.run(product_service.create_backlog(fake_session, "Yamaha MT-07"))
    _document(fake_session, first.id, ARTICLE)
    _document(fake_session, first.id, "## Reception\n\nReviewers praised it.")
    _document(fake_session, second.id, ARTICLE)

    assert asyncio.run(embedding_service.count_documents(fake_session)) == 3
