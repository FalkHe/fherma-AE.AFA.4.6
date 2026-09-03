"""`embeddings.rebuild` — re-chunk and re-embed the whole knowledge base.

The job an admin reaches through `app embeddings rebuild`. It exists because the
embedding columns are the only part of the catalogue that goes stale without
anybody touching a row: change `EMBEDDING_MODEL` and every stored vector was
produced by a model that is no longer the one queries are embedded with. The
rebuild rewrites them all — chunks included, because a vector must belong to the
text it was computed from.

Like `ingestion.run` the task is thin: ids only, its own session, and the
`operations` row it was given is the state the admin UI reads. Progress is
counted in **documents processed** over the whole catalogue, which is the only
unit known before the work starts (the chunk count exists only after a document
has been split).

Failure policy:

* A typed `EmbeddingFailure` (missing key, gateway error) stops the run and
  marks the operation `failed` with that detail — unlike the ingestion stage,
  there is nothing else this job could still accomplish.
* `DimensionMismatchError` and any other exception mark the operation `failed`
  and are re-raised for the worker log. Neither is a `TransientJobError`, so the
  retry middleware never repeats them.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operation import Operation
from app.db.session import get_sessionmaker
from app.jobs.broker import broker
from app.services import embedding_service, operation_service, product_service

logger = logging.getLogger(__name__)

# One page of catalogue entries per query; the catalogue ceiling is a few
# hundred rows, so this is one or two round trips.
PAGE_SIZE = 100

# Progress messages. Not part of the pinned ingestion milestone list — this
# operation has its own — but rendered verbatim in the admin UI all the same.
START_MESSAGE = "Rebuilding the knowledge base"
DOCUMENT_MESSAGE_TEMPLATE = "Generating embeddings ({index}/{total})"
EMPTY_MESSAGE = "Nothing to embed: the catalogue holds no source documents."

# While the job runs, progress stops one short of complete: 100 % means finished.
RUNNING_PROGRESS_CEILING = 99


@dataclass(slots=True)
class _Progress:
    """Counts documents across the whole run and reports each one."""

    session: AsyncSession
    operation: Operation
    total: int
    documents: int = 0
    chunks: int = 0

    async def document_finished(self) -> None:
        """Record one finished document and advance the operation."""
        self.documents += 1
        await operation_service.advance(
            self.session,
            self.operation,
            min(self.documents * 100 // self.total, RUNNING_PROGRESS_CEILING),
            DOCUMENT_MESSAGE_TEMPLATE.format(index=self.documents, total=self.total),
        )


@broker.task("embeddings.rebuild", retry_on_error=True)
async def rebuild(operation_id: str) -> None:
    """Re-embed every catalogue entry, reporting into `operation_id`.

    Args:
        operation_id: The `queued` operation row created before the enqueue.
    """
    async with get_sessionmaker()() as session:
        operation = await operation_service.get(session, operation_id)
        if operation is None:
            # Nothing to report into; a retry would find the same missing row.
            logger.error("embeddings.rebuild: unknown operation %r — nothing to do.", operation_id)
            return

        await operation_service.start(session, operation)
        try:
            await _rebuild(session, operation)
        except Exception as error:
            logger.exception("embeddings.rebuild failed.")
            # The exception may have left a broken transaction behind; the
            # bookkeeping below needs a usable session.
            await session.rollback()
            await operation_service.fail(session, operation, f"{type(error).__name__}: {error}")
            raise


async def _rebuild(session: AsyncSession, operation: Operation) -> None:
    """Walk the catalogue and close `operation` with the outcome."""
    # Before the first row is rewritten: a configured size that the column
    # cannot hold is a deployment mistake, and the message says which migration
    # fixes it.
    embedding_service.require_matching_dimensions()

    total = await embedding_service.count_documents(session)
    if total == 0:
        await operation_service.advance(session, operation, RUNNING_PROGRESS_CEILING, EMPTY_MESSAGE)
        await operation_service.succeed(session, operation)
        logger.info("embeddings.rebuild found no source documents.")
        return

    await operation_service.advance(session, operation, 0, START_MESSAGE)
    progress = _Progress(session=session, operation=operation, total=total)

    failure = await _rebuild_catalogue(session, progress)
    if failure is not None:
        await operation_service.fail(session, operation, failure.detail)
        logger.warning(
            "embeddings.rebuild stopped after %d document(s): %s",
            progress.documents,
            failure.detail,
        )
        return

    await operation_service.succeed(session, operation)
    logger.info(
        "embeddings.rebuild embedded %d chunk(s) from %d document(s).",
        progress.chunks,
        progress.documents,
    )


async def _rebuild_catalogue(
    session: AsyncSession, progress: _Progress
) -> embedding_service.EmbeddingFailure | None:
    """Rebuild every catalogue entry, stopping at the first typed failure."""
    offset = 0
    while True:
        page, total = await product_service.list_motorbikes(session, limit=PAGE_SIZE, offset=offset)
        if not page:
            return None

        for motorbike in page:
            outcome = await embedding_service.rebuild_motorbike(
                session, motorbike.id, on_document=progress.document_finished
            )
            if isinstance(outcome, embedding_service.EmbeddingFailure):
                progress.chunks += outcome.chunks
                return outcome
            progress.chunks += outcome.chunks

        offset += len(page)
        if offset >= total:
            return None
