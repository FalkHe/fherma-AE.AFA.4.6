"""Async engine, session factory and the FastAPI session dependency."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

# Cap how long a connection attempt may block, so an unreachable database
# fails the readiness probe instead of hanging the request.
CONNECT_TIMEOUT_SECONDS = 5


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine (created on first use)."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        # Recycled or server-side-closed connections are detected before use.
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory."""
    return async_sessionmaker(
        bind=get_engine(),
        # Attributes stay readable after commit, which HTTP responses need.
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """Yield a request-scoped session.

    Transaction boundaries belong to the service layer: this dependency only
    guarantees that the session is closed once the request is finished.
    """
    async with get_sessionmaker()() as session:
        yield session
