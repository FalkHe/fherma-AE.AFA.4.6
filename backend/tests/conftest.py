"""Shared fixtures for the backend test suite.

No test here may touch a real database: PostgreSQL is not running during a
plain `uv run pytest`. Routes that depend on a session receive a stub via
FastAPI's dependency overrides, so `app.db.session.get_engine()` is never
called — which also side-steps the `lru_cache`'d-engine / event-loop pitfall
described in `docs/qa-checklist.md`.

The same holds for Redis: adding a product auto-starts its ingestion and
starting a consultation auto-starts the advisor's greeting, so the
`enqueue_ingestion` seam of `product_service` and the `enqueue_chat_response`
seam of `chat_service` are replaced for **every** test by the autouse
`recorded_enqueues` / `recorded_chat_enqueues` fixtures. A test that wants to
prove an enqueue happened simply requests the fixture and reads the recorded
ids.
"""

from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app
from app.services import chat_service, product_service


@pytest.fixture(scope="session", autouse=True)
def _settings_environment() -> Iterator[None]:
    """Pin the settings the app reads, so the developer's `.env` cannot leak in.

    The URLs are syntactically valid but deliberately never dialled.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:5432/test")
        patch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        patch.setenv("ENVIRONMENT", "development")
        patch.setenv("LOG_LEVEL", "WARNING")
        # The root `.env` may legitimately select `openrouter`; tests pin the default instead.
        patch.setenv("SEARCH_PROVIDER", "tavily")
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def recorded_enqueues(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record `ingestion.run` enqueues instead of pushing them onto Redis.

    Returns the `(motorbike_id, operation_id)` pairs, in order.
    """
    calls: list[tuple[str, str]] = []

    async def record(motorbike_id: str, operation_id: str) -> None:
        calls.append((motorbike_id, operation_id))

    monkeypatch.setattr(product_service, "enqueue_ingestion", record)
    return calls


@pytest.fixture(autouse=True)
def recorded_chat_enqueues(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record `chat.respond` enqueues instead of pushing them onto Redis.

    Returns the `(chat_id, operation_id)` pairs, in order.
    """
    calls: list[tuple[str, str]] = []

    async def record(chat_id: str, operation_id: str) -> None:
        calls.append((chat_id, operation_id))

    monkeypatch.setattr(chat_service, "enqueue_chat_response", record)
    return calls


class StubSession:
    """Stand-in for `AsyncSession`; only `execute()` is exercised so far."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.statements: list[str] = []

    async def execute(self, statement: object) -> None:
        """Record the statement and raise the configured failure, if any."""
        self.statements.append(str(statement))
        if self.error is not None:
            raise self.error


@pytest.fixture
def api() -> FastAPI:
    """Return a freshly built application instance."""
    return create_app()


@pytest.fixture
def stub_db_session(api: FastAPI) -> Iterator[Callable[..., StubSession]]:
    """Return a factory that installs a `StubSession` as the session dependency."""

    def install(error: Exception | None = None) -> StubSession:
        session = StubSession(error)
        api.dependency_overrides[get_db_session] = lambda: session
        return session

    yield install
    api.dependency_overrides.clear()


@pytest.fixture
def client(api: FastAPI) -> Iterator[TestClient]:
    """Return a synchronous HTTP client bound to the application."""
    with TestClient(api) as test_client:
        yield test_client
