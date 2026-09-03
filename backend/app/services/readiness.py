"""Readiness checks for the application's essential dependencies."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def is_database_reachable(session: AsyncSession) -> bool:
    """Return whether a trivial statement can be executed against PostgreSQL.

    Any driver or connection failure means "not ready"; it is logged here and
    never propagated, so the endpoint can answer 503 instead of raising.
    """
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Readiness check failed: database unreachable", exc_info=True)
        return False
    return True
