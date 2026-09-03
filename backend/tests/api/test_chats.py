"""Behavioural tests for the `chats` JSON:API resource.

Same setup as `test_products.py`: the in-memory `FakeAsyncSession` stands behind
`get_db_session`, so `chat_service` really runs — rows are really created, the
soft delete really hides them and the `-updatedAt` ordering really comes out of
the store. The difference is the guard: this is the customer surface, so a plain
account (the default role after `/auth/register`) is enough, and a **second**
account exists in every ownership test — the pinned rule is that its
consultations are indistinguishable from consultations that never existed.
"""

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.chat import Chat
from app.db.models.operation import Operation, OperationStatus
from app.db.session import get_db_session
from app.services import chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

CHAT_ATTRIBUTES = {"title", "activeOperationId", "createdAt", "updatedAt"}

PASSWORD = "secret123"


@dataclass(frozen=True)
class Account:
    """A signed-in account: its own cookie jar plus its user id."""

    client: TestClient
    user_id: str


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def sign_in(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[Callable[[str], Account]]:
    """Return a factory that registers and logs in one account per call."""
    api.dependency_overrides[get_db_session] = lambda: fake_session

    with ExitStack() as stack:

        def _sign_in(username: str) -> Account:
            client = stack.enter_context(TestClient(api))
            registered = client.post(
                "/auth/register", json={"username": username, "password": PASSWORD}
            )
            assert registered.status_code == 201, registered.text
            logged_in = client.post(
                "/auth/login",
                json={"username": username, "password": PASSWORD, "rememberMe": False},
            )
            assert logged_in.status_code == 200, logged_in.text
            return Account(client=client, user_id=registered.json()["id"])

        yield _sign_in

    api.dependency_overrides.clear()


@pytest.fixture
def customer(sign_in: Callable[[str], Account]) -> Account:
    return sign_in("rider")


@pytest.fixture
def other(sign_in: Callable[[str], Account]) -> Account:
    return sign_in("stranger")


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _create(client: TestClient):
    return client.post(
        "/api/chats",
        json={"data": {"type": "chats", "attributes": {}}},
        headers=_csrf(client),
    )


def _seed(
    session: FakeAsyncSession,
    user_id: str,
    *,
    updated_at: datetime | None = None,
    deleted: bool = False,
) -> Chat:
    """Store one consultation directly, so its timestamps are controllable."""
    chat = Chat(user_id=user_id)
    session.add(chat)
    if updated_at is not None:
        chat.updated_at = updated_at
    if deleted:
        chat.deleted_at = datetime.now(UTC)
    return chat


# --- GET /api/chats -----------------------------------------------------------


def test_list_returns_own_consultations_most_recent_activity_first(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    older = _seed(fake_session, customer.user_id, updated_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _seed(fake_session, customer.user_id, updated_at=datetime(2026, 3, 1, tzinfo=UTC))

    response = customer.client.get("/api/chats")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"totalCount": 2}
    assert [resource["id"] for resource in body["data"]] == [newer.id, older.id]
    assert {resource["type"] for resource in body["data"]} == {"chats"}
    assert set(body["data"][0]["attributes"]) == CHAT_ATTRIBUTES


def test_list_excludes_deleted_and_foreign_consultations(
    customer: Account, other: Account, fake_session: FakeAsyncSession
) -> None:
    mine = _seed(fake_session, customer.user_id)
    _seed(fake_session, customer.user_id, deleted=True)
    _seed(fake_session, other.user_id)

    response = customer.client.get("/api/chats")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"totalCount": 1}
    assert [resource["id"] for resource in body["data"]] == [mine.id]


def test_list_paginates_within_the_sorted_order(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    _seed(fake_session, customer.user_id, updated_at=datetime(2026, 1, 1, tzinfo=UTC))
    newer = _seed(fake_session, customer.user_id, updated_at=datetime(2026, 3, 1, tzinfo=UTC))

    response = customer.client.get("/api/chats", params={"page[number]": 1, "page[size]": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    # `totalCount` stays the unpaginated total.
    assert body["meta"] == {"totalCount": 2}
    assert [resource["id"] for resource in body["data"]] == [newer.id]


def test_list_page_size_above_the_maximum_is_rejected(customer: Account) -> None:
    response = customer.client.get("/api/chats", params={"page[size]": 101})

    assert response.status_code == 422


def test_list_without_a_session_returns_401(client: TestClient) -> None:
    response = client.get("/api/chats")

    assert response.status_code == 401


# --- GET /api/chats/{id} ------------------------------------------------------


def test_get_returns_the_pinned_attributes(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    stored = _seed(fake_session, customer.user_id)

    response = customer.client.get(f"/api/chats/{stored.id}")

    assert response.status_code == 200, response.text
    resource = response.json()["data"]
    assert resource["type"] == "chats"
    assert resource["id"] == stored.id
    assert set(resource["attributes"]) == CHAT_ATTRIBUTES
    # A fresh consultation is unnamed and idle.
    assert resource["attributes"]["title"] is None
    assert resource["attributes"]["activeOperationId"] is None
    assert resource["attributes"]["createdAt"] is not None


def test_get_unknown_id_returns_404_not_found(customer: Account) -> None:
    response = customer.client.get("/api/chats/" + "0" * 26)

    assert response.status_code == 404
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["status"] == "404"
    assert errors[0]["code"] == "not-found"


def test_get_another_accounts_consultation_returns_404(
    customer: Account, other: Account, fake_session: FakeAsyncSession
) -> None:
    theirs = _seed(fake_session, other.user_id)

    response = customer.client.get(f"/api/chats/{theirs.id}")

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"


def test_get_deleted_consultation_returns_404(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    deleted = _seed(fake_session, customer.user_id, deleted=True)

    response = customer.client.get(f"/api/chats/{deleted.id}")

    assert response.status_code == 404


# --- POST /api/chats ----------------------------------------------------------


def test_post_creates_a_consultation_the_advisor_opens(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    """The advisor speaks first: the 201 already carries the greeting turn.

    Only the turn, though — the title still comes from the first *user* message,
    so a fresh consultation is unnamed.
    """
    response = _create(customer.client)

    assert response.status_code == 201, response.text
    resource = response.json()["data"]
    assert set(resource["attributes"]) == CHAT_ATTRIBUTES
    assert resource["attributes"]["title"] is None
    assert resource["attributes"]["activeOperationId"] is not None
    stored = fake_session.store(Chat)[resource["id"]]
    assert stored.user_id == customer.user_id
    assert stored.deleted_at is None


def test_post_enqueues_the_greeting_turn(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
) -> None:
    """One `chat.respond` task per created consultation, pointing at its operation."""
    response = _create(customer.client)

    assert response.status_code == 201, response.text
    chat_id = response.json()["data"]["id"]
    operation_id = response.json()["data"]["attributes"]["activeOperationId"]
    assert recorded_chat_enqueues == [(chat_id, operation_id)]

    operation = fake_session.store(Operation)[operation_id]
    assert (operation.type, operation.entity_type, operation.entity_id) == (
        chat_service.RESPONSE_OPERATION_TYPE,
        operation_service.CHAT_ENTITY_TYPE,
        chat_id,
    )
    assert operation.status is OperationStatus.QUEUED


def test_post_rejects_an_invented_attribute(customer: Account) -> None:
    response = customer.client.post(
        "/api/chats",
        json={"data": {"type": "chats", "attributes": {"title": "Commuter bike"}}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422


def test_post_without_the_csrf_header_returns_403(customer: Account) -> None:
    response = customer.client.post(
        "/api/chats", json={"data": {"type": "chats", "attributes": {}}}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}


# --- DELETE /api/chats/{id} ---------------------------------------------------


def test_delete_soft_deletes_and_hides_the_consultation(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    created = _create(customer.client).json()["data"]["id"]

    deleted = customer.client.delete(f"/api/chats/{created}", headers=_csrf(customer.client))

    assert deleted.status_code == 204
    assert deleted.content == b""
    # The row survives, only its `deleted_at` was set.
    assert fake_session.store(Chat)[created].deleted_at is not None
    assert customer.client.get("/api/chats").json()["meta"] == {"totalCount": 0}
    assert customer.client.get(f"/api/chats/{created}").status_code == 404


def test_delete_twice_returns_404(customer: Account) -> None:
    created = _create(customer.client).json()["data"]["id"]
    assert (
        customer.client.delete(f"/api/chats/{created}", headers=_csrf(customer.client)).status_code
        == 204
    )

    again = customer.client.delete(f"/api/chats/{created}", headers=_csrf(customer.client))

    assert again.status_code == 404
    assert again.json()["errors"][0]["code"] == "not-found"


def test_delete_another_accounts_consultation_returns_404(
    customer: Account, other: Account, fake_session: FakeAsyncSession
) -> None:
    theirs = _seed(fake_session, other.user_id)

    response = customer.client.delete(f"/api/chats/{theirs.id}", headers=_csrf(customer.client))

    assert response.status_code == 404
    assert fake_session.store(Chat)[theirs.id].deleted_at is None


def test_delete_without_the_csrf_header_returns_403(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    stored = _seed(fake_session, customer.user_id)

    response = customer.client.delete(f"/api/chats/{stored.id}")

    assert response.status_code == 403
    assert stored.deleted_at is None


# --- No rename route ----------------------------------------------------------


def test_patch_is_not_routed(customer: Account, fake_session: FakeAsyncSession) -> None:
    stored = _seed(fake_session, customer.user_id)

    response = customer.client.patch(
        f"/api/chats/{stored.id}",
        json={"data": {"type": "chats", "attributes": {"title": "Renamed"}}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 405
