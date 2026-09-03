"""Behavioural tests for the read-only `operations` JSON:API resource.

Same setup as `test_products.py`: the in-memory `FakeAsyncSession` stands behind
`get_db_session`, so `operation_service` really runs. Rows are created through
the service — there is no HTTP path that creates an operation, which is itself
part of the contract.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.operation import Operation, OperationStatus
from app.db.models.user import UserRole
from app.db.session import get_db_session
from app.services import operation_service
from app.services.operation_service import MOTORBIKE_ENTITY_TYPE
from tests.services.conftest import FakeAsyncSession

OPERATION_ATTRIBUTES = {
    "type",
    "status",
    "progress",
    "message",
    "error",
    "entityType",
    "entityId",
    "createdAt",
    "startedAt",
    "finishedAt",
}

BIKE_ID = "0" * 22 + "BIKE"
OTHER_BIKE_ID = "0" * 22 + "OTHR"


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


def _signed_in_client(
    api: FastAPI, fake_session: FakeAsyncSession, *, role: UserRole
) -> Iterator[TestClient]:
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
        # Out-of-band promotion, exactly as the admin CLI would do it.
        fake_session.users[registered.json()["id"]].role = role
        yield client
    api.dependency_overrides.clear()


@pytest.fixture
def admin_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    yield from _signed_in_client(api, fake_session, role=UserRole.ADMIN)


@pytest.fixture
def user_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    yield from _signed_in_client(api, fake_session, role=UserRole.USER)


def _operation(
    session: FakeAsyncSession,
    *,
    type: str = "demo",
    entity_type: str | None = None,
    entity_id: str | None = None,
    created_at: datetime | None = None,
) -> Operation:
    """Create an operation and stamp `created_at` (a server default in real life)."""
    operation = asyncio.run(
        operation_service.create(session, type, entity_type=entity_type, entity_id=entity_id)
    )
    if created_at is not None:
        operation.created_at = created_at
    return operation


def _ids(response_body: dict) -> list[str]:
    return [resource["id"] for resource in response_body["data"]]


def test_list_returns_the_pinned_resource_shape(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    operation = _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)
    asyncio.run(operation_service.start(fake_session, operation))
    asyncio.run(operation_service.advance(fake_session, operation, 65, "Processing images"))

    response = admin_client.get("/api/operations")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"] == {"totalCount": 1}
    resource = body["data"][0]
    assert resource["type"] == "operations"
    assert resource["id"] == operation.id
    assert set(resource["attributes"]) == OPERATION_ATTRIBUTES
    attributes = resource["attributes"]
    assert attributes["type"] == "demo"
    assert attributes["status"] == "running"
    assert attributes["progress"] == 65
    assert attributes["message"] == "Processing images"
    assert attributes["error"] is None
    assert attributes["entityType"] == MOTORBIKE_ENTITY_TYPE
    assert attributes["entityId"] == BIKE_ID
    assert attributes["startedAt"] is not None
    assert attributes["finishedAt"] is None


def test_list_is_newest_first(admin_client: TestClient, fake_session: FakeAsyncSession) -> None:
    older = _operation(fake_session, created_at=datetime(2026, 8, 26, 9, tzinfo=UTC))
    newer = _operation(fake_session, created_at=datetime(2026, 8, 26, 11, tzinfo=UTC))

    response = admin_client.get("/api/operations")

    assert _ids(response.json()) == [newer.id, older.id]


def test_list_filters_by_entity_id(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    mine = _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)
    _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=OTHER_BIKE_ID)

    response = admin_client.get("/api/operations", params={"filter[entityId]": BIKE_ID})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"totalCount": 1}
    assert _ids(body) == [mine.id]


def test_list_filters_by_entity_type(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    linked = _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)
    _operation(fake_session)

    response = admin_client.get(
        "/api/operations", params={"filter[entityType]": MOTORBIKE_ENTITY_TYPE}
    )

    assert _ids(response.json()) == [linked.id]


def test_list_filters_by_status(admin_client: TestClient, fake_session: FakeAsyncSession) -> None:
    queued = _operation(fake_session)
    finished = _operation(fake_session)
    asyncio.run(operation_service.succeed(fake_session, finished))

    response = admin_client.get("/api/operations", params={"filter[status]": "queued,running"})

    assert _ids(response.json()) == [queued.id]


def test_list_accepts_several_filters_at_once(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)

    response = admin_client.get(
        "/api/operations",
        params={
            "filter[entityType]": MOTORBIKE_ENTITY_TYPE,
            "filter[entityId]": OTHER_BIKE_ID,
            "filter[status]": OperationStatus.QUEUED.value,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"totalCount": 0}}


def test_list_rejects_an_unknown_status_filter_with_400_invalid_filter(
    admin_client: TestClient,
) -> None:
    response = admin_client.get("/api/operations", params={"filter[status]": "nonsense"})

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert errors[0]["status"] == "400"
    assert errors[0]["code"] == "invalid-filter"
    assert set(errors[0]) == {"status", "code", "detail"}


def test_list_paginates_and_reports_the_unpaginated_total(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    for hour in (9, 10, 11):
        _operation(fake_session, created_at=datetime(2026, 8, 26, hour, tzinfo=UTC))

    response = admin_client.get("/api/operations", params={"page[number]": 2, "page[size]": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"totalCount": 3}
    assert len(body["data"]) == 1


def test_list_page_size_above_the_maximum_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.get("/api/operations", params={"page[size]": 101})

    assert response.status_code == 422


def test_list_as_non_admin_returns_403(user_client: TestClient) -> None:
    response = user_client.get("/api/operations")

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin privileges required."}


def test_list_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        response = client.get("/api/operations")
    api.dependency_overrides.clear()

    assert response.status_code == 401


def test_the_resource_is_read_only(admin_client: TestClient) -> None:
    headers = {"X-CSRF-Token": admin_client.cookies["csrf_token"]}
    body = {"data": {"type": "operations", "attributes": {"type": "demo"}}}

    assert admin_client.post("/api/operations", json=body, headers=headers).status_code == 405
    assert admin_client.patch("/api/operations", json=body, headers=headers).status_code == 405
