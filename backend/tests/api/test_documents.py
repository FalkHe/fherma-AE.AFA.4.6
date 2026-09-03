"""Behavioural tests for the read-only `documents` JSON:API resource.

Same setup as `test_operations.py`: the in-memory `FakeAsyncSession` stands
behind `get_db_session`, so `document_service` really runs. Rows are created
through the service — there is no HTTP path that writes a document, which is
itself part of the contract.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.source_document import SourceDocument, SourceType
from app.db.models.user import UserRole
from app.db.session import get_db_session
from app.services import document_service
from tests.services.conftest import FakeAsyncSession

DOCUMENT_ATTRIBUTES = {
    "sourceType",
    "sourceUrl",
    "sourceTitle",
    "contentMarkdown",
    "fetchedAt",
    "createdAt",
}

BIKE_ID = "0" * 22 + "BIKE"
OTHER_BIKE_ID = "0" * 22 + "OTHR"

FETCHED_AT = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)
MARKDOWN = "# Suzuki GSR600\n\n| Bore | Stroke |\n|---|---|\n| 67 mm | 42.5 mm |\n"


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


def _document(
    session: FakeAsyncSession,
    *,
    motorbike_id: str = BIKE_ID,
    source_type: SourceType = SourceType.PRODUCT,
    source_title: str = "Some page",
    source_url: str | None = "https://example.invalid/page",
    created_at: datetime,
) -> SourceDocument:
    """Create a document and stamp `created_at` (a server default in real life)."""
    document = asyncio.run(
        document_service.create_document(
            session,
            motorbike_id,
            source_type=source_type,
            source_title=source_title,
            raw_path=f"sources/{motorbike_id}/doc.html",
            content_markdown=MARKDOWN,
            fetched_at=FETCHED_AT,
            source_url=source_url,
        )
    )
    document.created_at = created_at
    return document


def _ids(response_body: dict) -> list[str]:
    return [resource["id"] for resource in response_body["data"]]


def test_list_returns_the_pinned_resource_shape_with_markdown_and_provenance(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    document = _document(
        fake_session,
        source_type=SourceType.WIKIPEDIA,
        source_title="Suzuki GSR600",
        source_url="https://en.wikipedia.org/wiki/Suzuki_GSR600",
        created_at=datetime(2026, 8, 26, 11, tzinfo=UTC),
    )

    response = admin_client.get("/api/documents", params={"filter[product]": BIKE_ID})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["meta"] == {"totalCount": 1}
    resource = body["data"][0]
    assert resource["type"] == "documents"
    assert resource["id"] == document.id
    assert set(resource["attributes"]) == DOCUMENT_ATTRIBUTES
    attributes = resource["attributes"]
    assert attributes["sourceType"] == "wikipedia"
    assert attributes["sourceUrl"] == "https://en.wikipedia.org/wiki/Suzuki_GSR600"
    assert attributes["sourceTitle"] == "Suzuki GSR600"
    assert attributes["contentMarkdown"] == MARKDOWN
    assert attributes["fetchedAt"].startswith("2026-08-26T10:30")


def test_list_puts_wikipedia_first_then_created_at(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    magazine = _document(fake_session, created_at=datetime(2026, 8, 26, 9, tzinfo=UTC))
    technical = _document(fake_session, created_at=datetime(2026, 8, 26, 10, tzinfo=UTC))
    # Stored last, still expected first.
    wikipedia = _document(
        fake_session,
        source_type=SourceType.WIKIPEDIA,
        created_at=datetime(2026, 8, 26, 11, tzinfo=UTC),
    )

    response = admin_client.get("/api/documents", params={"filter[product]": BIKE_ID})

    assert _ids(response.json()) == [wikipedia.id, magazine.id, technical.id]


def test_list_returns_only_the_filtered_product(
    admin_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    mine = _document(fake_session, created_at=datetime(2026, 8, 26, 9, tzinfo=UTC))
    _document(
        fake_session, motorbike_id=OTHER_BIKE_ID, created_at=datetime(2026, 8, 26, 9, tzinfo=UTC)
    )

    response = admin_client.get("/api/documents", params={"filter[product]": BIKE_ID})

    assert _ids(response.json()) == [mine.id]


def test_list_of_a_product_without_documents_is_empty(admin_client: TestClient) -> None:
    response = admin_client.get("/api/documents", params={"filter[product]": BIKE_ID})

    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"totalCount": 0}}


def test_list_without_the_product_filter_returns_400_missing_filter(
    admin_client: TestClient,
) -> None:
    response = admin_client.get("/api/documents")

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert errors[0]["status"] == "400"
    assert errors[0]["code"] == "missing-filter"
    assert set(errors[0]) == {"status", "code", "detail"}


def test_list_with_several_products_returns_400_invalid_filter(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/documents", params={"filter[product]": f"{BIKE_ID},{OTHER_BIKE_ID}"}
    )

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "invalid-filter"


def test_list_as_non_admin_returns_403(user_client: TestClient) -> None:
    response = user_client.get("/api/documents", params={"filter[product]": BIKE_ID})

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin privileges required."}


def test_list_without_a_session_returns_401(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        response = client.get("/api/documents", params={"filter[product]": BIKE_ID})
    api.dependency_overrides.clear()

    assert response.status_code == 401


def test_the_resource_is_read_only(admin_client: TestClient) -> None:
    headers = {"X-CSRF-Token": admin_client.cookies["csrf_token"]}
    body = {"data": {"type": "documents", "attributes": {"sourceTitle": "Forged"}}}

    assert admin_client.post("/api/documents", json=body, headers=headers).status_code == 405
    assert admin_client.patch("/api/documents", json=body, headers=headers).status_code == 405
