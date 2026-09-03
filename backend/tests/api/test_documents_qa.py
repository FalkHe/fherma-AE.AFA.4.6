"""QA supplement to `test_documents.py` (step 2.9).

Only fills the one gap the dev-authored suite leaves in the "writes are
rejected" criterion: it proves POST and PATCH return 405 but not DELETE.
Everything else in the acceptance criteria (auth matrix, filter handling,
Markdown + provenance round-trip) is already covered there and is not
re-authored here to avoid duplication.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.user import UserRole
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession

BIKE_ID = "0" * 22 + "BIKE"


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def admin_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        registered = client.post(
            "/auth/register", json={"username": "curator", "password": "secret123"}
        )
        assert registered.status_code == 201, registered.text
        assert (
            client.post(
                "/auth/login",
                json={"username": "curator", "password": "secret123", "rememberMe": False},
            ).status_code
            == 200
        )
        fake_session.users[registered.json()["id"]].role = UserRole.ADMIN
        yield client
    api.dependency_overrides.clear()


def test_delete_without_an_id_returns_405(admin_client: TestClient) -> None:
    headers = {"X-CSRF-Token": admin_client.cookies["csrf_token"]}

    response = admin_client.delete(
        "/api/documents", params={"filter[product]": BIKE_ID}, headers=headers
    )

    assert response.status_code == 405
