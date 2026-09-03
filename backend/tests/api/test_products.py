"""Behavioural tests for the `products` JSON:API resource.

Same setup as `test_auth.py`: the in-memory `FakeAsyncSession` stands behind
`get_db_session`, so `product_service` really runs — rows are really created,
the transition matrix is really enforced and specification upserts really
persist. The admin client registers and logs in through `/auth/*` and is then
promoted in the store, because `current_admin` reads the role fresh per request.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike
from app.db.models.operation import Operation, OperationStatus
from app.db.models.user import UserRole
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession

PRODUCT_ATTRIBUTES = {
    "name",
    "slug",
    "queryName",
    "manufacturer",
    "buildingline",
    "modelName",
    "yearFrom",
    "yearTo",
    "typeCodes",
    "variants",
    "suggestion",
    "status",
    "draftSpec",
    "verifiedSpec",
    "createdAt",
    "updatedAt",
}

SPEC_ATTRIBUTES = {
    "category",
    "engineCc",
    "cylinders",
    "powerKw",
    "torqueNm",
    "wetWeightKg",
    "seatHeightMm",
    "tankCapacityL",
    "topSpeedKmh",
    "abs",
    "a2Eligible",
    "priceBand",
    "msrpEur",
    "extra",
    "sourceHints",
    "extractedAt",
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


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _create(client: TestClient, name: str = "Suzuki GSR 600"):
    return client.post(
        "/api/products",
        json={"data": {"type": "products", "attributes": {"name": name}}},
        headers=_csrf(client),
    )


def _assign_manufacturer(
    fake_session: FakeAsyncSession, product_id: str, name: str = "Suzuki"
) -> Manufacturer:
    """Give a stored catalogue row a brand, as extraction or the CLI would.

    The attribute is derived since Phase 2b: only the foreign key is stored, so
    a fixture has to create the `manufacturers` row it points at.
    """
    manufacturer = Manufacturer(name=name, slug=name.lower())
    fake_session.add(manufacturer)
    fake_session.store(Motorbike)[product_id].manufacturer_id = manufacturer.id
    return manufacturer


def _create_manufacturer(fake_session: FakeAsyncSession, name: str = "Suzuki") -> Manufacturer:
    """Store a brand row without attaching it to any product (6.20 identity tests)."""
    manufacturer = Manufacturer(name=name, slug=name.lower())
    fake_session.add(manufacturer)
    return manufacturer


def _patch(client: TestClient, product_id: str, attributes: dict):
    return client.patch(
        f"/api/products/{product_id}",
        json={"data": {"type": "products", "attributes": attributes}},
        headers=_csrf(client),
    )


# --- POST /api/products -------------------------------------------------------


def test_create_returns_201_json_api_document_for_an_ingesting_row(
    admin_client: TestClient,
) -> None:
    response = _create(admin_client)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {"data"}
    resource = body["data"]
    assert resource["type"] == "products"
    assert len(resource["id"]) == 26
    assert set(resource["attributes"]) == PRODUCT_ATTRIBUTES
    assert resource["attributes"]["name"] == "Suzuki GSR 600"
    assert resource["attributes"]["slug"] == "suzuki-gsr-600"
    # Adding a model auto-starts its ingestion (step 2.14).
    assert resource["attributes"]["status"] == "ingesting"
    assert resource["attributes"]["draftSpec"] is None
    assert resource["attributes"]["verifiedSpec"] is None
    assert resource["attributes"]["createdAt"] is not None


def test_create_enqueues_the_ingestion_job_for_a_queued_operation(
    admin_client: TestClient,
    fake_session: FakeAsyncSession,
    recorded_enqueues: list[tuple[str, str]],
) -> None:
    product_id = _create(admin_client).json()["data"]["id"]

    operations = fake_session.rows(Operation)
    assert [
        (operation.type, operation.status, operation.entity_id) for operation in operations
    ] == [("ingestion", OperationStatus.QUEUED, product_id)]
    # The task is enqueued after both commits, with ids only.
    assert recorded_enqueues == [(product_id, operations[0].id)]


def test_patch_to_ingesting_re_enqueues_the_job(
    admin_client: TestClient, recorded_enqueues: list[tuple[str, str]]
) -> None:
    created = _create(admin_client).json()["data"]
    for target in ("in_review", "rejected"):
        assert _patch(admin_client, created["id"], {"status": target}).status_code == 200

    response = _patch(admin_client, created["id"], {"status": "ingesting"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["status"] == "ingesting"
    assert [motorbike_id for motorbike_id, _ in recorded_enqueues] == [
        created["id"],
        created["id"],
    ]


def test_create_duplicate_name_returns_409_duplicate_model(admin_client: TestClient) -> None:
    assert _create(admin_client).status_code == 201

    response = _create(admin_client, name="suzuki  GSR-600")

    assert response.status_code == 409
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["status"] == "409"
    assert errors[0]["code"] == "duplicate-model"
    assert "suzuki-gsr-600" in errors[0]["detail"]


def test_create_without_csrf_header_returns_403(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/products", json={"data": {"type": "products", "attributes": {"name": "Honda CB500"}}}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}


def test_create_as_non_admin_returns_403(user_client: TestClient) -> None:
    response = _create(user_client)

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin privileges required."}


def test_create_with_a_name_without_slug_characters_returns_422(admin_client: TestClient) -> None:
    response = _create(admin_client, name="   ???   ")

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "name") in locs


# --- GET /api/products --------------------------------------------------------


def test_list_returns_the_created_row_when_filtered_by_status(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = admin_client.get("/api/products", params={"filter[status]": "ingesting"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"totalCount": 1}
    assert [resource["id"] for resource in body["data"]] == [created["id"]]
    assert set(body["data"][0]["attributes"]) == PRODUCT_ATTRIBUTES


def test_list_filter_excludes_other_statuses(admin_client: TestClient) -> None:
    _create(admin_client)

    response = admin_client.get("/api/products", params={"filter[status]": "approved,in_review"})

    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"totalCount": 0}}


def test_list_rejects_an_unknown_status_filter_with_400_invalid_filter(
    admin_client: TestClient,
) -> None:
    response = admin_client.get("/api/products", params={"filter[status]": "nonsense"})

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "invalid-filter"


def test_list_page_size_above_the_maximum_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.get("/api/products", params={"page[size]": 101})

    assert response.status_code == 422


def test_list_paginates_and_reports_the_unpaginated_total(admin_client: TestClient) -> None:
    for name in ("Honda CB500", "Yamaha MT-07", "KTM 390 Duke"):
        assert _create(admin_client, name=name).status_code == 201

    response = admin_client.get("/api/products", params={"page[number]": 2, "page[size]": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"totalCount": 3}
    assert len(body["data"]) == 1


def test_list_as_non_admin_returns_403(user_client: TestClient) -> None:
    response = user_client.get("/api/products")

    assert response.status_code == 403


def test_list_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        response = client.get("/api/products")
    api.dependency_overrides.clear()

    assert response.status_code == 401


# --- GET /api/products/{id} ---------------------------------------------------


def test_get_returns_the_product(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = admin_client.get(f"/api/products/{created['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


def test_manufacturer_is_the_related_rows_name_and_null_without_one(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client).json()["data"]
    # A fresh row has no brand yet.
    assert created["attributes"]["manufacturer"] is None

    _assign_manufacturer(fake_session, created["id"])

    detail = admin_client.get(f"/api/products/{created['id']}").json()["data"]
    listed = admin_client.get("/api/products").json()["data"][0]
    assert detail["attributes"]["manufacturer"] == "Suzuki"
    assert listed["attributes"]["manufacturer"] == "Suzuki"
    # Still the pinned attribute set — no relationships, no extra attribute.
    assert set(detail["attributes"]) == PRODUCT_ATTRIBUTES


def test_get_unknown_id_returns_404_in_the_error_document_shape(admin_client: TestClient) -> None:
    response = admin_client.get(f"/api/products/{'0' * 26}")

    assert response.status_code == 404
    errors = response.json()["errors"]
    assert errors[0]["status"] == "404"
    assert errors[0]["code"] == "not-found"
    assert set(errors[0]) == {"status", "code", "detail"}


# --- PATCH /api/products/{id} -------------------------------------------------


def test_patch_illegal_status_returns_422_invalid_transition(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"status": "approved"})

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert errors[0]["status"] == "422"
    assert errors[0]["code"] == "invalid-transition"
    assert "ingesting" in errors[0]["detail"]

    # The row is untouched.
    stored = admin_client.get(f"/api/products/{created['id']}").json()
    assert stored["data"]["attributes"]["status"] == "ingesting"


def test_patch_approve_without_identity_returns_422_incomplete_identity(
    admin_client: TestClient,
) -> None:
    """D4 (step 6.12): an `in_review` row with no manufacturer/model/year
    cannot be approved — the API maps `IncompleteIdentityError` to 422
    `incomplete-identity`, distinct from `invalid-transition`.
    """
    created = _create(admin_client).json()["data"]
    assert _patch(admin_client, created["id"], {"status": "in_review"}).status_code == 200

    response = _patch(admin_client, created["id"], {"status": "approved"})

    assert response.status_code == 422
    errors = response.json()["errors"]
    assert errors[0]["status"] == "422"
    assert errors[0]["code"] == "incomplete-identity"

    # The row is untouched.
    stored = admin_client.get(f"/api/products/{created['id']}").json()
    assert stored["data"]["attributes"]["status"] == "in_review"


def test_patch_legal_status_transitions_the_row(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"status": "in_review"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["status"] == "in_review"


def test_patch_draft_spec_persists_and_echoes_camel_case(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(
        admin_client,
        created["id"],
        {
            "draftSpec": {
                "category": "naked",
                "engineCc": 599,
                "powerKw": 72.0,
                "wetWeightKg": 208.0,
                "seatHeightMm": 785,
                "tankCapacityL": 16.5,
                "priceBand": "budget",
                "extra": {"frame": "steel"},
            }
        },
    )

    assert response.status_code == 200, response.text
    draft = response.json()["data"]["attributes"]["draftSpec"]
    assert set(draft) == SPEC_ATTRIBUTES
    assert draft["engineCc"] == 599
    assert draft["powerKw"] == 72.0
    assert draft["tankCapacityL"] == 16.5
    assert draft["priceBand"] == "budget"
    assert draft["extra"] == {"frame": "steel"}
    # Derived because the incoming value was null: 72 kW is beyond the A2 limit.
    assert draft["a2Eligible"] is False
    # Omitted fields of the frozen set are reset, not missing.
    assert draft["torqueNm"] is None

    reread = admin_client.get(f"/api/products/{created['id']}").json()
    assert reread["data"]["attributes"]["draftSpec"] == draft
    assert reread["data"]["attributes"]["verifiedSpec"] is None


def test_patch_draft_spec_replaces_the_whole_object(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]
    assert _patch(admin_client, created["id"], {"draftSpec": {"engineCc": 599}}).status_code == 200

    response = _patch(admin_client, created["id"], {"draftSpec": {"cylinders": 4}})

    draft = response.json()["data"]["attributes"]["draftSpec"]
    assert draft["cylinders"] == 4
    assert draft["engineCc"] is None


def test_patch_rejects_verified_spec_in_the_payload(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"verifiedSpec": {"engineCc": 599}})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "verifiedSpec") in locs


def test_patch_rejects_an_out_of_vocabulary_category(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"draftSpec": {"category": "hovercraft"}})

    assert response.status_code == 422


def test_patch_rejects_a_negative_number(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"draftSpec": {"engineCc": -1}})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "draftSpec", "engineCc") in locs


# --- draftSpec.extra / sourceHints size caps (5.5) ------------------------------


def test_patch_draft_spec_extra_at_the_key_count_ceiling_is_accepted(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]
    extra = {f"k{i}": "x" for i in range(50)}

    response = _patch(admin_client, created["id"], {"draftSpec": {"extra": extra}})

    assert response.status_code == 200, response.text


def test_patch_draft_spec_extra_beyond_the_key_count_ceiling_returns_422(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]
    extra = {f"k{i}": "x" for i in range(51)}

    response = _patch(admin_client, created["id"], {"draftSpec": {"extra": extra}})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "draftSpec", "extra") in locs


def test_patch_draft_spec_source_hints_beyond_the_key_count_ceiling_returns_422(
    admin_client: TestClient,
) -> None:
    """The same validator guards `sourceHints`, not only `extra`."""
    created = _create(admin_client).json()["data"]
    source_hints = {f"k{i}": "x" for i in range(51)}

    response = _patch(admin_client, created["id"], {"draftSpec": {"sourceHints": source_hints}})

    assert response.status_code == 422


def test_patch_draft_spec_extra_key_at_the_length_ceiling_is_accepted(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"draftSpec": {"extra": {"k" * 64: "x"}}})

    assert response.status_code == 200, response.text


def test_patch_draft_spec_extra_key_beyond_the_length_ceiling_returns_422(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"draftSpec": {"extra": {"k" * 65: "x"}}})

    assert response.status_code == 422


def test_patch_draft_spec_extra_value_at_the_length_ceiling_is_accepted(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]
    # `json.dumps` adds the two quote characters, so 1998 + 2 == 2000.
    extra = {"k": "x" * 1998}

    response = _patch(admin_client, created["id"], {"draftSpec": {"extra": extra}})

    assert response.status_code == 200, response.text


def test_patch_draft_spec_extra_value_beyond_the_length_ceiling_returns_422(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]
    extra = {"k": "x" * 1999}

    response = _patch(admin_client, created["id"], {"draftSpec": {"extra": extra}})

    assert response.status_code == 422


def test_patch_without_csrf_header_returns_403(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = admin_client.patch(
        f"/api/products/{created['id']}",
        json={"data": {"type": "products", "attributes": {"status": "ingesting"}}},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}


def test_patch_as_non_admin_returns_403(
    api: FastAPI, fake_session: FakeAsyncSession, admin_client: TestClient
) -> None:
    created = _create(admin_client).json()["data"]
    # Demote the very account that created the row.
    fake_session.users[next(iter(fake_session.users))].role = UserRole.USER

    response = _patch(admin_client, created["id"], {"status": "ingesting"})

    assert response.status_code == 403


def test_patch_unknown_id_returns_404(admin_client: TestClient) -> None:
    response = _patch(admin_client, "0" * 26, {"status": "ingesting"})

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"


# --- PATCH identity (step 6.20, D2) -------------------------------------------


def test_patch_identity_recomputes_the_slug_and_echoes_the_block(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client, name="Yamaha MT-07").json()["data"]
    yamaha = _create_manufacturer(fake_session, "Yamaha")

    response = _patch(
        admin_client,
        created["id"],
        {
            "identity": {
                "manufacturerId": yamaha.id,
                "buildingline": "MT",
                "modelName": "MT-07",
                "yearFrom": 2014,
                "yearTo": None,
                "typeCodes": ["RM04", "RM17", "RM33"],
                "variants": [],
            }
        },
    )

    assert response.status_code == 200, response.text
    attributes = response.json()["data"]["attributes"]
    assert attributes["slug"] == "yamaha/mt-07/2014-"
    assert attributes["buildingline"] == "MT"
    assert attributes["modelName"] == "MT-07"
    assert attributes["yearFrom"] == 2014
    assert attributes["yearTo"] is None
    assert attributes["typeCodes"] == ["RM04", "RM17", "RM33"]
    assert attributes["variants"] == []
    assert attributes["name"] == "Yamaha MT-07"
    assert attributes["queryName"] == "Yamaha MT-07"

    # Persisted, not just echoed.
    reread = admin_client.get(f"/api/products/{created['id']}").json()["data"]["attributes"]
    assert reread["slug"] == "yamaha/mt-07/2014-"


def test_patch_identity_with_a_variant_persists_the_delta_and_recomputes_its_slug(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client, name="Honda Africa Twin").json()["data"]
    honda = _create_manufacturer(fake_session, "Honda")

    response = _patch(
        admin_client,
        created["id"],
        {
            "identity": {
                "manufacturerId": honda.id,
                "modelName": "Africa Twin",
                "yearFrom": 2020,
                # The client never sends a trim `slug` (D1) — recomputed here.
                "variants": [
                    {
                        "name": "Adventure Sports",
                        "description": "Larger tank, crash bars.",
                        "specs": {"tank_capacity_l": 24.8},
                    }
                ],
            }
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["variants"] == [
        {
            "slug": "adventure-sports",
            "name": "Adventure Sports",
            "description": "Larger tank, crash bars.",
            "specs": {"tank_capacity_l": 24.8},
        }
    ]


def test_patch_identity_collision_returns_409_duplicate_model(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    ktm = _create_manufacturer(fake_session, "KTM")
    existing = _create(admin_client, name="KTM 390 Duke").json()["data"]
    assert (
        _patch(
            admin_client,
            existing["id"],
            {"identity": {"manufacturerId": ktm.id, "modelName": "390 Duke", "yearFrom": 2017}},
        ).status_code
        == 200
    )
    other = _create(admin_client, name="KTM 390 Duke Gen3").json()["data"]

    response = _patch(
        admin_client,
        other["id"],
        {"identity": {"manufacturerId": ktm.id, "modelName": "390 Duke", "yearFrom": 2017}},
    )

    assert response.status_code == 409
    errors = response.json()["errors"]
    assert errors[0]["code"] == "duplicate-model"
    assert "ktm/390-duke/2017-" in errors[0]["detail"]

    # Neither row was written: the collision check runs before any attribute is.
    stored = admin_client.get(f"/api/products/{other['id']}").json()["data"]["attributes"]
    assert stored["modelName"] is None


def test_patch_identity_bad_year_pair_returns_422_with_a_field_pointer(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"identity": {"yearFrom": 2020, "yearTo": 2010}})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "identity") in locs


def test_patch_identity_year_below_the_minimum_returns_422_with_a_field_pointer(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"identity": {"yearFrom": 1800}})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "identity", "yearFrom") in locs


def test_patch_identity_unknown_manufacturer_returns_422_with_a_field_pointer(
    admin_client: TestClient,
) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(
        admin_client,
        created["id"],
        {"identity": {"manufacturerId": "0" * 26, "modelName": "X", "yearFrom": 2020}},
    )

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "identity", "manufacturerId") in locs

    # Nothing was written: existence is checked before `assign_identity` runs.
    stored = admin_client.get(f"/api/products/{created['id']}").json()["data"]["attributes"]
    assert stored["modelName"] is None


def test_patch_identity_bad_type_code_returns_422(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = _patch(admin_client, created["id"], {"identity": {"typeCodes": ["not a code!"]}})

    assert response.status_code == 422


def test_patch_identity_then_approve_in_the_same_call_succeeds(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    """D2: identity is applied before status, so fill-and-approve is one call."""
    created = _create(admin_client, name="Suzuki SV650").json()["data"]
    suzuki = _create_manufacturer(fake_session, "Suzuki")
    assert _patch(admin_client, created["id"], {"status": "in_review"}).status_code == 200

    response = _patch(
        admin_client,
        created["id"],
        {
            "identity": {"manufacturerId": suzuki.id, "modelName": "SV650", "yearFrom": 1999},
            "status": "approved",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["status"] == "approved"


def test_patch_identity_without_csrf_header_returns_403(admin_client: TestClient) -> None:
    created = _create(admin_client).json()["data"]

    response = admin_client.patch(
        f"/api/products/{created['id']}",
        json={
            "data": {
                "type": "products",
                "attributes": {"identity": {"modelName": "X", "yearFrom": 2020}},
            }
        },
    )

    assert response.status_code == 403


# --- `suggestion` (D6) ---------------------------------------------------------

_SUGGESTION = {
    "source": "bike-list.txt",
    "raw": "BMW R 1200 GS (2004–2018) [K25/K50]",
    "manufacturer": "BMW",
    "model": "R 1200 GS",
    "year_from": 2004,
    "year_to": 2018,
    "in_production": False,
    "year_ranges": [{"from": 2004, "to": 2018}],
    "type_codes": ["K25", "K50"],
    "links": ["https://en.wikipedia.org/wiki/BMW_R1200GS"],
}


def test_get_returns_the_suggestion_claim_camel_cased(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    created = _create(admin_client).json()["data"]
    # No suggestion until one is set: a plain admin-added row never has one.
    assert created["attributes"]["suggestion"] is None
    fake_session.store(Motorbike)[created["id"]].suggestion = dict(_SUGGESTION)

    response = admin_client.get(f"/api/products/{created['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["suggestion"] == {
        "source": "bike-list.txt",
        "raw": "BMW R 1200 GS (2004–2018) [K25/K50]",
        "manufacturer": "BMW",
        "model": "R 1200 GS",
        "yearFrom": 2004,
        "yearTo": 2018,
        "inProduction": False,
        "yearRanges": [{"from": 2004, "to": 2018}],
        "typeCodes": ["K25", "K50"],
        "links": ["https://en.wikipedia.org/wiki/BMW_R1200GS"],
    }
