"""Authentication and availability of the SSE endpoint `GET /api/events`.

The streaming behaviour itself is covered where it lives — in
`tests/services/test_notification_listener.py` and by the manual curl check of
step 2.7; what matters here is that an unauthenticated browser never gets a
stream, and that a request handled by a process without a listener is refused
cleanly instead of raising.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.endpoints.events import LISTENER_STATE_ATTRIBUTE
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def signed_in(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    """A client with a session cookie, on an app whose lifespan never ran.

    No lifespan means no listener — exactly the state the availability test
    needs, and irrelevant to the authentication one.
    """
    api.dependency_overrides[get_db_session] = lambda: fake_session
    client = TestClient(api)
    assert (
        client.post("/auth/register", json={"username": "rider", "password": "secret123"})
    ).status_code == 201
    assert (
        client.post(
            "/auth/login",
            json={"username": "rider", "password": "secret123", "rememberMe": False},
        ).status_code
        == 200
    )
    yield client
    api.dependency_overrides.clear()


def test_stream_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        response = client.get("/api/events")
    api.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_stream_without_a_listener_returns_503(signed_in: TestClient) -> None:
    response = signed_in.get("/api/events")

    assert response.status_code == 503
    assert response.json() == {"detail": "Event stream unavailable."}


def test_a_running_listener_is_parked_on_the_application_state(api: FastAPI) -> None:
    """The lifespan owns the listener the endpoint reads."""
    with TestClient(api):
        listener = getattr(api.state, LISTENER_STATE_ATTRIBUTE)
        assert listener is not None
