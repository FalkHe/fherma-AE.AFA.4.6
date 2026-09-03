"""QA behavioural coverage for the `products` JSON:API resource (step 2.3).

Complements `tests/api/test_products.py` rather than duplicating it: this file
targets the auth matrix on every route (including `GET /{id}`, and the
`anonymous` case on writes), the `verifiedSpec` write boundary, additional
illegal-transition pairs, pagination edge bounds, malformed JSON:API body
shapes, and the unknown-draft-spec-key boundary. Same fixture setup as
`test_products.py`: an in-memory `FakeAsyncSession` stands behind
`get_db_session`, so `product_service` really runs.
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


@pytest.fixture
def anon_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        yield client
    api.dependency_overrides.clear()


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _create(client: TestClient, name: str = "Suzuki GSR 600"):
    return client.post(
        "/api/products",
        json={"data": {"type": "products", "attributes": {"name": name}}},
        headers=_csrf(client),
    )


def _patch(client: TestClient, product_id: str, attributes: dict):
    return client.patch(
        f"/api/products/{product_id}",
        json={"data": {"type": "products", "attributes": attributes}},
        headers=_csrf(client),
    )


def _give_identity(fake_session: FakeAsyncSession, product_id: str) -> None:
    """Fill `manufacturer_id`/`model_name`/`year_from` directly (step 6.12's D4 guard).

    Bypasses `assign_identity` on purpose: these tests exercise the status
    workflow, not identity assignment, and there is no PATCH `identity` block
    to drive this through yet (that is step 6.20's).
    """
    manufacturer = Manufacturer(name="Suzuki", slug="suzuki")
    fake_session.add(manufacturer)
    motorbike = fake_session.store(Motorbike)[product_id]
    motorbike.manufacturer_id = manufacturer.id
    motorbike.model_name = "GSR 600"
    motorbike.year_from = 2011


def _assert_clean_error_body(response) -> None:
    """The body must be parseable JSON with no leaked traceback text."""
    body = response.json()
    assert "Traceback" not in response.text
    assert "traceback" not in response.text
    return body


# --- 1. Auth matrix on every route --------------------------------------------


def test_get_list_without_a_session_returns_401(anon_client: TestClient) -> None:
    response = anon_client.get("/api/products")
    assert response.status_code == 401
    assert _assert_clean_error_body(response) == {"detail": "Not authenticated."}


def test_get_by_id_without_a_session_returns_401(anon_client: TestClient) -> None:
    response = anon_client.get(f"/api/products/{'0' * 26}")
    assert response.status_code == 401
    assert _assert_clean_error_body(response) == {"detail": "Not authenticated."}


def test_get_by_id_as_non_admin_returns_403(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client).json()["data"]
    # Demote the very account that created the row (same pattern as
    # `test_patch_as_non_admin_returns_403` in test_products.py).
    fake_session.users[next(iter(fake_session.users))].role = UserRole.USER

    response = admin_client.get(f"/api/products/{created['id']}")

    assert response.status_code == 403
    assert _assert_clean_error_body(response) == {"detail": "Admin privileges required."}


def test_post_without_a_session_returns_401(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/api/products", json={"data": {"type": "products", "attributes": {"name": "Honda CB500"}}}
    )
    assert response.status_code == 401
    assert _assert_clean_error_body(response) == {"detail": "Not authenticated."}


def test_patch_without_a_session_returns_401(anon_client: TestClient) -> None:
    response = anon_client.patch(
        f"/api/products/{'0' * 26}",
        json={"data": {"type": "products", "attributes": {"status": "ingesting"}}},
    )
    assert response.status_code == 401
    assert _assert_clean_error_body(response) == {"detail": "Not authenticated."}


def test_admin_with_csrf_can_create_and_transition(admin_client: TestClient) -> None:
    """The success path of the matrix: admin + CSRF header succeeds end to end."""
    created = _create(admin_client).json()["data"]
    # Creation auto-starts the ingestion (step 2.14).
    assert created["attributes"]["status"] == "ingesting"

    response = _patch(admin_client, created["id"], {"status": "in_review"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["status"] == "in_review"


# --- 2. `verifiedSpec` can never be written ------------------------------------


def test_patch_rejects_snake_case_verified_spec_too(admin_client: TestClient) -> None:
    """`populate_by_name=True` accepts snake_case field names on other models;
    prove it does not open a back door here, since `verified_spec` is not a
    field on `ProductPatchAttributes` at all (`extra='forbid'` must still bite)."""
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"verified_spec": {"engineCc": 599}})

    assert response.status_code == 422
    _assert_clean_error_body(response)


def test_draft_spec_patch_never_touches_an_already_promoted_verified_spec(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client).json()["data"]
    product_id = created["id"]

    assert _patch(admin_client, product_id, {"draftSpec": {"engineCc": 599}}).status_code == 200
    assert _patch(admin_client, product_id, {"status": "in_review"}).status_code == 200
    _give_identity(fake_session, product_id)
    approved = _patch(admin_client, product_id, {"status": "approved"}).json()["data"]
    assert approved["attributes"]["verifiedSpec"]["engineCc"] == 599

    # A further draft edit must not reach the verified row.
    after_draft_edit = _patch(admin_client, product_id, {"draftSpec": {"engineCc": 750}}).json()[
        "data"
    ]

    assert after_draft_edit["attributes"]["draftSpec"]["engineCc"] == 750
    assert after_draft_edit["attributes"]["verifiedSpec"]["engineCc"] == 599


# --- 3. Transition matrix: additional illegal pairs ----------------------------


def test_patch_illegal_transition_ingesting_to_approved(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]
    product_id = created["id"]

    response = _patch(admin_client, product_id, {"status": "approved"})

    assert response.status_code == 422
    body = _assert_clean_error_body(response)
    assert body["errors"][0]["code"] == "invalid-transition"

    stored = admin_client.get(f"/api/products/{product_id}").json()
    assert stored["data"]["attributes"]["status"] == "ingesting"


def test_patch_illegal_transition_in_review_to_backlog(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]
    product_id = created["id"]
    assert _patch(admin_client, product_id, {"status": "in_review"}).status_code == 200

    response = _patch(admin_client, product_id, {"status": "backlog"})

    assert response.status_code == 422
    assert _assert_clean_error_body(response)["errors"][0]["code"] == "invalid-transition"

    stored = admin_client.get(f"/api/products/{product_id}").json()
    assert stored["data"]["attributes"]["status"] == "in_review"


def test_patch_illegal_transition_approved_has_no_legal_moves(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client).json()["data"]
    product_id = created["id"]
    assert _patch(admin_client, product_id, {"status": "in_review"}).status_code == 200
    _give_identity(fake_session, product_id)
    assert _patch(admin_client, product_id, {"status": "approved"}).status_code == 200

    response = _patch(admin_client, product_id, {"status": "rejected"})

    assert response.status_code == 422
    assert _assert_clean_error_body(response)["errors"][0]["code"] == "invalid-transition"

    stored = admin_client.get(f"/api/products/{product_id}").json()
    assert stored["data"]["attributes"]["status"] == "approved"


# --- 4. Duplicate name --------------------------------------------------------


def test_duplicate_name_does_not_create_a_second_row(admin_client: TestClient) -> None:
    assert _create(admin_client).status_code == 201
    assert _create(admin_client, name="SUZUKI gsr 600!!").status_code == 409

    response = admin_client.get("/api/products", params={"filter[status]": "ingesting"})

    assert response.json()["meta"] == {"totalCount": 1}


# --- 5. Pagination bounds ------------------------------------------------------


def test_list_page_size_zero_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.get("/api/products", params={"page[size]": 0})
    assert response.status_code == 422
    _assert_clean_error_body(response)


def test_list_page_number_zero_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.get("/api/products", params={"page[number]": 0})
    assert response.status_code == 422
    _assert_clean_error_body(response)


def test_list_unknown_status_filter_is_not_a_500(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/products", params={"filter[status]": "backlog,not-a-real-status"}
    )
    assert response.status_code == 400
    body = _assert_clean_error_body(response)
    assert body["errors"][0]["code"] == "invalid-filter"


# --- 6. draftSpec camelCase round-trip: null handling and unknown keys ---------


def test_patch_draft_spec_unknown_key_is_rejected_not_500_not_dropped(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(
        admin_client, created["id"], {"draftSpec": {"engineCc": 599, "wingspanMm": 10}}
    )

    assert response.status_code == 422
    body = _assert_clean_error_body(response)
    assert "detail" in body

    # And the row was not silently written with the recognised field either.
    stored = admin_client.get(f"/api/products/{created['id']}").json()
    assert stored["data"]["attributes"]["draftSpec"] is None


def test_patch_draft_spec_explicit_null_resets_the_field(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]
    product_id = created["id"]
    assert _patch(admin_client, product_id, {"draftSpec": {"engineCc": 599}}).status_code == 200

    response = _patch(admin_client, product_id, {"draftSpec": {"engineCc": None, "cylinders": 4}})

    assert response.status_code == 200, response.text
    draft = response.json()["data"]["attributes"]["draftSpec"]
    assert draft["engineCc"] is None
    assert draft["cylinders"] == 4


# --- 7. Malformed JSON:API body shapes ------------------------------------------


def test_post_missing_data_key_returns_422_not_500(admin_client: TestClient) -> None:
    response = admin_client.post("/api/products", json={}, headers=_csrf(admin_client))
    assert response.status_code == 422
    _assert_clean_error_body(response)


def test_post_wrong_resource_type_returns_422_not_500(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/products",
        json={"data": {"type": "widgets", "attributes": {"name": "Honda CB500"}}},
        headers=_csrf(admin_client),
    )
    assert response.status_code == 422
    _assert_clean_error_body(response)


def test_patch_body_with_an_id_field_is_rejected_not_500(admin_client: TestClient) -> None:
    """The resource object schema carries no `id` (identity comes from the URL
    path only); an id smuggled into the body must be a clean 422, not silently
    accepted or a 500."""
    created = _create(admin_client).json()["data"]

    response = admin_client.patch(
        f"/api/products/{created['id']}",
        json={
            "data": {
                "id": "0" * 26,
                "type": "products",
                "attributes": {"status": "ingesting"},
            }
        },
        headers=_csrf(admin_client),
    )

    assert response.status_code == 422
    _assert_clean_error_body(response)


def test_patch_missing_data_key_returns_422_not_500(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = admin_client.patch(
        f"/api/products/{created['id']}", json={"notData": True}, headers=_csrf(admin_client)
    )

    assert response.status_code == 422
    _assert_clean_error_body(response)
