"""`app/services/chat_service.py` — timeline, soft delete and preferences.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.

Two things here cannot be checked by looking at the result: the announcement
must follow the commit (`_RecordingSession` keeps an interleaved log, as in
`test_operation_service.py`), and the timeline order must survive rows written
in the same instant (the tests stamp `created_at` explicitly).
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.db.models.chat import (
    TITLE_LENGTH,
    Chat,
    ChatMessage,
    ChatMessageRole,
    ChatPreference,
    PreferenceFirmness,
)
from app.services import chat_service
from app.services.operation_service import EVENT_CHANNEL
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"
OTHER_USER_ID = "1" * 22 + "USER"
OPERATION_ID = "2" * 22 + "OPER"


class _RecordingSession(FakeAsyncSession):
    """A fake session that also remembers the *order* of commits and notifies."""

    def __init__(self) -> None:
        super().__init__()
        self.log: list[str] = []

    async def commit(self) -> None:
        await super().commit()
        self.log.append("commit")

    async def execute(self, statement: object) -> Any:
        before = len(self.notifications)
        result = await super().execute(statement)
        if len(self.notifications) > before:
            self.log.append("notify")
        return result


@pytest.fixture
def session() -> _RecordingSession:
    return _RecordingSession()


def _payloads(session: FakeAsyncSession) -> list[dict[str, Any]]:
    """Return the decoded payloads published on the events channel."""
    return [json.loads(payload) for channel, payload in session.notifications]


def _create_chat(session: FakeAsyncSession, user_id: str = USER_ID) -> Chat:
    return asyncio.run(chat_service.create_chat(session, user_id))


def _user_message(session: FakeAsyncSession, chat: Chat, body: str) -> ChatMessage:
    return asyncio.run(chat_service.append_user_message(session, chat, body))


def _assistant_message(session: FakeAsyncSession, chat: Chat, body: str, **kwargs: Any) -> Any:
    return asyncio.run(chat_service.append_assistant_message(session, chat, body, **kwargs))


def _record(session: FakeAsyncSession, chat_id: str, attribute: str, value: str) -> ChatPreference:
    return asyncio.run(
        chat_service.record_preference(
            session,
            chat_id,
            attribute=attribute,
            value=value,
            firmness=PreferenceFirmness.SOFT,
        )
    )


# --- create / get / list ------------------------------------------------------


def test_create_chat_stores_an_empty_consultation_and_announces_nothing(
    session: _RecordingSession,
) -> None:
    chat = _create_chat(session)

    assert session.rows(Chat) == [chat]
    assert (chat.user_id, chat.title, chat.active_operation_id) == (USER_ID, None, None)
    assert chat.deleted_at is None
    assert session.notifications == []
    assert session.commit_count == 1


def test_get_owned_chat_returns_the_owner_s_chat(session: _RecordingSession) -> None:
    chat = _create_chat(session)

    assert asyncio.run(chat_service.get_owned_chat(session, chat.id, USER_ID)) is chat


@pytest.mark.parametrize("user_id", [OTHER_USER_ID])
def test_get_owned_chat_hides_another_account_s_chat(
    session: _RecordingSession, user_id: str
) -> None:
    chat = _create_chat(session)

    assert asyncio.run(chat_service.get_owned_chat(session, chat.id, user_id)) is None


def test_get_owned_chat_reports_an_unknown_id_as_missing(session: _RecordingSession) -> None:
    _create_chat(session)

    assert asyncio.run(chat_service.get_owned_chat(session, "9" * 26, USER_ID)) is None


def test_list_chats_orders_by_last_activity_and_reports_the_total(
    session: _RecordingSession,
) -> None:
    now = datetime.now(UTC)
    older, newer, newest = (_create_chat(session) for _ in range(3))
    for index, chat in enumerate((newest, newer, older)):
        chat.updated_at = now - timedelta(minutes=index)

    rows, total = asyncio.run(chat_service.list_chats(session, USER_ID, limit=2, offset=0))

    assert [row.id for row in rows] == [newest.id, newer.id]
    assert total == 3


def test_list_chats_excludes_other_accounts(session: _RecordingSession) -> None:
    mine = _create_chat(session)
    _create_chat(session, OTHER_USER_ID)

    rows, total = asyncio.run(chat_service.list_chats(session, USER_ID, limit=100, offset=0))

    assert ([row.id for row in rows], total) == ([mine.id], 1)


def test_list_chats_paginates(session: _RecordingSession) -> None:
    now = datetime.now(UTC)
    chats = [_create_chat(session) for _ in range(3)]
    for index, chat in enumerate(chats):
        chat.updated_at = now - timedelta(minutes=index)

    rows, total = asyncio.run(chat_service.list_chats(session, USER_ID, limit=2, offset=2))

    assert ([row.id for row in rows], total) == ([chats[2].id], 3)


# --- soft delete --------------------------------------------------------------


def test_soft_delete_chat_stamps_deleted_at_without_an_event(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    session.log.clear()

    asyncio.run(chat_service.soft_delete_chat(session, chat))

    assert chat.deleted_at is not None
    assert session.rows(Chat) == [chat]
    assert session.log == ["commit"]
    assert session.notifications == []


def test_a_deleted_chat_is_gone_from_get_and_list(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    asyncio.run(chat_service.soft_delete_chat(session, chat))

    assert asyncio.run(chat_service.get_owned_chat(session, chat.id, USER_ID)) is None
    assert asyncio.run(chat_service.list_chats(session, USER_ID, limit=100, offset=0)) == ([], 0)


# --- message append -----------------------------------------------------------


def test_append_user_message_stores_the_message_with_empty_traces(
    session: _RecordingSession,
) -> None:
    chat = _create_chat(session)

    message = _user_message(session, chat, "I ride to work every day.")

    assert session.rows(ChatMessage) == [message]
    assert (message.chat_id, message.role) == (chat.id, ChatMessageRole.USER)
    assert (message.tool_calls, message.sources, message.recommendations) == ([], [], [])


def test_append_user_message_announces_nothing(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    session.log.clear()

    _user_message(session, chat, "Hello.")

    assert session.log == ["commit"]
    assert session.notifications == []


def test_append_user_message_bumps_last_activity(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    chat.updated_at = datetime.now(UTC) - timedelta(hours=1)

    _user_message(session, chat, "Hello.")

    assert chat.updated_at > datetime.now(UTC) - timedelta(minutes=1)


def test_the_first_user_message_titles_the_chat(session: _RecordingSession) -> None:
    chat = _create_chat(session)

    _user_message(session, chat, "Looking for an A2 bike")

    assert chat.title == "Looking for an A2 bike"


def test_the_title_is_truncated_to_the_column_width(session: _RecordingSession) -> None:
    chat = _create_chat(session)

    _user_message(session, chat, "x" * 500)

    assert chat.title == "x" * TITLE_LENGTH


def test_a_later_user_message_never_renames_the_chat(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    _user_message(session, chat, "First question")

    _user_message(session, chat, "Second question")

    assert chat.title == "First question"


def test_an_assistant_message_never_titles_the_chat(session: _RecordingSession) -> None:
    """The advisor speaks first, so its greeting must not name every chat."""
    chat = _create_chat(session)

    _assistant_message(session, chat, "Hello! What kind of riding do you do?")

    assert chat.title is None


def test_an_assistant_message_does_not_rename_a_titled_chat(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    _user_message(session, chat, "First question")

    _assistant_message(session, chat, "Here is my answer.")

    assert chat.title == "First question"


def test_append_assistant_message_stores_the_three_traces_verbatim(
    session: _RecordingSession,
) -> None:
    chat = _create_chat(session)
    tool_calls = [{"id": "call-1", "tool": "catalogue_search", "status": "succeeded"}]
    sources = [{"chunkId": "c1", "score": 0.03}]
    recommendations = [{"motorbikeId": "m1", "name": "Honda CB500F"}]

    message = _assistant_message(
        session,
        chat,
        "The CB500F fits.",
        tool_calls=tool_calls,
        sources=sources,
        recommendations=recommendations,
    )

    assert message.role is ChatMessageRole.ASSISTANT
    assert message.tool_calls == tool_calls
    assert message.sources == sources
    assert message.recommendations == recommendations


def test_append_assistant_message_ends_the_turn(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    chat.active_operation_id = OPERATION_ID

    _assistant_message(session, chat, "Sorry, something went wrong.")

    assert chat.active_operation_id is None


def test_append_assistant_message_announces_after_the_commit(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    session.log.clear()

    message = _assistant_message(session, chat, "Hello!")

    # The data commit, then the notification and the commit that delivers it.
    assert session.log == ["commit", "notify", "commit"]
    assert [channel for channel, _ in session.notifications] == [EVENT_CHANNEL]
    assert _payloads(session) == [
        {
            "event": "chat.message.created",
            "chatId": chat.id,
            "messageId": message.id,
            "role": "assistant",
        }
    ]


# --- list_messages ------------------------------------------------------------


def test_list_messages_returns_the_timeline_oldest_first(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    first = _user_message(session, chat, "First")
    second = _assistant_message(session, chat, "Second")
    third = _user_message(session, chat, "Third")
    stamp = datetime.now(UTC)
    for index, message in enumerate((third, second, first)):
        message.created_at = stamp - timedelta(minutes=index)

    timeline = asyncio.run(chat_service.list_messages(session, chat.id))

    assert [message.id for message in timeline] == [first.id, second.id, third.id]


def test_list_messages_falls_back_to_the_id_within_one_instant(
    session: _RecordingSession,
) -> None:
    """ULIDs are time-sortable, so equal timestamps still order deterministically."""
    chat = _create_chat(session)
    messages = [_user_message(session, chat, f"Message {index}") for index in range(3)]
    stamp = datetime.now(UTC)
    for message in messages:
        message.created_at = stamp

    ordered = asyncio.run(chat_service.list_messages(session, chat.id))

    assert [message.id for message in ordered] == sorted(message.id for message in messages)


def test_list_messages_is_scoped_to_one_chat(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    other = _create_chat(session)
    mine = _user_message(session, chat, "Mine")
    _user_message(session, other, "Theirs")

    timeline = asyncio.run(chat_service.list_messages(session, chat.id))

    assert [message.id for message in timeline] == [mine.id]


# --- preferences --------------------------------------------------------------


def test_record_preference_stores_an_active_row(session: _RecordingSession) -> None:
    chat = _create_chat(session)

    preference = asyncio.run(
        chat_service.record_preference(
            session,
            chat.id,
            attribute="budget",
            value="6000 EUR",
            firmness=PreferenceFirmness.HARD,
        )
    )

    assert session.rows(ChatPreference) == [preference]
    assert (preference.attribute, preference.value) == ("budget", "6000 EUR")
    assert preference.firmness is PreferenceFirmness.HARD
    assert preference.superseded_by_id is None
    assert asyncio.run(chat_service.active_preferences(session, chat.id)) == [preference]


def test_recording_the_same_attribute_supersedes_the_previous_row(
    session: _RecordingSession,
) -> None:
    chat = _create_chat(session)
    first = _record(session, chat.id, "budget", "6000 EUR")

    second = _record(session, chat.id, "budget", "8000 EUR")

    assert first.superseded_by_id == second.id
    assert second.superseded_by_id is None
    assert len(session.rows(ChatPreference)) == 2
    assert asyncio.run(chat_service.active_preferences(session, chat.id)) == [second]


def test_supersession_is_one_transaction(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    _record(session, chat.id, "budget", "6000 EUR")
    session.log.clear()

    _record(session, chat.id, "budget", "8000 EUR")

    assert session.log == ["commit"]


def test_a_third_answer_supersedes_only_the_active_row(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    first = _record(session, chat.id, "budget", "6000 EUR")
    second = _record(session, chat.id, "budget", "8000 EUR")

    third = _record(session, chat.id, "budget", "9000 EUR")

    assert (first.superseded_by_id, second.superseded_by_id) == (second.id, third.id)
    assert asyncio.run(chat_service.active_preferences(session, chat.id)) == [third]


def test_another_attribute_is_left_active(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    budget = _record(session, chat.id, "budget", "6000 EUR")
    licence = _record(session, chat.id, "licence", "A2")

    _record(session, chat.id, "budget", "8000 EUR")

    assert licence.superseded_by_id is None
    assert budget.superseded_by_id is not None


def test_the_same_attribute_in_another_chat_is_left_active(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    other = _create_chat(session)
    theirs = _record(session, other.id, "budget", "6000 EUR")

    _record(session, chat.id, "budget", "8000 EUR")

    assert theirs.superseded_by_id is None
    assert asyncio.run(chat_service.active_preferences(session, other.id)) == [theirs]


def test_active_preferences_is_scoped_to_one_chat(session: _RecordingSession) -> None:
    chat = _create_chat(session)
    other = _create_chat(session)
    mine = _record(session, chat.id, "budget", "6000 EUR")
    _record(session, other.id, "budget", "9000 EUR")

    assert asyncio.run(chat_service.active_preferences(session, chat.id)) == [mine]


def test_active_preferences_of_a_chat_without_any_is_empty(session: _RecordingSession) -> None:
    chat = _create_chat(session)

    assert asyncio.run(chat_service.active_preferences(session, chat.id)) == []
