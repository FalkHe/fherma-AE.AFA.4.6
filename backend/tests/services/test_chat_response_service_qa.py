"""QA additions to `app/services/chat_response_service.py`.

The dev agent's own `test_chat_response_service.py` already proves the prompt
shape (system + Human/AI history, body-only replay), the empty-answer guard and
that the requested model id equals `get_settings().advisor_model`. This file
adds two things worth independent confirmation rather than trusting the dev's
own assertions:

* the model actually used is `ADVISOR_MODEL`, not `CHAT_MODEL` — proven by
  pointing the two settings at *different* values and reading which one the
  stub model was built with (the dev's test only proves `advisor_model` is
  read; it does not distinguish it from `chat_model` by contrast);
* `sources`/`recommendations` traces on a prior assistant message, not only
  `tool_calls`, never leak into the replayed prompt text — shared-knowledge
  pins "body only", and the dev's own test only checks `tool_calls`.
"""

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from app.core.config import get_settings
from app.db.models.chat import Chat
from app.db.models.operation import Operation
from app.llm.agents import advisor
from app.services import chat_response_service, chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"


class StubModel:
    def __init__(self, answer: str = "Welcome! What will you use the bike for?") -> None:
        self.answer = answer
        self.requested: list[str | None] = []
        self.prompts: list[list[BaseMessage]] = []

    def bind_tools(self, _tools: Any) -> "StubModel":
        """The agent loop binds the advisor's tools; this stub answers either way."""
        return self

    async def ainvoke(self, prompt: list[BaseMessage], **_kwargs: Any) -> AIMessage:
        self.prompts.append(list(prompt))
        return AIMessage(self.answer)


@pytest.fixture
def stub_model(monkeypatch: pytest.MonkeyPatch) -> StubModel:
    model = StubModel()

    def factory(name: str | None = None) -> StubModel:
        model.requested.append(name)
        return model

    # Step 3.13 moved the factory into the agent loop the service delegates to.
    monkeypatch.setattr(advisor, "get_chat_model", factory)
    return model


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


def test_generate_asks_advisor_model_not_chat_model(
    fake_session: FakeAsyncSession, stub_model: StubModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two config keys must stay distinguishable, not merely both readable."""
    settings = get_settings()
    monkeypatch.setattr(settings, "advisor_model", "openai/advisor-only-model")
    monkeypatch.setattr(settings, "chat_model", "openai/chat-only-model")

    chat = _chat(fake_session)
    asyncio.run(chat_response_service.generate(fake_session, chat, _operation(fake_session, chat)))

    assert stub_model.requested == ["openai/advisor-only-model"]
    assert "openai/chat-only-model" not in stub_model.requested


def test_generate_does_not_replay_sources_or_recommendations(
    fake_session: FakeAsyncSession, stub_model: StubModel
) -> None:
    """Body-only replay applies to every JSONB trace, not only `tool_calls`."""
    chat = _chat(fake_session)
    asyncio.run(chat_service.append_user_message(fake_session, chat, "I'm 1.65m, A2 licence."))
    asyncio.run(
        chat_service.append_assistant_message(
            fake_session,
            chat,
            "Here is a match for you.",
            sources=[{"chunkId": "01CHUNK", "sourceUrl": "https://example.test/leak-marker"}],
            recommendations=[{"motorbikeId": "01BIKE", "name": "LeakedRecommendationName"}],
        )
    )

    asyncio.run(chat_response_service.generate(fake_session, chat, _operation(fake_session, chat)))

    prompt_text = "\n".join(message.text for message in stub_model.prompts[0])
    assert "leak-marker" not in prompt_text
    assert "LeakedRecommendationName" not in prompt_text
    assert "01CHUNK" not in prompt_text
