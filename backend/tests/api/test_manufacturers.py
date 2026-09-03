"""Behavioural tests for the read-only `manufacturers` JSON:API resource.

Same setup as `test_operations.py`: the in-memory `FakeAsyncSession` stands
behind `get_db_session`, so `manufacturer_service` really runs — ordering,
pagination and the total come out of the store, not out of a mock. Rows are
seeded directly, because no HTTP path creates a manufacturer; that absence is
itself part of the contract.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike
from app.db.models.user import UserRole
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession

MANUFACTURER_ATTRIBUTES = {
    "name",
    "slug",
    "description",
    "logoPath",
    "createdAt",
    "updatedAt",
}


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


def _seed(session: FakeAsyncSession, *names: str) -> list[Manufacturer]:
    """Store one brand per name, as `get_or_create` would."""
    rows = [Manufacturer(name=name, slug=name.lower().replace(" ", "-")) for name in names]
    for row in rows:
        session.add(row)
    return rows


# --- GET /api/manufacturers ---------------------------------------------------


def test_list_returns_the_brands_sorted_by_name(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    _seed(fake_session, "Suzuki", "Honda", "BMW")

    response = admin_client.get("/api/manufacturers")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"] == {"totalCount": 3}
    assert [resource["attributes"]["name"] for resource in body["data"]] == [
        "BMW",
        "Honda",
        "Suzuki",
    ]
    assert {resource["type"] for resource in body["data"]} == {"manufacturers"}


def test_list_paginates_within_the_sorted_order(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    _seed(fake_session, "Suzuki", "Honda", "BMW")

    response = admin_client.get("/api/manufacturers", params={"page[number]": 2, "page[size]": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    # `totalCount` stays the unpaginated total.
    assert body["meta"] == {"totalCount": 3}
    assert [resource["attributes"]["name"] for resource in body["data"]] == ["Suzuki"]


def test_list_page_size_above_the_maximum_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.get("/api/manufacturers", params={"page[size]": 101})

    assert response.status_code == 422


def test_list_as_plain_user_returns_the_same_brands(
    user_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    """Since Phase 4 the brand list is readable by any signed-in account (D2)."""
    _seed(fake_session, "Suzuki", "Honda")

    response = user_client.get("/api/manufacturers")

    assert response.status_code == 200, response.text
    assert [resource["attributes"]["name"] for resource in response.json()["data"]] == [
        "Honda",
        "Suzuki",
    ]


def test_list_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as anonymous:
        response = anonymous.get("/api/manufacturers")
    api.dependency_overrides.clear()

    assert response.status_code == 401


# --- GET /api/manufacturers/{id} ----------------------------------------------


def test_get_returns_the_pinned_attributes(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    stored = _seed(fake_session, "Suzuki")[0]

    response = admin_client.get(f"/api/manufacturers/{stored.id}")

    assert response.status_code == 200, response.text
    resource = response.json()["data"]
    assert resource["type"] == "manufacturers"
    assert resource["id"] == stored.id
    assert set(resource["attributes"]) == MANUFACTURER_ATTRIBUTES
    assert resource["attributes"]["name"] == "Suzuki"
    assert resource["attributes"]["slug"] == "suzuki"
    # Neither column has a writer yet.
    assert resource["attributes"]["description"] is None
    assert resource["attributes"]["logoPath"] is None
    assert resource["attributes"]["createdAt"] is not None


def test_get_unknown_id_returns_404_not_found(admin_client: TestClient) -> None:
    response = admin_client.get("/api/manufacturers/" + "0" * 26)

    assert response.status_code == 404
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["status"] == "404"
    assert errors[0]["code"] == "not-found"


def test_get_as_plain_user_returns_the_brand(
    user_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    stored = _seed(fake_session, "Suzuki")[0]

    response = user_client.get(f"/api/manufacturers/{stored.id}")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == stored.id


# --- No write routes ----------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_writes_are_not_routed(
    admin_client: TestClient, fake_session: FakeAsyncSession, method: str
) -> None:
    stored = _seed(fake_session, "Suzuki")[0]
    collection = admin_client.request(method, "/api/manufacturers")
    detail = admin_client.request(method, f"/api/manufacturers/{stored.id}")

    assert collection.status_code == 405
    assert detail.status_code == 405


# --- GET /api/manufacturers/{id}/buildinglines (step 6.20, ui-spec API-5) -----


def _seed_motorbike_with_buildingline(
    session: FakeAsyncSession, manufacturer_id: str, name: str, buildingline: str | None
) -> Motorbike:
    motorbike = Motorbike(
        query_name=name,
        slug=name.lower().replace(" ", "-"),
        manufacturer_id=manufacturer_id,
        buildingline=buildingline,
    )
    session.add(motorbike)
    return motorbike


def test_buildinglines_returns_the_distinct_sorted_values(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    bmw = _seed(fake_session, "BMW")[0]
    _seed_motorbike_with_buildingline(fake_session, bmw.id, "BMW R 1250 RT", "RT")
    _seed_motorbike_with_buildingline(fake_session, bmw.id, "BMW R 1250 GS", "GS")
    _seed_motorbike_with_buildingline(fake_session, bmw.id, "BMW R 1300 GS", "GS")
    _seed_motorbike_with_buildingline(fake_session, bmw.id, "BMW F 900 R", None)
    other = _seed(fake_session, "Honda")[0]
    _seed_motorbike_with_buildingline(fake_session, other.id, "Honda Africa Twin", "Africa Twin")

    response = admin_client.get(f"/api/manufacturers/{bmw.id}/buildinglines")

    assert response.status_code == 200, response.text
    assert response.json() == {"data": ["GS", "RT"]}


def test_buildinglines_unknown_manufacturer_returns_404(admin_client: TestClient) -> None:
    response = admin_client.get(f"/api/manufacturers/{'0' * 26}/buildinglines")

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"


def test_buildinglines_as_non_admin_returns_403(
    user_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    """Admin-only, unlike the rest of this router (D2's `current_user` relax)."""
    bmw = _seed(fake_session, "BMW")[0]

    response = user_client.get(f"/api/manufacturers/{bmw.id}/buildinglines")

    assert response.status_code == 403


def test_buildinglines_without_a_session_returns_401(
    api: FastAPI, fake_session: FakeAsyncSession
) -> None:
    bmw = _seed(fake_session, "BMW")[0]
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as anonymous:
        response = anonymous.get(f"/api/manufacturers/{bmw.id}/buildinglines")
    api.dependency_overrides.clear()

    assert response.status_code == 401
