"""QA supplement to `test_images.py` (step 2.9).

`test_images.py` already independently proves the full legal/illegal status
matrix, the CSRF and non-admin 403s, the anonymous-list 401 and the pinned
variant-URL formula on the list endpoint. This file only adds the gaps left
in the acceptance criteria handed to QA:

1. anonymous PATCH (no session at all) -> 401 (only "wrong role" was proved,
   not "no session"),
2. extra/unknown keys anywhere in the PATCH envelope (top-level *and*
   resource-object level, not just an extra attribute) -> 422, not silently
   dropped,
3. the variant URLs in the PATCH *response* also match the pinned formula
   (only the list response was checked),
4. an illegal transition emits *no* notification (only the legal-transition
   case was checked).
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

BIKE_ID = "0" * 22 + "BIKE"
SOURCE_URL = "https://upload.wikimedia.invalid/Suzuki_GSR600.jpg"


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


def _image(
    session: FakeAsyncSession,
    *,
    motorbike_id: str = BIKE_ID,
    status: ImageStatus = ImageStatus.PENDING,
) -> MotorbikeImage:
    image = MotorbikeImage(
        motorbike_id=motorbike_id,
        source_url=SOURCE_URL,
        attribution=None,
        status=status,
        original_path=f"motorbikes/{motorbike_id}/original.jpg",
        created_at=datetime(2026, 8, 26, 11, tzinfo=UTC),
    )
    session.add(image)
    return image


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


# --- auth matrix ----------------------------------------------------------


def test_patch_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        image = _image(fake_session)
        response = client.patch(
            f"/api/product-images/{image.id}",
            json={"data": {"type": "product-images", "attributes": {"status": "rejected"}}},
        )
    api.dependency_overrides.clear()

    assert response.status_code == 401
    assert image.status is ImageStatus.PENDING


# --- envelope strictness ---------------------------------------------------


def test_patch_with_an_extra_top_level_key_is_rejected(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = admin_client.patch(
        f"/api/product-images/{image.id}",
        json={
            "data": {"type": "product-images", "attributes": {"status": "rejected"}},
            "meta": {"unexpected": True},
        },
        headers=_csrf(admin_client),
    )

    assert response.status_code == 422
    assert image.status is ImageStatus.PENDING


def test_patch_with_an_extra_key_in_the_resource_object_is_rejected(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = admin_client.patch(
        f"/api/product-images/{image.id}",
        json={
            "data": {
                "id": image.id,
                "type": "product-images",
                "attributes": {"status": "rejected"},
            }
        },
        headers=_csrf(admin_client),
    )

    assert response.status_code == 422
    assert image.status is ImageStatus.PENDING


# --- response shape after a write ------------------------------------------


def test_patch_response_variant_urls_match_the_pinned_formula(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session)

    response = admin_client.patch(
        f"/api/product-images/{image.id}",
        json={"data": {"type": "product-images", "attributes": {"status": "approved"}}},
        headers=_csrf(admin_client),
    )

    assert response.status_code == 200, response.text
    variants = response.json()["data"]["attributes"]["variants"]
    assert variants == {
        "thumb": f"/media/motorbikes/{BIKE_ID}/{image.id}_thumb.webp",
        "card": f"/media/motorbikes/{BIKE_ID}/{image.id}_card.webp",
        "detail": f"/media/motorbikes/{BIKE_ID}/{image.id}_detail.webp",
    }


# --- notification discipline ------------------------------------------------


def test_illegal_patch_emits_no_notification(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    image = _image(fake_session, status=ImageStatus.REJECTED)
    notifications_before = len(fake_session.notifications)

    response = admin_client.patch(
        f"/api/product-images/{image.id}",
        json={"data": {"type": "product-images", "attributes": {"status": "approved"}}},
        headers=_csrf(admin_client),
    )

    assert response.status_code == 422, response.text
    assert fake_session.notifications[notifications_before:] == []
