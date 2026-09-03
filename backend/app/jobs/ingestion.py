"""`ingestion.run` — the task that ingests one catalogue entry.

The task is deliberately thin: it owns the worker's session and the failure
policy, while `app.services.ingestion.service` owns the pipeline. Its arguments
are ids only — the enqueuing process and the worker share no objects, and the
`operations` row (created `queued` before the enqueue) is the state both sides
talk through.

Failure policy, matching the pinned retry contract:

* `TransientJobError` propagates untouched, so the broker's retry middleware
  sees it. The operation stays `running` and the motorbike stays `ingesting`,
  because the very same run is about to be attempted again.
* Any other exception is a bug or a deterministic failure: the operation is
  marked `failed`, the motorbike goes back to `backlog` and the exception is
  re-raised for the worker log. The middleware's type filter means it is never
  retried. This is also how the embedding stage's dimension guard surfaces:
  `embedding_service.DimensionMismatchError` deliberately escapes the stage, so
  the operation `error` an admin reads is the message naming the migration that
  has to happen before the knowledge base can be embedded.
"""

import logging

from app.db.session import get_sessionmaker
from app.jobs import TransientJobError
from app.jobs.broker import broker
from app.services import operation_service, product_service
from app.services.ingestion import service as ingestion_service

logger = logging.getLogger(__name__)


@broker.task("ingestion.run", retry_on_error=True)
async def run(motorbike_id: str, operation_id: str) -> None:
    """Ingest `motorbike_id`, reporting progress into `operation_id`.

    Args:
        motorbike_id: Catalogue entry to ingest; expected in `ingesting`.
        operation_id: Its `queued` operation row.
    """
    async with get_sessionmaker()() as session:
        motorbike = await product_service.get_motorbike(session, motorbike_id)
        operation = await operation_service.get(session, operation_id)
        if motorbike is None or operation is None:
            # Nothing to report into and nothing to report about: a retry would
            # find the same missing rows.
            logger.error(
                "ingestion.run: unknown motorbike %r or operation %r — nothing to do.",
                motorbike_id,
                operation_id,
            )
            return

        try:
            await ingestion_service.ingest(session, motorbike, operation)
        except TransientJobError:
            logger.warning(
                "ingestion.run for motorbike %s hit a transient failure; retrying.", motorbike_id
            )
            raise
        except Exception as error:
            logger.exception("ingestion.run for motorbike %s failed.", motorbike_id)
            # The exception may have left a broken transaction behind; the
            # bookkeeping below needs a usable session.
            await session.rollback()
            await ingestion_service.abandon(
                session, motorbike, operation, f"{type(error).__name__}: {error}"
            )
            raise
