"""Shared fixtures and environment pinning for the backend test suite.

Binding arrangement, `step-0.1.md` §6.5 / `shared-knowledge.md` D9: this suite
never constructs a real database engine and never uses `pytest-asyncio`. It is
fully synchronous (`TestClient`), overrides `get_db_session` with a stub that
is never actually touched, and drives behaviour by monkeypatching the pinned
service functions of §6.1. `get_engine()` / `get_sessionmaker()` must never be
called by anything in here.

Environment variables are pinned *before* `app` is imported, because
`app.core.settings.get_settings()` may be read at import time by code we do
not control, and the root `.env` (outside `backend/`) must not leak into a
run. `get_settings.cache_clear()` is called immediately after, per §6.5 step 1.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://app:app@postgres:5432/application"
os.environ["ENVIRONMENT"] = "development"
os.environ["SESSION_TTL_SECONDS"] = "1209600"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"
os.environ["OPENROUTER_API_KEY"] = "test-key"
os.environ["CHAT_MODEL"] = "test/model"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.db import get_db_session  # noqa: E402
from app.main import create_app  # noqa: E402

# Mirrors the env vars above; tests assert cookie/CORS attributes against
# these rather than against magic numbers scattered through the suite.
SESSION_TTL_SECONDS = 1209600
FRONTEND_ORIGIN = "http://localhost:5173"


def _stub_db_session():
    """Override for `get_db_session`. Route tests never let this object be
    used for anything: they replace the pinned service functions instead
    (§6.5 step 3-4), so the stub only needs to satisfy FastAPI's dependency
    injection, never SQLAlchemy's API."""
    return object()


@pytest.fixture
def app():
    """A fresh `create_app()` per test, wired to the DB-session stub. Tests
    that need a route to behave a particular way monkeypatch the relevant
    `service` module attribute(s) *before* issuing the request."""
    application = create_app()
    application.dependency_overrides[get_db_session] = _stub_db_session
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def error_client(app):
    """A client that does not re-raise server exceptions into the test
    process, so the `500 INTERNAL_ERROR` envelope can be observed instead of
    the exception propagating (§6.5: `TestClient(app,
    raise_server_exceptions=False)`)."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def production_client(monkeypatch):
    """A client built against `environment=production` settings, for the
    cookie-`Secure`-flag and docs-disabled edge cases (§5.7, §6.1
    `create_app()`). Clears the settings cache on the way in and out so
    `production` never leaks into another test - `monkeypatch` reverts the
    env var automatically at teardown, but the `lru_cache`d settings object
    would otherwise survive that revert."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[get_db_session] = _stub_db_session
    try:
        yield TestClient(application)
    finally:
        get_settings.cache_clear()


@pytest.fixture
def session_cookie_header():
    """Returns a callable building a `Cookie` request header for a given
    session-token value.

    Not `TestClient.get(..., cookies={...})`: the pinned `httpx>=0.28.1`
    (`step-0.1.md` §6.1) deprecated per-request `cookies=` in favour of
    setting cookies on the client instance, and warns on every call under
    that parameter - fatal under `filterwarnings = ["error"]`
    (`pyproject.toml`). Per-request cookies are still the right tool here
    (each test simulates a distinct, possibly stale, cookie value against a
    shared `client` fixture), so tests send the `Cookie` header directly
    instead of triggering the deprecated parameter."""

    def _header(token: str) -> dict[str, str]:
        return {"Cookie": f"session={token}"}

    return _header


@pytest.fixture
def assert_error_envelope():
    """Returns a callable that asserts the §5.1 error envelope shape -
    exactly `{"error": {"code", "message", "details"}}` and no other
    top-level key - and returns the inner `error` object for further
    assertions. Used throughout the suite; collectively this is what proves
    criterion 26 ("every non-2xx response ... has this body shape") across
    every error path the other test modules exercise."""

    def _assert(response, *, status: int, code: str) -> dict:
        assert response.status_code == status, response.text
        body = response.json()
        assert set(body.keys()) == {"error"}, body
        error = body["error"]
        assert set(error.keys()) == {"code", "message", "details"}, error
        assert error["code"] == code, error
        return error

    return _assert
