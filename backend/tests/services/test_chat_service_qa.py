"""QA additions to `app/services/chat_service.py`.

The dev agent's own `test_chat_service.py` already exhaustively covers
supersession, the title-once rule, the announce-after-commit ordering, message
ordering (incl. the ULID tiebreaker) and soft-delete visibility. This file only
adds the pinned edges that file leaves unexercised:

* `list_chats`'s secondary sort key — `id DESC` — is only exercised by the dev
  file through chats that also differ in `updated_at`; this proves the
  tiebreaker itself, for rows touched in the same instant.
* `append_assistant_message` bumps `updated_at` too (the dev file only proves
  this for `append_user_message`), since shared-knowledge pins it as "every
  message append", not just user ones.
* `get_owned_chat` returns `None` when a chat is *both* foreign and
  soft-deleted (the dev file proves each condition separately) — a
  security-critical existence-leak guard worth confirming directly rather than
  inferring from independent WHERE clauses.

Step 3.5 additions (QA, independent of the dev's own healing coverage which
lives entirely behind the `POST /api/chat-messages` route in
`tests/api/test_chat_messages.py`): `heal_stale_turn` exercised directly at the
service seam, including the exact-boundary second the API-level tests do not
touch (they use threshold-5s and threshold+1s, never the threshold itself).
"""

import asyncio
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.db.models.chat import Chat
from app.db.models.operation import Operation, OperationStatus
from app.services import chat_service, operation_service
from tests.services.conftest import FakeAsyncSession

USER_ID = "0" * 22 + "USER"
OTHER_USER_ID = "1" * 22 + "USER"


def test_list_chats_breaks_a_tied_updated_at_by_id_descending(
    fake_session: FakeAsyncSession,
) -> None:
    chats = [asyncio.run(chat_service.create_chat(fake_session, USER_ID)) for _ in range(3)]
    same_instant = datetime.now(UTC)
    for chat in chats:
        chat.updated_at = same_instant

    rows, total = asyncio.run(chat_service.list_chats(fake_session, USER_ID, limit=100, offset=0))

    assert [row.id for row in rows] == sorted((chat.id for chat in chats), reverse=True)
    assert total == 3


def test_append_assistant_message_also_bumps_last_activity(
    fake_session: FakeAsyncSession,
) -> None:
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    chat.updated_at = datetime.now(UTC) - timedelta(hours=1)

    asyncio.run(chat_service.append_assistant_message(fake_session, chat, "Hello there."))

    assert chat.updated_at > datetime.now(UTC) - timedelta(minutes=1)


def test_get_owned_chat_hides_a_soft_deleted_chat_even_for_a_foreign_owner(
    fake_session: FakeAsyncSession,
) -> None:
    """Belt-and-braces: the ownership *and* soft-delete filters combined still
    resolve to the same no-existence-leak `None`, not an exception or a hit."""
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    asyncio.run(chat_service.soft_delete_chat(fake_session, chat))

    assert asyncio.run(chat_service.get_owned_chat(fake_session, chat.id, OTHER_USER_ID)) is None
    assert asyncio.run(chat_service.get_owned_chat(fake_session, chat.id, USER_ID)) is None


def test_list_chats_still_excludes_a_soft_deleted_chat_among_live_ones(
    fake_session: FakeAsyncSession,
) -> None:
    live = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    deleted = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    asyncio.run(chat_service.soft_delete_chat(fake_session, deleted))

    rows, total = asyncio.run(chat_service.list_chats(fake_session, USER_ID, limit=100, offset=0))

    assert ([row.id for row in rows], total) == ([live.id], 1)


def test_a_message_body_is_stored_verbatim_not_only_the_truncated_title(
    fake_session: FakeAsyncSession,
) -> None:
    """Landed-decisions note: `append_user_message` stores `body` verbatim and
    only *derives* the (truncated) title from it — the message itself must
    not be truncated."""
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    long_body = "x" * 500

    message = asyncio.run(chat_service.append_user_message(fake_session, chat, long_body))

    assert message.body == long_body
    assert len(chat.title) == 160


def test_list_messages_has_no_pagination_parameters() -> None:
    """Landed-decisions note: `list_messages(session, chat_id)` is unpaginated
    by pin — confirm the signature carries no `limit`/`offset`."""
    import inspect

    parameters = inspect.signature(chat_service.list_messages).parameters
    assert set(parameters) == {"session", "chat_id"}


def test_chat_model_has_no_status_column() -> None:
    """Deliberate omission pinned in shared-knowledge: `deleted_at` is the
    only lifecycle flag."""
    assert "status" not in Chat.__table__.columns


# --- Step 3.5: `heal_stale_turn`, exercised directly at the service seam ------


def _pointed_chat(
    session: FakeAsyncSession, *, status: OperationStatus, age_seconds: float
) -> tuple[Chat, Operation]:
    chat = asyncio.run(chat_service.create_chat(session, USER_ID))
    operation = asyncio.run(
        operation_service.create(
            session,
            chat_service.RESPONSE_OPERATION_TYPE,
            entity_type=operation_service.CHAT_ENTITY_TYPE,
            entity_id=chat.id,
        )
    )
    operation.status = status
    operation.created_at = datetime.now(UTC) - timedelta(seconds=age_seconds)
    chat.active_operation_id = operation.id
    return chat, operation


def test_heal_stale_turn_is_a_noop_when_no_pointer_is_set(fake_session: FakeAsyncSession) -> None:
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert chat.active_operation_id is None


def test_heal_stale_turn_clears_a_pointer_at_a_vanished_operation(
    fake_session: FakeAsyncSession,
) -> None:
    chat = asyncio.run(chat_service.create_chat(fake_session, USER_ID))
    chat.active_operation_id = "9" * 26

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert chat.active_operation_id is None


def test_heal_stale_turn_clears_a_pointer_at_a_succeeded_operation(
    fake_session: FakeAsyncSession,
) -> None:
    chat, operation = _pointed_chat(fake_session, status=OperationStatus.SUCCEEDED, age_seconds=0)

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert chat.active_operation_id is None
    # A terminal operation is left exactly as it was — healing only moves the pointer.
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.error is None


def test_heal_stale_turn_clears_a_pointer_at_a_failed_operation(
    fake_session: FakeAsyncSession,
) -> None:
    chat, operation = _pointed_chat(fake_session, status=OperationStatus.FAILED, age_seconds=0)
    operation.error = "some earlier failure"

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert chat.active_operation_id is None
    assert operation.error == "some earlier failure"


def test_heal_stale_turn_refuses_a_fresh_live_turn(fake_session: FakeAsyncSession) -> None:
    chat, operation = _pointed_chat(fake_session, status=OperationStatus.RUNNING, age_seconds=5)

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is False
    # Nothing moved: a genuinely live turn is untouched, not just refused.
    assert chat.active_operation_id == operation.id
    assert operation.status is OperationStatus.RUNNING
    assert operation.error is None


def test_heal_stale_turn_times_out_a_queued_turn_older_than_the_threshold(
    fake_session: FakeAsyncSession,
) -> None:
    chat, operation = _pointed_chat(
        fake_session,
        status=OperationStatus.QUEUED,
        age_seconds=chat_service.stale_turn_seconds() + 1,
    )

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert chat.active_operation_id is None
    assert operation.status is OperationStatus.FAILED
    assert operation.error == chat_service.TIMED_OUT_ERROR
    assert operation.finished_at is not None


def test_heal_stale_turn_times_out_a_running_turn_older_than_the_threshold(
    fake_session: FakeAsyncSession,
) -> None:
    chat, operation = _pointed_chat(
        fake_session,
        status=OperationStatus.RUNNING,
        age_seconds=chat_service.stale_turn_seconds() + 1,
    )

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert operation.status is OperationStatus.FAILED
    assert operation.error == chat_service.TIMED_OUT_ERROR


def test_heal_stale_turn_a_fraction_of_a_second_under_the_threshold_is_still_in_flight(
    fake_session: FakeAsyncSession,
) -> None:
    """The boundary itself: `>` STALE_TURN_SECONDS, not `>=`.

    Note: asserting the exact threshold second (`age_seconds ==
    STALE_TURN_SECONDS`) is not a meaningful test — by the time
    `heal_stale_turn` calls `datetime.now(UTC)`, strictly more than
    `STALE_TURN_SECONDS` has elapsed since `created_at` was stamped in this
    fixture, so that case always times out (confirmed while writing this test:
    it failed with `True != False`). A margin safely below the threshold but
    far tighter than the API-level tests' 5 s margin is the honest way to prove
    the comparison is strict."""
    chat, operation = _pointed_chat(
        fake_session,
        status=OperationStatus.RUNNING,
        age_seconds=chat_service.stale_turn_seconds() - 0.5,
    )

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is False
    assert chat.active_operation_id == operation.id
    assert operation.status is OperationStatus.RUNNING


def test_heal_stale_turn_one_second_over_the_threshold_times_out(
    fake_session: FakeAsyncSession,
) -> None:
    """The other side of the same boundary, for contrast with the test above."""
    chat, operation = _pointed_chat(
        fake_session,
        status=OperationStatus.RUNNING,
        age_seconds=chat_service.stale_turn_seconds() + 1,
    )

    assert asyncio.run(chat_service.heal_stale_turn(fake_session, chat)) is True
    assert operation.status is OperationStatus.FAILED


def test_stale_turn_seconds_is_derived_from_the_agent_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step 3.13 resolved the interim constant: the threshold is
    `AGENT_TIMEOUT_SECONDS` + the grace period, read at call time — so the
    healing window cannot drift away from the time a turn is actually given, and
    the pinned 150 s the SPA mirrors is what the default configuration yields."""
    settings = get_settings()
    assert settings.agent_timeout_seconds == 120
    assert chat_service.STALE_TURN_GRACE_SECONDS == 30
    assert chat_service.stale_turn_seconds() == 150
    # Derived, not a coincidence: a reconfigured timeout moves the threshold with it.
    monkeypatch.setattr(settings, "agent_timeout_seconds", 300)
    assert chat_service.stale_turn_seconds() == 330
    source = inspect.getsource(chat_service)
    assert "STALE_TURN_SECONDS = 150" not in source
