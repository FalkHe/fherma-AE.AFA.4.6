"""Fill the embedding columns of the knowledge base.

The service half of step 2.19: it turns stored chunks into vectors and writes
them back with the model that produced them. Chunking itself belongs to
`app.services.chunking`; this module composes the two, because a chunk and its
vector must be written from the same text — a rewritten chunk keeping an old
vector is the one bug this layer exists to prevent.

Four rules live here:

* **The dimension guard is loud.** The configured `EMBEDDING_DIMENSIONS` and the
  `vector(n)` width of `chunks.embedding` must agree. They do not agree by
  luck — a different embedding model means a migration — so a mismatch raises
  `DimensionMismatchError` naming that migration instead of truncating,
  padding, or writing rows the index cannot use.
* **Every vector is measured before it is written.** A gateway that answers
  with a differently sized vector is a model error, not something to store.
* **Requests are batched** (`BATCH_SIZE` texts per call) and each batch is
  committed on its own, so a run that dies halfway leaves the work it already
  did behind instead of starting over.
* **A failure is a typed value, not an exception** (the adapter convention of
  `spec_extraction_service` and the ingestion adapters): the ingestion stage
  appends the `detail` to its operation message and hands the model to review
  anyway, while `app embeddings rebuild` fails its operation with it. The one
  exception is `DimensionMismatchError` — a deployment mistake that must not be
  reduced to a line of warning text.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import islice

from langchain_core.embeddings import Embeddings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.chunk import EMBEDDING_MODEL_LENGTH, Chunk
from app.db.models.source_document import SourceDocument, SourceType
from app.llm import embeddings as llm_embeddings
from app.llm.models import MissingApiKeyError
from app.services import chunking, document_service

logger = logging.getLogger(__name__)

# `type` of the operation an `app embeddings rebuild` is tracked as. Matches the
# Taskiq task name on purpose: one string names the job everywhere.
REBUILD_OPERATION_TYPE = "embeddings.rebuild"

# Texts per embeddings request. Large enough that a catalogue re-embed is a
# handful of round trips, small enough to stay well inside any gateway's
# request-size limits.
BATCH_SIZE = 64

# One embeddings call is retried this often before the failure is reported: a
# gateway hiccup must not cost a whole run, but the caller (an ingestion stage
# that still has a model to hand to review) may not wait forever either.
TRANSIENT_ATTEMPTS = 3
TRANSIENT_RETRY_DELAY_SECONDS = 2.0

# How the typed failures read in an operation message.
MISSING_KEY_DETAIL = "Embedding skipped: OPENROUTER_API_KEY is not configured."
MODEL_ERROR_DETAIL = "Embedding failed: {error}"
MAX_ERROR_CHARS = 200


class DimensionMismatchError(RuntimeError):
    """Configured embedding size and `chunks.embedding` column width disagree.

    Deliberately fatal: the alternative — truncating or padding vectors to fit —
    would silently poison every retrieval built on the affected rows.
    """

    def __init__(self, configured: int, column: int) -> None:
        super().__init__(
            f"EMBEDDING_DIMENSIONS is {configured}, but chunks.embedding is "
            f"vector({column}). Change EMBEDDING_DIMENSIONS in app/core/config.py "
            f"(and .env) together with EMBEDDING_DIMENSIONS in "
            f"app/db/models/chunk.py, then generate and apply the migration that "
            f"alters the column: "
            f"`docker compose run --rm app-cli alembic revision --autogenerate "
            f'-m "resize chunk embeddings"` followed by `alembic upgrade head`. '
            f"Embeddings are never truncated to fit."
        )
        self.configured = configured
        self.column = column


class UnexpectedVectorSizeError(RuntimeError):
    """The gateway returned a vector that is not `EMBEDDING_DIMENSIONS` long."""

    def __init__(self, expected: int, received: int) -> None:
        super().__init__(
            f"Embedding model returned a {received}-dimension vector, expected {expected}."
        )
        self.expected = expected
        self.received = received


class EmbeddingFailureReason(StrEnum):
    """Why one embedding pass produced no (or incomplete) vectors."""

    MISSING_API_KEY = "missing_api_key"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """A completed pass: what it rewrote, and with which model."""

    documents: int
    chunks: int
    model: str
    dimensions: int


@dataclass(frozen=True, slots=True)
class EmbeddingFailure:
    """A pass that did not embed everything, with a warning-ready detail."""

    reason: EmbeddingFailureReason
    detail: str
    documents: int
    chunks: int


EmbeddingOutcome = EmbeddingResult | EmbeddingFailure

# Called once per document a rebuild finished, so a job can report progress.
DocumentCallback = Callable[[], Awaitable[None]]


def column_dimensions() -> int:
    """Return the `vector(n)` width the `chunks.embedding` column was built with.

    Read from the mapped column rather than from a constant, so the guard below
    compares against the schema itself; the value is
    `app.db.models.chunk.EMBEDDING_DIMENSIONS` by construction, and no database
    round trip is needed to learn it.
    """
    return Chunk.__table__.c.embedding.type.dim


def require_matching_dimensions() -> None:
    """Fail loudly unless the configured size matches the column width.

    Raises:
        DimensionMismatchError: the two disagree; the message names the
            migration that has to happen first.
    """
    configured = get_settings().embedding_dimensions
    column = column_dimensions()
    if configured != column:
        raise DimensionMismatchError(configured, column)


async def count_documents(session: AsyncSession) -> int:
    """Return how many source documents the whole catalogue holds.

    The unit a rebuild reports progress in: documents, not chunks — the chunk
    count is only known once a document has been split.
    """
    result = await session.execute(select(func.count()).select_from(SourceDocument))
    return result.scalar_one()


async def embed_chunks(
    session: AsyncSession,
    chunks: Sequence[Chunk],
    *,
    embeddings: Embeddings | None = None,
    model: str | None = None,
) -> int:
    """Embed `chunks` in batches and write vector, model and size per row.

    Args:
        session: Session the rows belong to; one commit per finished batch.
        chunks: Rows to embed, in any order.
        embeddings: Reuse a client (one per run); built from configuration when
            omitted.
        model: Model identifier recorded on every row; defaults to the
            configured `EMBEDDING_MODEL`. Must describe `embeddings`.

    Returns:
        How many rows were written.

    Raises:
        DimensionMismatchError: configuration and column width disagree.
        MissingApiKeyError: no client was passed and no key is configured.
        UnexpectedVectorSizeError: the gateway answered with a wrong-sized
            vector or a wrong number of vectors — nothing is written.
    """
    require_matching_dimensions()
    if not chunks:
        return 0

    settings = get_settings()
    model_name = model or settings.embedding_model
    client = llm_embeddings.get_embeddings(model_name) if embeddings is None else embeddings

    written = 0
    for batch in _batched(chunks, BATCH_SIZE):
        vectors = await _embed_batch(client, [chunk.text for chunk in batch])
        if len(vectors) != len(batch):
            raise UnexpectedVectorSizeError(len(batch), len(vectors))

        for chunk, vector in zip(batch, vectors, strict=True):
            if len(vector) != settings.embedding_dimensions:
                # Measured before the write, never after: a wrong-sized vector
                # must not reach a row at all.
                raise UnexpectedVectorSizeError(settings.embedding_dimensions, len(vector))
            chunk.embedding = vector
            chunk.embedding_model = model_name[:EMBEDDING_MODEL_LENGTH]
            chunk.embedding_dimensions = settings.embedding_dimensions

        # Per batch, so a failure halfway keeps what was already paid for.
        await session.commit()
        written += len(batch)

    return written


async def rebuild_motorbike(
    session: AsyncSession,
    motorbike_id: str,
    *,
    model: str | None = None,
    on_document: DocumentCallback | None = None,
) -> EmbeddingOutcome:
    """Re-chunk and re-embed every document of one catalogue entry.

    Chunking always runs to completion, even when the embeddings half cannot:
    the chunks are the part of the knowledge base that is cheap to rebuild and
    correct without a gateway, and `app embeddings rebuild` backfills the
    vectors later. The returned failure says why the vectors are missing.

    Args:
        session: Session everything is written through; the services commit.
        motorbike_id: Catalogue entry whose stored documents are rebuilt.
        model: Embedding model identifier; defaults to `EMBEDDING_MODEL`.
        on_document: Awaited once per finished document — the progress hook of
            the rebuild job.

    Returns:
        What was rewritten, or a typed failure whose `detail` is ready for an
        operation message.

    Raises:
        DimensionMismatchError: configuration and column width disagree. The one
            failure that is not a value here — see the module docstring.
    """
    require_matching_dimensions()
    settings = get_settings()
    model_name = model or settings.embedding_model
    # `listing` documents are excluded (D12, second carve-out): dated asking
    # prices must never become a chunk or an embedding, or the RAG knowledge
    # base would retrieve them as timeless prose.
    documents = await document_service.list_for_motorbike(
        session, motorbike_id, exclude_source_types=(SourceType.LISTING,)
    )

    client: Embeddings | None = None
    failure: EmbeddingFailure | None = None
    try:
        client = llm_embeddings.get_embeddings(model_name)
    except MissingApiKeyError:
        # Deterministic, not transient: retrying cannot configure a key.
        failure = _failed(EmbeddingFailureReason.MISSING_API_KEY, MISSING_KEY_DETAIL, motorbike_id)

    written = 0
    for document in documents:
        chunks = await chunking.rebuild_document(session, document)
        if client is not None and chunks:
            try:
                written += await embed_chunks(session, chunks, embeddings=client, model=model_name)
            except Exception as error:
                # A gateway error, a timeout, an unusable answer: the taxonomy
                # spans the SDK, its HTTP client and the response shape, and
                # every one of them means the same thing here — stop embedding,
                # keep chunking, report once.
                failure = _model_error(error, motorbike_id)
                client = None
        if on_document is not None:
            await on_document()

    if failure is not None:
        return EmbeddingFailure(
            reason=failure.reason,
            detail=failure.detail,
            documents=len(documents),
            chunks=written,
        )
    logger.info(
        "Embedded %d chunk(s) from %d document(s) of motorbike %s with %s.",
        written,
        len(documents),
        motorbike_id,
        model_name,
    )
    return EmbeddingResult(
        documents=len(documents),
        chunks=written,
        model=model_name,
        dimensions=settings.embedding_dimensions,
    )


async def _embed_batch(client: Embeddings, texts: list[str]) -> list[list[float]]:
    """Embed one batch, retrying a failing call before giving up.

    The retry is here rather than in the broker because the caller may not be
    retryable as a whole: an ingestion run that re-queues itself would re-fetch
    every source over a hiccup in the embeddings gateway.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await client.aembed_documents(texts)
        except Exception as error:
            if attempt >= TRANSIENT_ATTEMPTS:
                raise
            delay = TRANSIENT_RETRY_DELAY_SECONDS * attempt
            logger.warning(
                "Embedding request failed (attempt %d/%d), retrying in %.1fs: %s: %s",
                attempt,
                TRANSIENT_ATTEMPTS,
                delay,
                type(error).__name__,
                error,
            )
            await asyncio.sleep(delay)


def _batched(chunks: Sequence[Chunk], size: int) -> list[list[Chunk]]:
    """Split `chunks` into request-sized batches, keeping their order."""
    iterator = iter(chunks)
    batches: list[list[Chunk]] = []
    while batch := list(islice(iterator, size)):
        batches.append(batch)
    return batches


def _failed(reason: EmbeddingFailureReason, detail: str, motorbike_id: str) -> EmbeddingFailure:
    """Log one expected failure once and return it, as the adapters do."""
    logger.warning("Motorbike %s: %s", motorbike_id, detail)
    return EmbeddingFailure(reason=reason, detail=detail, documents=0, chunks=0)


def _model_error(error: Exception, motorbike_id: str) -> EmbeddingFailure:
    """Turn any embeddings-side exception into the one warning-ready failure."""
    detail = MODEL_ERROR_DETAIL.format(error=f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS])
    logger.warning("Embedding of motorbike %s failed.", motorbike_id, exc_info=error)
    return EmbeddingFailure(
        reason=EmbeddingFailureReason.MODEL_ERROR, detail=detail, documents=0, chunks=0
    )
