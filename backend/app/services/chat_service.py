"""Consultations: the chat timeline, the soft delete and the captured preferences.

This module owns its transactions and speaks no HTTP, like every service here.
Four rules live here and nowhere else:

* **Ownership and the soft delete are one check.** `get_owned_chat` returns
  `None` for a foreign *and* for a deleted chat, so a route cannot accidentally
  distinguish the two — both are 404, and no existence is leaked.
* **The title is set once, and only by a user message.** The advisor opens every
  consultation with a greeting; naming the conversation after it would title
  every chat identically. `append_assistant_message` therefore never touches
  `title`.
* **`active_operation_id` is cleared by the assistant message.** The reply
  itself is the end of the turn — success or apology — so the insert and the
  clearing share one transaction and the UI can never be left typing forever
  next to a delivered answer.
* **Preferences are superseded, never overwritten.** Recording an attribute the
  chat already knows inserts the new row and points the old one at it, in one
  transaction; `superseded_by_id IS NULL` is the current answer.

Two more rules arrived with the response turn:

* **`start_response` is the only way a turn begins.** Operation row first, then
  the pointer, then the task — each committed before the next, so a worker can
  never pick up a turn the API cannot yet see.
* **A stale pointer heals instead of blocking.** `heal_stale_turn` is what makes
  a killed worker recoverable: a pointer at a finished operation, or at one that
  has been queued or running for longer than a turn can possibly take, is
  cleared (the latter after failing that operation), and the consultation is
  free again. Only a genuinely live turn refuses a second message.

The `chat.message.created` announcement is published by
`append_assistant_message` **after** its commit, through
`operation_service.notify` — the project's only `app_events` writer, and the
ordering rule documented there. User messages announce nothing: their author
already knows, and the SPA's own mutation invalidates its caches.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.base import new_ulid
from app.db.models.chat import (
    TITLE_LENGTH,
    Chat,
    ChatMessage,
    ChatMessageRole,
    ChatPreference,
    PreferenceFirmness,
)
from app.db.models.operation import Operation, OperationStatus
from app.services import operation_service

# `operations.type` of one response turn.
RESPONSE_OPERATION_TYPE = "chat.response"

# The grace period added to one turn's own time budget before the API gives up
# on it: the agent loop is cancelled at `AGENT_TIMEOUT_SECONDS`, and the job
# still has to store the apology and fail the operation after that.
STALE_TURN_GRACE_SECONDS = 30

# What an admin reads on an operation this healing gave up on.
TIMED_OUT_ERROR = "Response timed out."

# The two statuses a turn cannot come back from.
_TERMINAL_STATUSES = frozenset({OperationStatus.SUCCEEDED, OperationStatus.FAILED})


def stale_turn_seconds() -> float:
    """Return how long a turn may be queued or running before it is considered lost.

    `AGENT_TIMEOUT_SECONDS` (what the agent loop gives itself) plus the grace
    period above — derived rather than configured, so the two can never drift
    apart. The frontend mirrors the sum as `CHAT_TURN_STALE_SECONDS`, so the
    composer re-opens at the same moment the API starts accepting messages
    again; changing `AGENT_TIMEOUT_SECONDS` means changing that constant too.

    A function, not a module constant: settings are read at call time, so a
    process that configures the timeout does not depend on import order.
    """
    return get_settings().agent_timeout_seconds + STALE_TURN_GRACE_SECONDS


async def create_chat(session: AsyncSession, user_id: str) -> Chat:
    """Create an empty consultation for `user_id` and return it.

    A chat is only ever created by an explicit request, never on page load, so
    there is nothing to announce: the caller is the only one who can see it.
    """
    chat = Chat(user_id=user_id)
    session.add(chat)
    await session.commit()
    return chat


async def get_owned_chat(session: AsyncSession, chat_id: str, user_id: str) -> Chat | None:
    """Return `user_id`'s live consultation `chat_id`, or `None`.

    `None` covers all three misses — unknown id, another account's chat and a
    soft-deleted one — because routes map every one of them to the same 404.
    """
    result = await session.execute(
        select(Chat).where(
            Chat.id == chat_id,
            Chat.user_id == user_id,
            Chat.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_chat(session: AsyncSession, chat_id: str) -> Chat | None:
    """Return the live consultation `chat_id`, whoever owns it, or `None`.

    The worker's loader: a task is enqueued with ids and has no signed-in
    account to check them against. Deleted consultations are still excluded —
    there is nobody left to answer — so `None` also means "do not bother".
    HTTP routes use `get_owned_chat` instead; this function performs no
    ownership check at all.
    """
    result = await session.execute(
        select(Chat).where(Chat.id == chat_id, Chat.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_chats(
    session: AsyncSession, user_id: str, *, limit: int, offset: int
) -> tuple[list[Chat], int]:
    """Return one page of `user_id`'s live consultations plus the total.

    Ordered by last activity (`updated_at` descending, id as tiebreaker so
    paging is stable for rows touched in the same instant) — not by creation,
    like the admin lists: a customer looks for the conversation they were just
    having.
    """
    conditions = (Chat.user_id == user_id, Chat.deleted_at.is_(None))

    total = await session.execute(select(func.count()).select_from(Chat).where(*conditions))
    page = await session.execute(
        select(Chat)
        .where(*conditions)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(page.scalars().all()), total.scalar_one()


async def soft_delete_chat(session: AsyncSession, chat: Chat) -> Chat:
    """Mark `chat` deleted; its messages stay in place behind the ownership check.

    Nothing is announced: only the owner can see this list, and their own
    mutation invalidates it.
    """
    chat.deleted_at = datetime.now(UTC)
    await session.commit()
    return chat


async def append_user_message(session: AsyncSession, chat: Chat, body: str) -> ChatMessage:
    """Store the customer's message, naming the consultation if it is still unnamed.

    `body` is already validated by the caller (stripped, non-empty, bounded):
    this is the persistence step, not the boundary.
    """
    message = _new_message(chat, ChatMessageRole.USER, body)
    session.add(message)
    if chat.title is None:
        # Set once, from the first *user* message — never from the greeting.
        chat.title = body[:TITLE_LENGTH]
    _touch(chat)
    await session.commit()
    return message


async def append_assistant_message(
    session: AsyncSession,
    chat: Chat,
    body: str,
    *,
    tool_calls: Sequence[dict[str, Any]] = (),
    sources: Sequence[dict[str, Any]] = (),
    recommendations: Sequence[dict[str, Any]] = (),
) -> ChatMessage:
    """Store the advisor's reply, end the turn and announce the message.

    The three traces are stored verbatim in the pinned camelCase shapes. Ending
    the turn means clearing `chat.active_operation_id` in the same transaction —
    this is the apologetic-failure path too, so a dead turn always releases the
    typing indicator.
    """
    message = _new_message(
        chat,
        ChatMessageRole.ASSISTANT,
        body,
        tool_calls=tool_calls,
        sources=sources,
        recommendations=recommendations,
    )
    session.add(message)
    # The turn is over. Deliberately not conditional: whatever pointer was
    # there, this reply is its answer.
    chat.active_operation_id = None
    _touch(chat)
    await session.commit()
    await _announce_message(session, chat.id, message.id)
    return message


async def start_response(session: AsyncSession, chat: Chat) -> Operation:
    """Begin a response turn for `chat`: operation row, pointer, task.

    The ordering is the pinned one and the reason this function exists: the
    `queued` operation commits, the pointer that makes the UI show the advisor
    typing commits, and only then is the task enqueued. A worker therefore never
    picks up a turn whose state is not yet visible — and if the enqueue itself is
    lost, the pointer heals on the next message instead of blocking forever.

    Callers check first: a chat with a live turn must not start a second one (see
    `heal_stale_turn`).
    """
    operation = await operation_service.create(
        session,
        RESPONSE_OPERATION_TYPE,
        entity_type=operation_service.CHAT_ENTITY_TYPE,
        entity_id=chat.id,
    )
    chat.active_operation_id = operation.id
    _touch(chat)
    await session.commit()
    await enqueue_chat_response(chat.id, operation.id)
    return operation


async def enqueue_chat_response(chat_id: str, operation_id: str) -> None:
    """Push `chat.respond` onto the queue — ids only, after both commits.

    The task module is imported inside the function on purpose: it pulls in the
    broker and, through the response service, this module — a top-level import
    would be circular and would drag the Redis wiring into every importer of the
    chat service. This is also the seam the test suite replaces, so no test ever
    needs Redis.
    """
    from app.jobs.chat import respond as chat_respond

    await chat_respond.kiq(chat_id, operation_id)


async def heal_stale_turn(session: AsyncSession, chat: Chat) -> bool:
    """Report whether `chat` may start a new turn, clearing a stale pointer.

    This is the kill-the-worker recovery: the pointer is a claim that somebody
    is answering, and this function is where that claim is checked instead of
    trusted.

    * No pointer, or one at an operation that no longer exists → free.
    * Pointer at a `succeeded`/`failed` operation → the turn is over; the
      pointer is cleared and the consultation is free.
    * Pointer at a `queued`/`running` operation older than
      `stale_turn_seconds()` → nobody is coming back for it: the operation is
      failed with `TIMED_OUT_ERROR`, the pointer is cleared, and the
      consultation is free.
    * Anything else → a turn is genuinely in flight; the caller answers 409.

    Returns:
        `True` when a new turn may start, `False` while one is in flight.
    """
    if chat.active_operation_id is None:
        return True

    operation = await operation_service.get(session, chat.active_operation_id)
    if operation is None:
        # A pointer at nothing: there is no turn and nothing to report into.
        await _clear_active_operation(session, chat)
        return True

    if operation.status in _TERMINAL_STATUSES:
        # The turn ended without the reply that would have cleared the pointer
        # (a crash between the two commits, or a `failed` operation).
        await _clear_active_operation(session, chat)
        return True

    if datetime.now(UTC) - operation.created_at > timedelta(seconds=stale_turn_seconds()):
        await operation_service.fail(session, operation, TIMED_OUT_ERROR)
        await _clear_active_operation(session, chat)
        return True

    return False


async def list_messages(session: AsyncSession, chat_id: str) -> list[ChatMessage]:
    """Return the whole timeline of `chat_id`, oldest first.

    `created_at ASC, id ASC`: ULIDs are time-sortable, so the id is a stable
    tiebreaker for two messages written in the same instant. Ownership is the
    caller's business — it checked the chat before asking for its messages.
    """
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    )
    return list(result.scalars().all())


async def record_preference(
    session: AsyncSession,
    chat_id: str,
    *,
    attribute: str,
    value: str,
    firmness: PreferenceFirmness,
) -> ChatPreference:
    """Capture what the interview learned, superseding the previous answer.

    One transaction: the new row is inserted and every other still-active row
    for the same `(chat, attribute)` is pointed at it. The insert must reach the
    database before the update, because `superseded_by_id` is a real foreign key
    — hence the explicit flush and the `id !=` guard, which keeps the fresh row
    itself out of the update.
    """
    preference = ChatPreference(
        # The id is needed as the update's value, before the flush would assign
        # it; the mixin's default is only a fallback for the simple cases.
        id=new_ulid(),
        chat_id=chat_id,
        attribute=attribute,
        value=value,
        firmness=firmness,
    )
    session.add(preference)
    await session.flush()
    await session.execute(
        update(ChatPreference)
        .where(
            ChatPreference.chat_id == chat_id,
            ChatPreference.attribute == attribute,
            ChatPreference.superseded_by_id.is_(None),
            ChatPreference.id != preference.id,
        )
        .values(superseded_by_id=preference.id)
    )
    await session.commit()
    return preference


async def active_preferences(session: AsyncSession, chat_id: str) -> list[ChatPreference]:
    """Return the preferences of `chat_id` that have not been superseded.

    Oldest first, like the timeline: the agent renders them as a block in its
    system prompt, and a stable order keeps that prompt stable.
    """
    result = await session.execute(
        select(ChatPreference)
        .where(
            ChatPreference.chat_id == chat_id,
            ChatPreference.superseded_by_id.is_(None),
        )
        .order_by(ChatPreference.created_at.asc(), ChatPreference.id.asc())
    )
    return list(result.scalars().all())


def _new_message(
    chat: Chat,
    role: ChatMessageRole,
    body: str,
    *,
    tool_calls: Sequence[dict[str, Any]] = (),
    sources: Sequence[dict[str, Any]] = (),
    recommendations: Sequence[dict[str, Any]] = (),
) -> ChatMessage:
    """Build a message row with the three JSONB columns always populated.

    The columns are NOT NULL with a server default, but the services fill enum
    and JSONB defaults in Python (the project-wide convention), so a freshly
    built row is complete before it is ever flushed.
    """
    return ChatMessage(
        chat_id=chat.id,
        role=role,
        body=body,
        tool_calls=list(tool_calls),
        sources=list(sources),
        recommendations=list(recommendations),
    )


async def _clear_active_operation(session: AsyncSession, chat: Chat) -> None:
    """Release the typing indicator of a turn that will not deliver a reply.

    Nothing is announced: the only client that cares is the one asking for this
    check, and its own request is what re-reads the consultation.
    """
    chat.active_operation_id = None
    _touch(chat)
    await session.commit()


def _touch(chat: Chat) -> None:
    """Bump `updated_at`, which doubles as the consultation's last activity.

    Set explicitly rather than left to the column's server-side `onupdate`: a
    second message on an already-titled chat changes nothing else on the row, so
    without this the UPDATE would not happen at all and the list order would
    freeze. An explicit value wins over `onupdate`.
    """
    chat.updated_at = datetime.now(UTC)


async def _announce_message(session: AsyncSession, chat_id: str, message_id: str) -> None:
    """Publish the pinned `chat.message.created` payload — ids only, after commit."""
    await operation_service.notify(
        session,
        {
            "event": "chat.message.created",
            "chatId": chat_id,
            "messageId": message_id,
            "role": ChatMessageRole.ASSISTANT.value,
        },
    )
