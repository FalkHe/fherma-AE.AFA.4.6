"""`app/services/chat_response_service.py` — the seam between the job and the agent.

Since step 3.13 the seam is thin on purpose: it runs the agent loop and persists
what came back. So this file replaces the agent loop with a recorder (the loop
itself is covered in `tests/llm/agents/test_advisor.py`) and asserts only what
this module owns:

* the loop is asked for **this** chat, with no model override — production always
  uses the configured advisor model;
* all four parts of the result are persisted, the three traces verbatim and in
  their pinned camelCase shapes, through `append_assistant_message` (which ends
  the turn and announces the message);
* an answer with no text is refused instead of stored as an empty bubble.

The in-memory `FakeAsyncSession` stands in for the database; no gateway is ever
dialled.
"""

import asyncio
from typing import Any

import pytest

from app.db.models.chat import Chat, ChatMessage, ChatMessageRole
from app.db.models.operation import Operation, OperationStatus
from app.llm.agents import advisor
from app.services import chat_response_service, chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"

TOOL_CALL = {
    "id": "01J0TOOLCALL00000000000001",
    "tool": "catalogue_search",
    "arguments": {"a2Eligible": True},
    "result": {"results": [], "totalCount": 0},
    "status": "succeeded",
    "error": None,
}
SOURCE = {
    "chunkId": "01J0CHUNK000000000000000001",
    "motorbikeId": "01J0BIKE0000000000000000AA",
    "sourceDocumentId": "01J0DOC00000000000000000001",
    "sourceUrl": "https://example.test/review",
    "sourceTitle": "CB500F review",
    "headingPath": "Honda CB500F > Verdict",
    "score": 0.032,
}
RECOMMENDATION = {
    "motorbikeId": "01J0BIKE0000000000000000AA",
    "name": "Honda CB500F",
    "imageUrl": None,
    "rationale": "Fits your A2 licence and your commute.",
    "matchedPreferences": ["licence"],
    "keySpecs": {
        "category": "naked",
        "engineCc": 471,
        "powerKw": 35.0,
        "wetWeightKg": 189.0,
        "seatHeightMm": 785,
        "priceBand": "mid",
    },
}


class RecordedTurn:
    """Stands in for the agent loop: records its arguments, returns a result."""

    def __init__(self, result: advisor.AdvisorResult) -> None:
        self.result = result
        self.calls: list[tuple[Any, Chat, Any]] = []

    async def __call__(
        self, session: Any, chat: Chat, *, model: Any = None
    ) -> advisor.AdvisorResult:
        self.calls.append((session, chat, model))
        return self.result


@pytest.fixture
def turn(monkeypatch: pytest.MonkeyPatch) -> RecordedTurn:
    """Replace the agent loop the service imported, keeping a full result."""
    recorder = RecordedTurn(
        advisor.AdvisorResult(
            body="Welcome! What will you use the bike for?",
            tool_calls=[TOOL_CALL],
            sources=[SOURCE],
            recommendations=[RECOMMENDATION],
        )
    )
    monkeypatch.setattr(advisor, "run_advisor_turn", recorder)
    return recorder


def _chat(session: FakeAsyncSession) -> Chat:
    return asyncio.run(chat_service.create_chat(session, USER_ID))


def _operation(session: FakeAsyncSession, chat: Chat) -> Operation:
    return asyncio.run(
        operation_service.create(
            session,
            chat_service.RESPONSE_OPERATION_TYPE,
            entity_type=operation_service.CHAT_ENTITY_TYPE,
            entity_id=chat.id,
        )
    )


def test_generate_persists_the_reply_and_ends_the_turn(
    fake_session: FakeAsyncSession, turn: RecordedTurn
) -> None:
    chat = _chat(fake_session)
    operation = _operation(fake_session, chat)
    chat.active_operation_id = operation.id

    message = asyncio.run(chat_response_service.generate(fake_session, chat, operation))

    assert message.role is ChatMessageRole.ASSISTANT
    assert message.body == turn.result.body
    assert fake_session.rows(ChatMessage) == [message]
    # `append_assistant_message` owns both: the pointer and the announcement.
    assert chat.active_operation_id is None
    announced = [payload for _channel, payload in fake_session.notifications]
    assert any("chat.message.created" in payload for payload in announced)
    # The greeting must not name the consultation.
    assert chat.title is None


def test_generate_runs_the_agent_loop_for_this_chat_without_a_model_override(
    fake_session: FakeAsyncSession, turn: RecordedTurn
) -> None:
    """Production never picks the model here — the loop reads `ADVISOR_MODEL`."""
    chat = _chat(fake_session)

    asyncio.run(chat_response_service.generate(fake_session, chat, _operation(fake_session, chat)))

    assert turn.calls == [(fake_session, chat, None)]


def test_generate_stores_the_three_traces_verbatim(
    fake_session: FakeAsyncSession, turn: RecordedTurn
) -> None:
    """The pinned camelCase shapes reach the JSONB columns unchanged.

    Nothing in this module may re-map them: the read path validates them against
    the frozen `ToolCall`/`MessageSource`/`Recommendation` models, and the writer
    of those shapes is the agent, not the responder.
    """
    chat = _chat(fake_session)

    message = asyncio.run(
        chat_response_service.generate(fake_session, chat, _operation(fake_session, chat))
    )

    assert message.tool_calls == [TOOL_CALL]
    assert message.sources == [SOURCE]
    assert message.recommendations == [RECOMMENDATION]


def test_generate_refuses_to_store_an_empty_answer(
    fake_session: FakeAsyncSession, turn: RecordedTurn
) -> None:
    """An empty bubble would look like a delivered answer; the job apologises instead."""
    turn.result = advisor.AdvisorResult(body="", tool_calls=[TOOL_CALL])
    chat = _chat(fake_session)
    operation = _operation(fake_session, chat)
    chat.active_operation_id = operation.id

    with pytest.raises(chat_response_service.EmptyAnswerError):
        asyncio.run(chat_response_service.generate(fake_session, chat, operation))

    assert fake_session.rows(ChatMessage) == []
    assert chat.active_operation_id == operation.id
    assert operation.status is OperationStatus.QUEUED
