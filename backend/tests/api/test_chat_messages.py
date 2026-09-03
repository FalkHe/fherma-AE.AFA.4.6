"""Behavioural tests for the `chat-messages` JSON:API resource.

Setup as in `test_chats.py` (in-memory `FakeAsyncSession`, plain accounts, a
second account for every ownership assertion). Three things are specific to this
resource and are what these tests are about:

* `filter[chat]` is required, and a wrong number of members is a different error
  code than none at all;
* the timeline order is `createdAt ASC, id ASC` — the reverse of every admin
  list — and it is paginated;
* the three JSONB attributes are stored in the pinned camelCase shapes and must
  come back **verbatim**, open `arguments`/`result` objects included.
"""

from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas.chat_messages import BODY_MAX_LENGTH
from app.db.models.chat import Chat, ChatMessage, ChatMessageRole
from app.db.models.operation import Operation, OperationStatus
from app.db.session import get_db_session
from app.services import chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

MESSAGE_ATTRIBUTES = {
    "role",
    "body",
    "toolCalls",
    "sources",
    "recommendations",
    "createdAt",
}

PASSWORD = "secret123"

# The pinned JSONB item shapes, exactly as the agent loop persists them.
TOOL_CALL = {
    "id": "call_0",
    "tool": "catalogue_search",
    "arguments": {"maxPowerKw": 35, "category": "naked"},
    "result": {
        "results": [{"motorbikeId": "01BIKE", "name": "Honda CB500F"}],
        "totalCount": 1,
    },
    "status": "succeeded",
    "error": None,
}

SOURCE = {
    "chunkId": "01CHUNK",
    "motorbikeId": "01BIKE",
    "sourceDocumentId": "01DOC",
    "sourceUrl": "https://en.wikipedia.org/wiki/Honda_CB500F",
    "sourceTitle": "Honda CB500F",
    "headingPath": "Honda CB500F > Design",
    "score": 0.032,
}

RECOMMENDATION = {
    "motorbikeId": "01BIKE",
    "name": "Honda CB500F",
    "imageUrl": "/media/motorbikes/01BIKE/01IMAGE_card.webp",
    "rationale": "A2-legal, light and cheap to run.",
    "matchedPreferences": ["budget", "a2"],
    "keySpecs": {
        "category": "naked",
        "engineCc": 471,
        "powerKw": 35.0,
        "wetWeightKg": 189.0,
        "seatHeightMm": 785,
        "priceBand": "mid",
    },
}


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


def _seed_chat(session: FakeAsyncSession, user_id: str, *, deleted: bool = False) -> Chat:
    chat = Chat(user_id=user_id)
    session.add(chat)
    if deleted:
        chat.deleted_at = datetime.now(UTC)
    return chat


def _seed_message(
    session: FakeAsyncSession,
    chat: Chat,
    body: str,
    *,
    role: ChatMessageRole = ChatMessageRole.ASSISTANT,
    created_at: datetime | None = None,
    tool_calls: list[dict] | None = None,
    sources: list[dict] | None = None,
    recommendations: list[dict] | None = None,
) -> ChatMessage:
    """Store one message directly, so its timestamp and traces are controllable."""
    message = ChatMessage(
        chat_id=chat.id,
        role=role,
        body=body,
        tool_calls=tool_calls or [],
        sources=sources or [],
        recommendations=recommendations or [],
    )
    session.add(message)
    if created_at is not None:
        message.created_at = created_at
    return message


def _seed_operation(
    session: FakeAsyncSession,
    chat: Chat,
    *,
    status: OperationStatus,
    age_seconds: float = 0.0,
) -> Operation:
    """Point `chat` at a response operation of a given status and age."""
    operation = Operation(
        type=chat_service.RESPONSE_OPERATION_TYPE,
        status=status,
        progress=0,
        entity_type=operation_service.CHAT_ENTITY_TYPE,
        entity_id=chat.id,
    )
    session.add(operation)
    # `add` stamps the server default; the healing rule reads this timestamp.
    operation.created_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
    chat.active_operation_id = operation.id
    return operation


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


# --- GET /api/chat-messages: the required filter -------------------------------


def test_list_without_the_filter_returns_400_missing_filter(customer: Account) -> None:
    response = customer.client.get("/api/chat-messages")

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["status"] == "400"
    assert errors[0]["code"] == "missing-filter"


def test_list_with_two_filter_members_returns_400_invalid_filter(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    first = _seed_chat(fake_session, customer.user_id)
    second = _seed_chat(fake_session, customer.user_id)

    response = customer.client.get(
        "/api/chat-messages", params={"filter[chat]": f"{first.id},{second.id}"}
    )

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "invalid-filter"


# --- GET /api/chat-messages: ownership ----------------------------------------


def test_list_of_an_unknown_consultation_returns_404(customer: Account) -> None:
    response = customer.client.get("/api/chat-messages", params={"filter[chat]": "0" * 26})

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"


def test_list_of_another_accounts_consultation_returns_404(
    customer: Account, other: Account, fake_session: FakeAsyncSession
) -> None:
    theirs = _seed_chat(fake_session, other.user_id)
    _seed_message(fake_session, theirs, "Their private conversation.")

    response = customer.client.get("/api/chat-messages", params={"filter[chat]": theirs.id})

    assert response.status_code == 404


def test_list_of_a_deleted_consultation_returns_404(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    deleted = _seed_chat(fake_session, customer.user_id, deleted=True)
    _seed_message(fake_session, deleted, "Still on disk, unreachable over HTTP.")

    response = customer.client.get("/api/chat-messages", params={"filter[chat]": deleted.id})

    assert response.status_code == 404


def test_list_without_a_session_returns_401(client: TestClient) -> None:
    response = client.get("/api/chat-messages", params={"filter[chat]": "0" * 26})

    assert response.status_code == 401


# --- GET /api/chat-messages: the timeline -------------------------------------


def test_list_returns_the_timeline_oldest_first(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    # Stored newest first on purpose: the order must come from the query.
    _seed_message(fake_session, chat, "third", created_at=datetime(2026, 3, 1, tzinfo=UTC))
    _seed_message(fake_session, chat, "first", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    _seed_message(fake_session, chat, "second", created_at=datetime(2026, 2, 1, tzinfo=UTC))

    response = customer.client.get("/api/chat-messages", params={"filter[chat]": chat.id})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"totalCount": 3}
    assert [resource["attributes"]["body"] for resource in body["data"]] == [
        "first",
        "second",
        "third",
    ]
    assert {resource["type"] for resource in body["data"]} == {"chat-messages"}


def test_list_excludes_the_messages_of_other_consultations(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    elsewhere = _seed_chat(fake_session, customer.user_id)
    _seed_message(fake_session, chat, "mine")
    _seed_message(fake_session, elsewhere, "another conversation")

    response = customer.client.get("/api/chat-messages", params={"filter[chat]": chat.id})

    assert response.status_code == 200, response.text
    assert [resource["attributes"]["body"] for resource in response.json()["data"]] == ["mine"]


def test_list_paginates_the_timeline(customer: Account, fake_session: FakeAsyncSession) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    for index in range(3):
        _seed_message(
            fake_session,
            chat,
            f"message {index}",
            created_at=datetime(2026, 1, index + 1, tzinfo=UTC),
        )

    first_page = customer.client.get(
        "/api/chat-messages", params={"filter[chat]": chat.id, "page[size]": 2}
    )
    second_page = customer.client.get(
        "/api/chat-messages",
        params={"filter[chat]": chat.id, "page[size]": 2, "page[number]": 2},
    )

    assert first_page.status_code == 200, first_page.text
    assert [resource["attributes"]["body"] for resource in first_page.json()["data"]] == [
        "message 0",
        "message 1",
    ]
    # `totalCount` stays the length of the whole timeline, so the SPA can walk.
    assert first_page.json()["meta"] == {"totalCount": 3}
    assert [resource["attributes"]["body"] for resource in second_page.json()["data"]] == [
        "message 2"
    ]
    assert second_page.json()["meta"] == {"totalCount": 3}


def test_list_page_size_above_the_maximum_is_rejected(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = customer.client.get(
        "/api/chat-messages", params={"filter[chat]": chat.id, "page[size]": 101}
    )

    assert response.status_code == 422


def test_list_serves_the_jsonb_traces_verbatim(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    _seed_message(
        fake_session,
        chat,
        "The CB500F fits your licence.",
        tool_calls=[TOOL_CALL],
        sources=[SOURCE],
        recommendations=[RECOMMENDATION],
    )

    response = customer.client.get("/api/chat-messages", params={"filter[chat]": chat.id})

    assert response.status_code == 200, response.text
    attributes = response.json()["data"][0]["attributes"]
    assert set(attributes) == MESSAGE_ATTRIBUTES
    assert attributes["role"] == "assistant"
    assert attributes["toolCalls"] == [TOOL_CALL]
    assert attributes["sources"] == [SOURCE]
    assert attributes["recommendations"] == [RECOMMENDATION]


# --- POST /api/chat-messages --------------------------------------------------


def test_post_stores_the_message_and_names_the_consultation(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = _send(customer.client, chat.id, "  I just got my A2 licence.  ")

    assert response.status_code == 201, response.text
    resource = response.json()["data"]
    assert resource["type"] == "chat-messages"
    assert set(resource["attributes"]) == MESSAGE_ATTRIBUTES
    assert resource["attributes"]["role"] == "user"
    # Stripped at the boundary; the service stores what it is given.
    assert resource["attributes"]["body"] == "I just got my A2 licence."
    # A user message carries three empty traces.
    assert resource["attributes"]["toolCalls"] == []
    assert resource["attributes"]["sources"] == []
    assert resource["attributes"]["recommendations"] == []
    assert fake_session.store(ChatMessage)[resource["id"]].chat_id == chat.id
    assert chat.title == "I just got my A2 licence."


def test_post_starts_the_response_turn(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
) -> None:
    """The advisor's turn begins with the message: pointer set, task enqueued."""
    chat = _seed_chat(fake_session, customer.user_id)

    assert _send(customer.client, chat.id, "Hello?").status_code == 201

    detail = customer.client.get(f"/api/chats/{chat.id}")
    assert detail.status_code == 200, detail.text
    operation_id = detail.json()["data"]["attributes"]["activeOperationId"]
    assert operation_id is not None
    assert recorded_chat_enqueues == [(chat.id, operation_id)]

    operation = fake_session.store(Operation)[operation_id]
    assert (operation.type, operation.entity_type, operation.entity_id) == (
        chat_service.RESPONSE_OPERATION_TYPE,
        operation_service.CHAT_ENTITY_TYPE,
        chat.id,
    )
    # The reply itself is the worker's job; only the customer's message is stored.
    assert [message.role for message in fake_session.rows(ChatMessage)] == [ChatMessageRole.USER]


def test_post_appends_to_the_existing_timeline(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    _seed_message(fake_session, chat, "Welcome!", created_at=datetime(2026, 1, 1, tzinfo=UTC))

    assert _send(customer.client, chat.id, "Thanks.").status_code == 201

    listed = customer.client.get("/api/chat-messages", params={"filter[chat]": chat.id})
    assert [resource["attributes"]["role"] for resource in listed.json()["data"]] == [
        "assistant",
        "user",
    ]


@pytest.mark.parametrize(
    "body",
    ["", "   ", "\n\t ", "x" * (BODY_MAX_LENGTH + 1)],
    ids=["empty", "spaces", "whitespace", "too-long"],
)
def test_post_rejects_an_unusable_body(
    customer: Account, fake_session: FakeAsyncSession, body: str
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = _send(customer.client, chat.id, body)

    assert response.status_code == 422
    # Request validation keeps FastAPI's own shape, which the SPA maps by `loc`.
    assert response.json()["detail"][0]["loc"][-1] == "body"
    assert fake_session.rows(ChatMessage) == []


def test_post_accepts_a_body_at_the_maximum_length(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = _send(customer.client, chat.id, "x" * BODY_MAX_LENGTH)

    assert response.status_code == 201, response.text


def test_post_rejects_an_invented_attribute(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = _send(customer.client, chat.id, "Hello.", role="assistant")

    assert response.status_code == 422
    assert fake_session.rows(ChatMessage) == []


def test_post_to_an_unknown_consultation_returns_404(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    """A well-formed but unknown 26-char ULID stays a 404, not a 422."""
    response = _send(customer.client, "0" * 26, "Hello.")

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"
    assert fake_session.rows(ChatMessage) == []


def test_post_with_a_too_long_chat_id_returns_422(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    response = _send(customer.client, "0" * 27, "Hello.")

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "data", "attributes", "chatId") in locs
    assert fake_session.rows(ChatMessage) == []


def test_post_with_a_non_crockford_chat_id_returns_422(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    """26 characters long, but lowercase is not the canonical ULID shape."""
    response = _send(customer.client, "0" * 25 + "a", "Hello.")

    assert response.status_code == 422
    assert fake_session.rows(ChatMessage) == []


def test_post_to_another_accounts_consultation_returns_404(
    customer: Account, other: Account, fake_session: FakeAsyncSession
) -> None:
    theirs = _seed_chat(fake_session, other.user_id)

    response = _send(customer.client, theirs.id, "Hello.")

    assert response.status_code == 404
    assert fake_session.rows(ChatMessage) == []


def test_post_to_a_deleted_consultation_returns_404(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    deleted = _seed_chat(fake_session, customer.user_id, deleted=True)

    response = _send(customer.client, deleted.id, "Hello.")

    assert response.status_code == 404
    assert fake_session.rows(ChatMessage) == []


def test_post_without_the_csrf_header_returns_403(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)

    response = customer.client.post(
        "/api/chat-messages",
        json={
            "data": {
                "type": "chat-messages",
                "attributes": {"chatId": chat.id, "body": "Hello."},
            }
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}
    assert fake_session.rows(ChatMessage) == []


# --- POST /api/chat-messages: stale-turn healing ------------------------------


@pytest.mark.parametrize(
    "status",
    [OperationStatus.SUCCEEDED, OperationStatus.FAILED],
    ids=["succeeded", "failed"],
)
def test_post_heals_a_pointer_at_a_finished_turn(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
    status: OperationStatus,
) -> None:
    """A turn that ended without clearing its pointer must not block the chat."""
    chat = _seed_chat(fake_session, customer.user_id)
    finished = _seed_operation(fake_session, chat, status=status)

    response = _send(customer.client, chat.id, "Are you still there?")

    assert response.status_code == 201, response.text
    assert chat.active_operation_id not in (None, finished.id)
    assert recorded_chat_enqueues == [(chat.id, chat.active_operation_id)]
    # The finished operation is left exactly as it was; only the pointer moved.
    assert finished.status is status
    assert finished.error is None


def test_post_heals_a_pointer_at_a_vanished_operation(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
) -> None:
    chat = _seed_chat(fake_session, customer.user_id)
    chat.active_operation_id = "9" * 26

    response = _send(customer.client, chat.id, "Hello?")

    assert response.status_code == 201, response.text
    assert recorded_chat_enqueues == [(chat.id, chat.active_operation_id)]


@pytest.mark.parametrize(
    "status",
    [OperationStatus.QUEUED, OperationStatus.RUNNING],
    ids=["queued", "running"],
)
def test_post_fails_a_timed_out_turn_and_accepts_the_message(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
    status: OperationStatus,
) -> None:
    """The killed-worker case: an unfinished turn older than the threshold is lost."""
    chat = _seed_chat(fake_session, customer.user_id)
    lost = _seed_operation(
        fake_session, chat, status=status, age_seconds=chat_service.stale_turn_seconds() + 1
    )

    response = _send(customer.client, chat.id, "Hello? Anybody?")

    assert response.status_code == 201, response.text
    assert lost.status is OperationStatus.FAILED
    assert lost.error == chat_service.TIMED_OUT_ERROR
    assert lost.finished_at is not None
    # A fresh turn took over.
    assert chat.active_operation_id not in (None, lost.id)
    assert recorded_chat_enqueues == [(chat.id, chat.active_operation_id)]


@pytest.mark.parametrize(
    "status",
    [OperationStatus.QUEUED, OperationStatus.RUNNING],
    ids=["queued", "running"],
)
def test_post_while_a_turn_is_in_flight_returns_409_response_pending(
    customer: Account,
    fake_session: FakeAsyncSession,
    recorded_chat_enqueues: list[tuple[str, str]],
    status: OperationStatus,
) -> None:
    """A live turn refuses the message — and refusing means not storing it.

    The in-flight turn built its context before this request arrived, so a
    message stored next to it would never be answered.
    """
    chat = _seed_chat(fake_session, customer.user_id)
    live = _seed_operation(fake_session, chat, status=status, age_seconds=5)

    response = _send(customer.client, chat.id, "And another thing…")

    assert response.status_code == 409
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["status"] == "409"
    assert errors[0]["code"] == "response-pending"
    # Nothing moved: no message, no second turn, no change to the live operation.
    assert fake_session.rows(ChatMessage) == []
    assert chat.active_operation_id == live.id
    assert live.status is status
    assert recorded_chat_enqueues == []


def test_the_stale_threshold_matches_the_constant_the_spa_mirrors() -> None:
    """150 s = the pinned `AGENT_TIMEOUT_SECONDS` (120) + 30, mirrored in the UI."""
    assert chat_service.stale_turn_seconds() == 150


def test_post_just_below_the_stale_threshold_is_still_pending(
    customer: Account, fake_session: FakeAsyncSession
) -> None:
    """The boundary is the pinned 150 s the frontend mirrors, not a rounded guess."""
    chat = _seed_chat(fake_session, customer.user_id)
    _seed_operation(
        fake_session,
        chat,
        status=OperationStatus.RUNNING,
        age_seconds=chat_service.stale_turn_seconds() - 5,
    )

    assert _send(customer.client, chat.id, "Hello?").status_code == 409


# --- No edit routes -----------------------------------------------------------


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_messages_are_immutable_over_http(customer: Account, method: str) -> None:
    """Neither the collection nor a single message accepts an edit.

    The collection routes only `GET`/`POST` (hence 405) and there is no
    single-message path at all (hence 404): a message is immutable once written.
    """
    collection = customer.client.request(
        method, "/api/chat-messages", headers=_csrf(customer.client)
    )
    detail = customer.client.request(
        method, "/api/chat-messages/" + "0" * 26, headers=_csrf(customer.client)
    )

    assert collection.status_code == 405
    assert detail.status_code == 404
