"""Tests for the liveness and readiness probes."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from tests.conftest import StubSession


def test_health_reports_alive_without_touching_the_database(client: TestClient) -> None:
    """`/health` must answer without any session dependency at all."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_ready_when_the_database_answers(
    client: TestClient,
    stub_db_session: Callable[..., StubSession],
) -> None:
    """A successful `SELECT 1` yields 200 and both fields healthy."""
    session = stub_db_session()

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    assert session.statements == ["SELECT 1"]


def test_ready_reports_503_when_the_database_fails(
    client: TestClient,
    stub_db_session: Callable[..., StubSession],
) -> None:
    """A driver error is swallowed into a 503 payload, not a stack trace."""
    stub_db_session(
        OperationalError("SELECT 1", None, Exception("connection refused")),
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unavailable"}
