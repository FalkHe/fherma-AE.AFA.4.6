"""Behavioural tests for the `product-images` JSON:API resource.

Same setup as `test_documents.py`: the in-memory `FakeAsyncSession` stands
behind `get_db_session`, so `product_service` really runs and the moderation
matrix is really enforced. Image rows are seeded straight into the store —
ingestion writes them (step 2.12), no HTTP path creates one.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.user import UserRole
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession

IMAGE_ATTRIBUTES = {"sourceUrl", "attribution", "status", "variants", "createdAt"}

BIKE_ID = "0" * 22 + "BIKE"
OTHER_BIKE_ID = "0" * 22 + "OTHR"

SOURCE_URL = "https://upload.wikimedia.invalid/Suzuki_GSR600.jpg"
ATTRIBUTION = "Jane Doe · CC BY-SA 4.0 · https://creativecommons.invalid/by-sa/4.0"


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


def _image(
    session: FakeAsyncSession,
    *,
    motorbike_id: str = BIKE_ID,
    status: ImageStatus = ImageStatus.PENDING,
    attribution: str | None = ATTRIBUTION,
    created_at: datetime = datetime(2026, 8, 26, 11, tzinfo=UTC),
) -> MotorbikeImage:
    """Seed one image row; `status` and `created_at` are database defaults in real life."""
    image = MotorbikeImage(
        motorbike_id=motorbike_id,
        source_url=SOURCE_URL,
        attribution=attribution,
        status=status,
        original_path=f"motorbikes/{motorbike_id}/original.jpg",
        created_at=created_at,
    )
    session.add(image)
    return image


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _patch(client: TestClient, image_id: str, attributes: dict):
    return client.patch(
        f"/api/product-images/{image_id}",
        json={"data": {"type": "product-images", "attributes": attributes}},
        headers=_csrf(client),
    )


def _ids(response_body: dict) -> list[str]:
    return [resource["id"] for resource in response_body["data"]]


# --- GET /api/product-images --------------------------------------------------


def test_list_returns_the_pinned_resource_shape(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = admin_client.get("/api/product-images", params={"filter[product]": BIKE_ID})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"] == {"totalCount": 1}
    resource = body["data"][0]
    assert resource["type"] == "product-images"
    assert resource["id"] == image.id
    assert set(resource["attributes"]) == IMAGE_ATTRIBUTES
    attributes = resource["attributes"]
    assert attributes["sourceUrl"] == SOURCE_URL
    assert attributes["attribution"] == ATTRIBUTION
    assert attributes["status"] == "pending"
    assert attributes["createdAt"].startswith("2026-08-26T11:00")


def test_list_computes_the_pinned_variant_urls(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = admin_client.get("/api/product-images", params={"filter[product]": BIKE_ID})

    variants = response.json()["data"][0]["attributes"]["variants"]
    assert variants == {
        "thumb": f"/media/motorbikes/{BIKE_ID}/{image.id}_thumb.webp",
        "card": f"/media/motorbikes/{BIKE_ID}/{image.id}_card.webp",
        "detail": f"/media/motorbikes/{BIKE_ID}/{image.id}_detail.webp",
    }


def test_list_is_newest_first_and_filtered_by_product(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    older = _image(fake_session, created_at=datetime(2026, 8, 26, 9, tzinfo=UTC))
    newer = _image(fake_session, created_at=datetime(2026, 8, 26, 11, tzinfo=UTC))
    _image(fake_session, motorbike_id=OTHER_BIKE_ID)

    response = admin_client.get("/api/product-images", params={"filter[product]": BIKE_ID})

    assert _ids(response.json()) == [newer.id, older.id]


def test_list_with_several_products_returns_400_invalid_filter(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/product-images", params={"filter[product]": f"{BIKE_ID},{OTHER_BIKE_ID}"}
    )

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert errors[0]["code"] == "invalid-filter"
    assert set(errors[0]) == {"status", "code", "detail"}


def test_list_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        response = client.get("/api/product-images")
    api.dependency_overrides.clear()

    assert response.status_code == 401


def test_list_as_non_admin_returns_403(user_client: TestClient) -> None:
    response = user_client.get("/api/product-images", params={"filter[product]": BIKE_ID})

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin privileges required."}


# --- PATCH /api/product-images/{id} -------------------------------------------


def test_patch_rejects_a_pending_image_and_announces_the_product(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)
    notifications_before = len(fake_session.notifications)

    response = _patch(admin_client, image.id, {"status": "rejected"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data"}
    assert body["data"]["attributes"]["status"] == "rejected"
    assert image.status is ImageStatus.REJECTED
    assert fake_session.notifications[notifications_before:] == [
        ("app_events", f'{{"event":"product.updated","productId":"{BIKE_ID}"}}')
    ]


def test_patch_approves_a_pending_image(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = _patch(admin_client, image.id, {"status": "approved"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["status"] == "approved"


def test_patch_rejects_an_approved_image(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session, status=ImageStatus.APPROVED)

    response = _patch(admin_client, image.id, {"status": "rejected"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["status"] == "rejected"


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (ImageStatus.PENDING, "pending"),
        (ImageStatus.APPROVED, "pending"),
        (ImageStatus.APPROVED, "approved"),
        (ImageStatus.REJECTED, "pending"),
        (ImageStatus.REJECTED, "approved"),
        (ImageStatus.REJECTED, "rejected"),
    ],
)
def test_patch_with_an_illegal_transition_returns_422_invalid_transition(
    admin_client: TestClient, fake_session: FakeAsyncSession, current: ImageStatus, requested: str
) -> None:
    image = _image(fake_session, status=current)

    response = _patch(admin_client, image.id, {"status": requested})

    assert response.status_code == 422, response.text
    errors = response.json()["errors"]
    assert errors[0]["status"] == "422"
    assert errors[0]["code"] == "invalid-transition"
    assert image.status is current


def test_patch_of_an_unknown_image_returns_404_not_found(admin_client: TestClient) -> None:
    response = _patch(admin_client, "0" * 26, {"status": "rejected"})

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"


def test_patch_of_another_attribute_is_rejected(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = _patch(admin_client, image.id, {"status": "rejected", "sourceUrl": "https://evil"})

    assert response.status_code == 422
    assert "detail" in response.json()
    assert image.status is ImageStatus.PENDING


def test_patch_without_a_status_is_rejected(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = _patch(admin_client, image.id, {})

    assert response.status_code == 422
    assert image.status is ImageStatus.PENDING


def test_patch_with_an_unknown_status_is_rejected(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = _patch(admin_client, image.id, {"status": "nonsense"})

    assert response.status_code == 422
    assert image.status is ImageStatus.PENDING


def test_patch_without_csrf_header_returns_403(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = admin_client.patch(
        f"/api/product-images/{image.id}",
        json={"data": {"type": "product-images", "attributes": {"status": "rejected"}}},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}
    assert image.status is ImageStatus.PENDING


def test_patch_as_non_admin_returns_403(
    user_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = _patch(user_client, image.id, {"status": "rejected"})

    assert response.status_code == 403
    assert image.status is ImageStatus.PENDING


def test_the_resource_has_no_other_writes(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)
    headers = _csrf(admin_client)
    body = {"data": {"type": "product-images", "attributes": {"status": "rejected"}}}

    assert admin_client.post("/api/product-images", json=body, headers=headers).status_code == 405
    assert (
        admin_client.delete(f"/api/product-images/{image.id}", headers=headers).status_code == 405
    )
