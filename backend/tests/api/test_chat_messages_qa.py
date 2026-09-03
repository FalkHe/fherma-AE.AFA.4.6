"""QA coverage for the `chat-messages` resource, extending `test_chat_messages.py`.

Focus areas the dev suite does not already nail down: the write route requires
a session too, the guard really is `current_user` and not `current_admin`,
`extra="forbid"` holds at the resource-object and top-level envelope (not just
inside `attributes`), pagination beyond the end of the timeline degrades to an
empty page with the same `totalCount` rather than an error, `POST` creates
exactly one `Operation` row and announces exactly that one event (rewritten in
step 3.5, which turned "no turn yet" into a real one), and — the sharpest one —
the read-validation contract: a
message row whose JSONB trace is missing a pinned key fails loudly (500, no
leaked traceback) instead of silently rendering a gap.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.chat import Chat, ChatMessage, ChatMessageRole
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


def _seed_chat(session: FakeAsyncSession, user_id: str) -> Chat:
    chat = Chat(user_id=user_id)
    session.add(chat)
    return chat


def _seed_message(
    session: FakeAsyncSession,
    chat: Chat,
    body: str,
    *,
    created_at: datetime | None = None,
    tool_calls: list[dict] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        chat_id=chat.id,
        role=ChatMessageRole.ASSISTANT,
        body=body,
        tool_calls=tool_calls if tool_calls is not None else [],
        sources=[],
        recommendations=[],
    )
    session.add(message)
    if created_at is not None:
        message.created_at = created_at
    return message


def _send(client: TestClient, chat_id: str, body: str, **extra: object):
    return client.post(
        "/api/chat-messages",
        json={
            "data": {
                "type": "chat-messages",
                "attributes": {"chatId": chat_id, "body": body, **extra},
            }
        },
        headers=_csrf(client),
    )


# --- Auth: the write route requires a session too -------------------------------


def test_post_without_a_session_returns_401(client: TestClient) -> None:
    """No cookie, no CSRF header: `current_user` must fire before `csrf_protect`."""
    response = client.post(
        "/api/chat-messages",
        json={
            "data": {
                "type": "chat-messages",
                "attributes": {"chatId": "0" * 26, "body": "Hello?"},
            }
        },
    )

    assert response.status_code == 401


# --- Guard is current_user, not current_admin -----------------------------------


def test_admin_account_can_send_messages_like_any_customer(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    fake_session.users[customer.user_id].role = UserRole.ADMIN
    chat = _seed_chat(fake_session, customer.user_id)

    response = _send(customer.client, chat.id, "Hello?")

    assert response.status_code == 201, response.text


# --- extra="forbid" holds at every level, not just inside attributes -----------


def test_post_rejects_an_extra_field_on_the_resource_object(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = customer.client.post(
        "/api/chat-messages",
        json={
            "data": {
                "type": "chat-messages",
                "id": "0" * 26,
                "attributes": {"chatId": chat.id, "body": "Hello?"},
            }
        },
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422
    assert fake_session.rows(ChatMessage) == []


def test_post_rejects_an_extra_top_level_field(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = customer.client.post(
        "/api/chat-messages",
        json={
            "data": {
                "type": "chat-messages",
                "attributes": {"chatId": chat.id, "body": "Hello?"},
            },
            "meta": {"nonsense": True},
        },
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422
    assert fake_session.rows(ChatMessage) == []


def test_post_rejects_the_wrong_resource_type(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = customer.client.post(
        "/api/chat-messages",
        json={"data": {"type": "widgets", "attributes": {"chatId": chat.id, "body": "Hello?"}}},
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422
    assert fake_session.rows(ChatMessage) == []


# --- Pagination boundary past the end of the timeline ---------------------------


def test_list_a_page_past_the_end_of_the_timeline_is_empty_with_the_full_total(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    for index in range(3):
        _seed_message(
            fake_session,
            chat,
            f"message {index}",
            created_at=datetime(2026, 1, index + 1, tzinfo=UTC),
        )

    response = customer.client.get(
        "/api/chat-messages",
        params={"filter[chat]": chat.id, "page[size]": 2, "page[number]": 3},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"] == []
    assert body["meta"] == {"totalCount": 3}


# --- The turn this route starts, verified independently of activeOperationId ---


def test_post_creates_exactly_one_operation_and_announces_only_that(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    """Rewritten in step 3.5 (was: no operation and no notification at all).

    Belt-and-braces alongside the dev's `activeOperationId` check: exactly one
    `Operation` row is created for the turn, and the only thing announced is its
    `operation.updated` — the customer's own message emits nothing, and
    `chat.message.created` belongs to the worker's reply.
    """
    chat = _seed_chat(fake_session, customer.user_id)

    response = _send(customer.client, chat.id, "Hello?")

    assert response.status_code == 201, response.text
    operations = fake_session.rows(Operation)
    assert len(operations) == 1
    events = [json.loads(payload) for _channel, payload in fake_session.notifications]
    assert [event["event"] for event in events] == ["operation.updated"]
    assert events[0]["operationId"] == operations[0].id
    assert events[0]["entityType"] == "chat"
    assert events[0]["entityId"] == chat.id


def test_post_that_fails_validation_enqueues_nothing(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
) -> None:
    """A 422 must not start a turn: the dev suite proves the message and the
    body are rejected together, but never that rejection also means no
    operation, no pointer and no enqueue — a request that never became a
    stored message must not silently start the advisor typing anyway."""
    chat = _seed_chat(fake_session, customer.user_id)

    response = customer.client.post(
        "/api/chat-messages",
        json={
            "data": {
                "type": "chat-messages",
                "attributes": {"chatId": chat.id, "body": "   "},
            }
        },
        headers=_csrf(customer.client),
    )

    assert response.status_code == 422, response.text
    assert fake_session.rows(Operation) == []
    assert fake_session.rows(ChatMessage) == []
    assert chat.active_operation_id is None
    assert recorded_chat_enqueues == []


# --- Read validation: a writer that skips a pinned key fails loudly ------------


def test_get_with_an_incomplete_tool_call_shape_is_a_500_not_a_silent_gap() -> None:
    """Per the Step 3.3 landed decision, `ChatMessageAttributes` validates the
    JSONB columns on read. A tool call missing a pinned key (here: `error`) must
    not render with a silently absent field — it must fail the request, and the
    failure must not leak internals (no stack trace, no exception message) to
    the client.
    """
    from app.main import create_app  # local import: keep the module-level API surface intact

    fake_session = FakeAsyncSession()
    api = create_app()
    api.dependency_overrides[get_db_session] = lambda: fake_session

    with TestClient(api, raise_server_exceptions=False) as raw_client:
        registered = raw_client.post(
            "/auth/register", json={"username": "rider", "password": PASSWORD}
        )
        assert registered.status_code == 201, registered.text
        logged_in = raw_client.post(
            "/auth/login",
            json={"username": "rider", "password": PASSWORD, "rememberMe": False},
        )
        assert logged_in.status_code == 200, logged_in.text
        user_id = registered.json()["id"]

        chat = _seed_chat(fake_session, user_id)
        _seed_message(
            fake_session,
            chat,
            "Broken trace.",
            # Missing the pinned `id`/`status`/`error` keys entirely.
            tool_calls=[{"tool": "catalogue_search", "arguments": {}, "result": {}}],
        )

        response = raw_client.get("/api/chat-messages", params={"filter[chat]": chat.id})

    assert response.status_code == 500
    assert "Traceback" not in response.text
    assert "chat_service" not in response.text
    assert "ValidationError" not in response.text

    api.dependency_overrides.clear()
