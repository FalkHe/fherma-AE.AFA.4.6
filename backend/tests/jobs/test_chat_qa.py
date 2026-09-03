"""QA additions to `app/jobs/chat.py`.

The dev agent's own `tests/jobs/test_chat.py` proves the lifecycle contract
(succeed/fail/retry, the apology, the rollback-expiry regression guard) with
`chat_response_service.generate` *stubbed out*. Two things are worth proving
independently, with the real service wired in instead of a stub:

* an actually-empty LLM answer (the real `chat_response_service.EmptyAnswerError`
  path, not a generic `RuntimeError` standing in for "any exception") still ends
  in the apology and a `failed` operation, not a silently empty bubble;
* `RequestTimeoutResponseError`, the second member of `TRANSIENT_GATEWAY_ERRORS`,
  is also actually caught by the `except` clause and retried — the dev's own
  `test_only_gateway_timeouts_are_retried` only checks the class *names* contain
  "Timeout", never that the second member is excepted by the running code (only
  `EdgeNetworkTimeoutResponseError` is exercised through `job.respond` there).
"""

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from openrouter.errors import RequestTimeoutResponseError

from app.db.models.chat import Chat, ChatMessage, ChatMessageRole
from app.db.models.operation import Operation, OperationStatus
from app.jobs import TransientJobError
from app.jobs import chat as job
from app.llm.agents import advisor
from app.services import chat_response_service, chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"


class _RequestTimeout(RequestTimeoutResponseError):
    """Constructible without the SDK's `httpx.Response`/`data`, like the dev's
    `_GatewayTimeout` subclass of the sibling error — the job only reads the
    exception's *type*, never its transport-bound attributes."""

    def __init__(self, message: str = "Provider request timed out") -> None:
        Exception.__init__(self, message)
        self.message = message


class WorkerSession(FakeAsyncSession):
    """`FakeAsyncSession` plus the no-op `rollback()` a worker calls before its
    post-failure bookkeeping (the `test_chat.py` `WorkerSession` pattern)."""

    async def rollback(self) -> None:
        return None


class _Sessionmaker:
    def __init__(self, session: FakeAsyncSession) -> None:
        self.session = session

    def __call__(self) -> "_Sessionmaker":
        return self

    async def __aenter__(self) -> FakeAsyncSession:
        return self.session

    async def __aexit__(self, *_exception: Any) -> bool:
        return False


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return WorkerSession()


@pytest.fixture(autouse=True)
def worker_session(fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job, "get_sessionmaker", lambda: _Sessionmaker(fake_session))


def _chat(session: FakeAsyncSession) -> Chat:
    return asyncio.run(chat_service.create_chat(session, USER_ID))


def _turn(session: FakeAsyncSession, chat: Chat) -> Operation:
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


def test_an_empty_llm_answer_still_apologises_through_the_real_service(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`chat_response_service.generate` is wired in for real here (only the
    model call is stubbed), so this proves the actual `EmptyAnswerError` raised
    by the actual seam reaches the job's generic `except Exception` branch —
    not a stand-in exception chosen to resemble it."""

    class BlankModel:
        def bind_tools(self, _tools: Any) -> "BlankModel":
            """The agent loop binds its tools before invoking; this model has none."""
            return self

        async def ainvoke(self, *_args: Any, **_kwargs: Any) -> AIMessage:
            return AIMessage("   \n\t  ")

    # Since step 3.13 the model is built by the agent loop, which the (real)
    # response service delegates to; the seam moved, the assertion did not.
    monkeypatch.setattr(advisor, "get_chat_model", lambda *_a, **_k: BlankModel())

    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)

    asyncio.run(job.respond(chat.id, operation.id))

    stored = fake_session.rows(ChatMessage)
    assert [message.body for message in stored] == [job.APOLOGY]
    assert stored[0].role is ChatMessageRole.ASSISTANT
    assert chat.active_operation_id is None
    assert operation.status is OperationStatus.FAILED
    assert operation.error is not None
    assert "EmptyAnswerError" in operation.error


def test_a_request_timeout_error_is_also_retried_not_apologised(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second member of `TRANSIENT_GATEWAY_ERRORS`, proven the same way the
    dev proved the first: through the real `except` clause in `job.respond`,
    not by inspecting the tuple's contents."""

    async def generate(*_args: Any, **_kwargs: Any) -> ChatMessage:
        raise _RequestTimeout()

    monkeypatch.setattr(chat_response_service, "generate", generate)

    chat = _chat(fake_session)
    operation = _turn(fake_session, chat)

    with pytest.raises(TransientJobError):
        asyncio.run(job.respond(chat.id, operation.id))

    assert operation.status is OperationStatus.RUNNING
    assert fake_session.rows(ChatMessage) == []
    assert chat.active_operation_id == operation.id
