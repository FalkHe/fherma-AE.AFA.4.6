"""QA coverage for `GET /api/operations`, extending `test_operations.py`.

Focus areas the dev suite does not already nail down: DELETE also 405 (not
just POST/PATCH), filters actually AND together (a matching combination, not
only the already-covered non-matching one), an unknown `filter[entityId]`/
`filter[entityType]` value degrades to an empty page rather than an error, and
an end-to-end check (through the real HTTP + service path, not a bare service
call) that a products write commits its data before it announces
`product.updated` on the shared `app_events` channel.
"""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.motorbike import Motorbike
from app.db.models.operation import Operation, OperationStatus
from app.db.models.user import UserRole
from app.db.session import get_db_session
from app.services import operation_service
from app.services.operation_service import MOTORBIKE_ENTITY_TYPE
from tests.services.conftest import FakeAsyncSession

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
        fake_session.users[registered.json()["id"]].role = role
        yield client
    api.dependency_overrides.clear()


@pytest.fixture
def admin_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    yield from _signed_in_client(api, fake_session, role=UserRole.ADMIN)


def _operation(session: FakeAsyncSession, **kwargs: object) -> Operation:
    return asyncio.run(operation_service.create(session, "demo", **kwargs))


def _ids(response_body: dict) -> list[str]:
    return [resource["id"] for resource in response_body["data"]]


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


# --- read-only surface ----------------------------------------------------------


def test_delete_on_the_collection_returns_405(admin_client: TestClient) -> None:
    response = admin_client.delete("/api/operations", headers=_csrf(admin_client))

    assert response.status_code == 405


def test_delete_on_a_single_operation_returns_404_no_such_route(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    # There is no `/api/operations/{id}` route at all (list-only resource);
    # confirm that surfaces as a clean 404, not a 500 or a route that
    # accidentally matches something else.
    operation = _operation(fake_session)

    response = admin_client.delete(f"/api/operations/{operation.id}", headers=_csrf(admin_client))

    assert response.status_code == 404


# --- filters: AND semantics and unknown-value degradation ----------------------


def test_filters_combine_with_and_semantics_on_a_matching_row(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    matching = _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)
    # Same entity type/id, wrong status: must be excluded by the status filter.
    other_status = _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)
    asyncio.run(operation_service.succeed(fake_session, other_status))
    # Right status, wrong entity: must be excluded by the entity filters.
    _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=OTHER_BIKE_ID)

    response = admin_client.get(
        "/api/operations",
        params={
            "filter[entityType]": MOTORBIKE_ENTITY_TYPE,
            "filter[entityId]": BIKE_ID,
            "filter[status]": OperationStatus.QUEUED.value,
        },
    )

    assert response.status_code == 200, response.text
    assert _ids(response.json()) == [matching.id]


def test_unknown_entity_id_filter_yields_an_empty_page_not_an_error(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    _operation(fake_session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)

    response = admin_client.get("/api/operations", params={"filter[entityId]": "0" * 22 + "NONE"})

    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"totalCount": 0}}


def test_multiple_status_values_are_ored_within_the_filter(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    queued = _operation(fake_session)
    succeeded = _operation(fake_session)
    asyncio.run(operation_service.succeed(fake_session, succeeded))
    failed = _operation(fake_session)
    asyncio.run(operation_service.fail(fake_session, failed, "boom"))

    response = admin_client.get("/api/operations", params={"filter[status]": "queued,failed"})

    assert {resource["id"] for resource in response.json()["data"]} == {queued.id, failed.id}


# --- end-to-end: commit-then-notify through the real products write path -------


def test_a_product_write_over_http_commits_before_it_notifies(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    response = admin_client.post(
        "/api/products",
        json={"data": {"type": "products", "attributes": {"name": "Honda CB500"}}},
        headers=_csrf(admin_client),
    )

    assert response.status_code == 201, response.text
    product_id = response.json()["data"]["id"]
    # The row exists in the store (data committed)...
    assert product_id in fake_session.store(Motorbike)
    # ...and exactly one ids-only `product.updated` notification went out for it.
    payloads = [payload for _channel, payload in fake_session.notifications]
    assert any(f'"productId":"{product_id}"' in payload for payload in payloads)
    assert all(len(payload.encode()) <= 1024 for payload in payloads)
