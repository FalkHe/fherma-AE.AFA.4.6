"""`chat.respond` — the operation lifecycle and the failure policy of one turn.

Neither Redis nor PostgreSQL nor OpenRouter is involved: the task's session
factory is replaced with the in-memory `WorkerSession` (the `test_embeddings.py`
pattern) and the response *service* is stubbed, because what is under test here
is the job's own contract — which outcome closes the operation how, and that a
failed turn is never silent.
"""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from openai import APIConnectionError
from openrouter.errors import EdgeNetworkTimeoutResponseError

from app.db.models.chat import Chat, ChatMessage, ChatMessageRole
from app.db.models.operation import Operation, OperationStatus
from app.jobs import TransientJobError
from app.jobs import chat as job
from app.services import chat_response_service, chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"

REPLY = "Welcome! What will you use the bike for?"


class _GatewayTimeout(EdgeNetworkTimeoutResponseError):
    """The SDK's edge-network timeout, constructible without an HTTP response.

    A real one carries the raw `httpx.Response` it was parsed from; the job only
    reads its text, so this subclass keeps the *type* (which is what the retry
    policy branches on) and skips the transport.
    """

    def __init__(self, message: str = "Provider request timed out at edge network") -> None:
        Exception.__init__(self, message)
        self.message = message


class WorkerSession(FakeAsyncSession):
    """The fake session plus the `rollback` a worker calls before bookkeeping.

    Nothing is undone: every service commits its own writes, so a failed task
    has no open transaction to discard — the call only has to exist. What *is*
    recorded is the order of rollbacks and table reads: a real `rollback()`
    expires every ORM instance, so the bookkeeping after one must re-load its
    rows instead of touching the ones it was holding.
    """

    def __init__(self) -> None:
        super().__init__()
        self.log: list[str] = []

    async def rollback(self) -> None:
        self.log.append("rollback")

    async def execute(self, statement: object) -> Any:
        for table in ("chats", "operations"):
            if f"FROM {table}" in str(statement):
                self.log.append(f"select:{table}")
        return await super().execute(statement)


class _Sessionmaker:
    """Hands the task the one fake session, as an async context manager."""

    def __init__(self, session: FakeAsyncSession) -> None:
        self.session = session

    def __call__(self) -> "_Sessionmaker":
        return self

    async def __aenter__(self) -> FakeAsyncSession:
        return self.session

    async def __aexit__(self, *_exception: Any) -> bool:
        return False


@pytest.fixture
def fake_session() -> WorkerSession:
    return WorkerSession()


@pytest.fixture(autouse=True)
def worker_session(fake_session: WorkerSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the task its session without a database."""
    monkeypatch.setattr(job, "get_sessionmaker", lambda: _Sessionmaker(fake_session))


@pytest.fixture
def generated(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Replace the response service with a stub that stores a fixed reply."""
    calls: list[tuple[str, str]] = []

    async def generate(session: Any, chat: Chat, operation: Operation) -> ChatMessage:
        calls.append((chat.id, operation.id))
        return await chat_service.append_assistant_message(session, chat, REPLY)

    monkeypatch.setattr(chat_response_service, "generate", generate)
    return calls


@pytest.fixture
def failing(monkeypatch: pytest.MonkeyPatch) -> Callable[[Exception], None]:
    """Return a setter that makes the response service raise a given exception."""

    def install(error: Exception) -> None:
        async def generate(session: Any, chat: Chat, operation: Operation) -> ChatMessage:
            raise error

        monkeypatch.setattr(chat_response_service, "generate", generate)

    return install


def _chat(session: FakeAsyncSession) -> Chat:
    return asyncio.run(chat_service.create_chat(session, USER_ID))


def _turn(session: FakeAsyncSession, chat: Chat) -> Operation:
    """The `queued` operation and the pointer `start_response` leaves behind."""
    operation = asyncio.run(
        operation_service.create(
            session,
            chat_service.RESPONSE_OPERATION_TYPE,
            entity_type=operation_service.CHAT_ENTITY_TYPE,
            entity_id=chat.id,
        )
    )
    chat.active_operation_id = operation.id
    return operation


def _events(session: FakeAsyncSession) -> list[str]:
    return [json.loads(payload)["event"] for _channel, payload in session.notifications]


def test_respond_answers_the_turn_and_succeeds(
    fake_session: WorkerSession, generated: list[tuple[str, str]]
) -> None:
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)

    asyncio.run(job.respond(chat.id, operation.id))

    assert generated == [(chat.id, operation.id)]
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.progress == 100
    assert operation.started_at is not None
    assert operation.error is None
    stored = fake_session.rows(ChatMessage)
    assert [message.body for message in stored] == [REPLY]
    assert stored[0].role is ChatMessageRole.ASSISTANT
    # The reply ends the turn: the typing indicator has nothing left to read.
    assert chat.active_operation_id is None
    # The message is announced before the operation's final state.
    assert _events(fake_session)[-2:] == ["chat.message.created", "operation.updated"]


def test_respond_persists_an_apology_when_the_turn_fails(
    fake_session: WorkerSession, failing: Callable[[Exception], None]
) -> None:
    """Never a silent dead chat: the customer reads an apology, the admin the cause."""
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)
    failing(RuntimeError("gateway said no"))

    asyncio.run(job.respond(chat.id, operation.id))

    assert [message.body for message in fake_session.rows(ChatMessage)] == [job.APOLOGY]
    assert fake_session.rows(ChatMessage)[0].role is ChatMessageRole.ASSISTANT
    assert chat.active_operation_id is None
    assert operation.status is OperationStatus.FAILED
    assert operation.error == "RuntimeError: gateway said no"
    assert operation.finished_at is not None
    # The apology is an ordinary reply, so it is announced like one.
    assert "chat.message.created" in _events(fake_session)


def test_the_apology_re_loads_its_rows_after_the_rollback(
    fake_session: WorkerSession, failing: Callable[[Exception], None]
) -> None:
    """The live bug this guards: `rollback()` expires every instance it holds.

    Reading `chat.id` afterwards is implicit IO — `MissingGreenlet` on an async
    session — which cost the customer their apology and left the operation
    `running`. The bookkeeping therefore re-reads both rows by id.
    """
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)
    failing(RuntimeError("boom"))

    asyncio.run(job.respond(chat.id, operation.id))

    assert "rollback" in fake_session.log
    after_rollback = fake_session.log[fake_session.log.index("rollback") :]
    assert "select:chats" in after_rollback
    assert "select:operations" in after_rollback
    assert after_rollback.index("select:chats") < after_rollback.index("select:operations")


def test_respond_re_raises_a_gateway_timeout_as_transient(
    fake_session: WorkerSession, failing: Callable[[Exception], None]
) -> None:
    """A timeout is the one failure worth retrying: the turn stays open."""
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)
    failing(_GatewayTimeout())

    with pytest.raises(TransientJobError):
        asyncio.run(job.respond(chat.id, operation.id))

    assert operation.status is OperationStatus.RUNNING
    assert fake_session.rows(ChatMessage) == []
    # Still claimed: the same turn is about to be attempted again.
    assert chat.active_operation_id == operation.id


def test_respond_fails_the_operation_of_a_deleted_consultation(
    fake_session: WorkerSession, generated: list[tuple[str, str]]
) -> None:
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)
    chat.deleted_at = datetime.now(UTC)

    asyncio.run(job.respond(chat.id, operation.id))

    assert generated == []
    assert fake_session.rows(ChatMessage) == []
    assert operation.status is OperationStatus.FAILED
    assert operation.error == job.CHAT_GONE_ERROR


def test_respond_of_an_unknown_operation_does_nothing(
    fake_session: WorkerSession, generated: list[tuple[str, str]]
) -> None:
    chat = _chat(fake_session)

    asyncio.run(job.respond(chat.id, "9" * 26))

    assert generated == []
    assert fake_session.rows(Operation) == []
    assert fake_session.rows(ChatMessage) == []


def test_a_failed_turn_lets_the_next_message_through(
    fake_session: WorkerSession, failing: Callable[[Exception], None]
) -> None:
    """The healing rule and the failure path agree: the chat is free afterwards."""
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)
    failing(RuntimeError("boom"))

    asyncio.run(job.respond(chat.id, operation.id))

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True


def test_respond_re_raises_an_embeddings_connection_error_as_transient(
    fake_session: WorkerSession, failing: Callable[[Exception], None]
) -> None:
    """The OpenAI-SDK errors `OpenAIEmbeddings` raises are transient too (D3)."""
    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
    failing(APIConnectionError(message="Connection error.", request=request))

    with pytest.raises(TransientJobError):
        asyncio.run(job.respond(chat.id, operation.id))

    assert operation.status is OperationStatus.RUNNING
    assert chat.active_operation_id == operation.id


def test_only_gateway_timeouts_and_connection_errors_are_retried() -> None:
    """A rejected, unauthorised or unparsable answer would fail again identically."""
    assert all(
        "Timeout" in error.__name__ or "Connection" in error.__name__
        for error in job.TRANSIENT_GATEWAY_ERRORS
    )
