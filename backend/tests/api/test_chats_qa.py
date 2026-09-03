"""QA coverage for the `chats` resource, extending `test_chats.py`.

Focus areas the dev suite does not already nail down: the three write routes
require a session too (the dev suite only proved it for the list route), the
guard really is `current_user` and not `current_admin` (an admin account gets
through like anyone else), `extra="forbid"` holds at the resource-object and
top-level envelope too (not just inside `attributes`), and `page[number]`
below its floor is a 422 like `page[size]` above its ceiling already is.
"""

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.chat import Chat
from app.db.models.operation import Operation
from app.db.models.user import UserRole
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession

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


def _csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["csrf_token"]}


def _create(client: TestClient):
    return client.post(
        "/api/chats",
        json={"data": {"type": "chats", "attributes": {}}},
        headers=_csrf(client),
    )


# --- Auth: the write routes require a session too, not only the list ----------


def test_post_without_a_session_returns_401(client: TestClient) -> None:
    """No cookie, no CSRF header: `current_user` must fire before `csrf_protect`."""
    response = client.post("/api/chats", json={"data": {"type": "chats", "attributes": {}}})

    assert response.status_code == 401


def test_delete_without_a_session_returns_401(client: TestClient) -> None:
    response = client.delete("/api/chats/" + "0" * 26)

    assert response.status_code == 401


def test_get_detail_without_a_session_returns_401(client: TestClient) -> None:
    response = client.get("/api/chats/" + "0" * 26)

    assert response.status_code == 401


# --- Guard is current_user, not current_admin ----------------------------------


def test_admin_account_can_use_chats_like_any_customer(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    """The customer surface is not admin-gated: an admin is a user too."""
    fake_session.users[customer.user_id].role = UserRole.ADMIN

    created = _create(customer.client)
    assert created.status_code == 201, created.text
    chat_id = created.json()["data"]["id"]

    listed = customer.client.get("/api/chats")
    assert listed.status_code == 200, listed.text
    assert listed.json()["meta"] == {"totalCount": 1}

    deleted = customer.client.delete(f"/api/chats/{chat_id}", headers=_csrf(customer.client))
    assert deleted.status_code == 204


# --- extra="forbid" holds at every level, not just inside attributes ----------


def test_post_rejects_an_extra_field_on_the_resource_object(customer: Account) -> None:
    response = customer.client.post(
        "/api/chats",
        json={"data": {"type": "chats", "id": "0" * 26, "attributes": {}}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422


def test_post_rejects_an_extra_top_level_field(customer: Account) -> None:
    response = customer.client.post(
        "/api/chats",
        json={"data": {"type": "chats", "attributes": {}}, "meta": {"nonsense": True}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422


def test_post_rejects_the_wrong_resource_type(customer: Account) -> None:
    response = customer.client.post(
        "/api/chats",
        json={"data": {"type": "widgets", "attributes": {}}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422


# --- Pagination floor, mirroring the already-proven ceiling --------------------


def test_list_page_number_below_one_is_rejected(customer: Account) -> None:
    response = customer.client.get("/api/chats", params={"page[number]": 0})

    assert response.status_code == 422


def test_list_page_size_below_one_is_rejected(customer: Account) -> None:
    response = customer.client.get("/api/chats", params={"page[size]": 0})

    assert response.status_code == 422


# --- Step 3.5: a rejected POST must not start a turn ---------------------------


def test_post_that_fails_validation_enqueues_nothing(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
) -> None:
    """The dev suite proves an invented attribute is a 422; it does not prove
    that the row it would have created never got as far as a greeting turn —
    `start_response` runs after `create_chat` in the route, so a validation
    failure raised by FastAPI before the handler body executes must leave no
    `Chat`, no `Operation` and no enqueue behind."""
    response = customer.client.post(
        "/api/chats",
        json={"data": {"type": "chats", "attributes": {"title": "Invented"}}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422, response.text
    assert fake_session.rows(Chat) == []
    assert fake_session.rows(Operation) == []
    assert recorded_chat_enqueues == []
