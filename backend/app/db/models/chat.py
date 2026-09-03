"""The three chat tables: consultations, their messages and captured preferences.

A `chats` row is one consultation with the advisor. Its messages are immutable
prose plus the JSONB trace of what the agent did for that turn; its preferences
are what the interview learned about the customer, superseded rather than
overwritten so the history of a changing mind survives.

Three deliberate shapes, all pinned by
`docs/roadmap/phase-3/shared-knowledge.md`:

* **`chats.deleted_at` is the only lifecycle flag** — there is no `status`
  column. Every read filters `deleted_at IS NULL`, so a deleted consultation
  answers 404 and un-deleting is a database operation, not an API path.
* **`chats.active_operation_id` carries no foreign key.** It mirrors the loose
  entity coupling of `operations` (an operation may outlive what it worked on)
  and it is the *only* input to the UI's typing indicator.
* **Tool traffic never becomes rows.** A turn's tool calls, retrieved sources
  and recommendation snapshots live in the three JSONB columns of the assistant
  message, stored camelCase exactly as the API serves them.

As everywhere in this project the models declare **no relationships**: callers
resolve ids through `app.services.chat_service`.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

# The title is derived from the first user message and truncated to this width.
TITLE_LENGTH = 160
ATTRIBUTE_LENGTH = 64
VALUE_LENGTH = 256

# The JSONB columns of a message are lists; an empty trace is an empty list.
_EMPTY_JSON_ARRAY = text("'[]'::jsonb")


class ChatMessageRole(StrEnum):
    """Who wrote a message.

    Only these two: the system prompt is code and never a row, and tool traffic
    lives in the JSONB columns of the assistant message it belongs to.
    """

    USER = "user"
    ASSISTANT = "assistant"


class PreferenceFirmness(StrEnum):
    """How committed the customer is to a captured preference.

    `hard` is a constraint the advisor must respect (a licence class, a budget
    ceiling), `soft` a leaning, `exploring` a possibility being tried on.
    """

    HARD = "hard"
    SOFT = "soft"
    EXPLORING = "exploring"


class Chat(ULIDPrimaryKeyMixin, Base):
    """One consultation between a customer and the advisor.

    `title` is set once, by the service, from the first **user** message (the
    advisor's opening greeting must not name the conversation) and is not
    user-editable. `updated_at` doubles as last activity: the service bumps it
    on every message append, and the consultation list is ordered by it.
    """

    __tablename__ = "chats"

    user_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting an account takes its consultations with it.
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # NULL until the first user message; the UI falls back to an i18n label.
    title: Mapped[str | None] = mapped_column(String(TITLE_LENGTH))
    # Set when a response turn starts, cleared in the same transaction that
    # persists the assistant message — on the failure path too. Deliberately no
    # foreign key (see the module docstring).
    active_operation_id: Mapped[str | None] = mapped_column(String(ULID_LENGTH))
    # Soft delete: set once, never unset through the API.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(ULIDPrimaryKeyMixin, Base):
    """One turn of a consultation — immutable once written.

    `body` is markdown for the assistant and plain text for the customer (length
    is bounded at the API boundary). The three JSONB columns are the assistant's
    trace of that turn and are served verbatim, so they are stored in the
    camelCase shapes pinned in shared-knowledge; a user message carries three
    empty lists.

    There is no `updated_at` and no sequence column: a message is never edited,
    and ULIDs are time-sortable, so the timeline is `created_at ASC, id ASC`.
    """

    __tablename__ = "chat_messages"

    chat_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting a consultation takes its messages with it.
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        # Native PostgreSQL enum carrying the member *values* (see `User.role`).
        Enum(
            ChatMessageRole,
            name="chat_message_role",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    body: Mapped[str] = mapped_column(Text)
    # Every executed tool call of this turn, in the pinned camelCase shape.
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=_EMPTY_JSON_ARRAY
    )
    # Retrieved knowledge-base chunks backing this answer.
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=_EMPTY_JSON_ARRAY)
    # Write-time snapshots of the recommended models: the cards must stay
    # renderable without reading the catalogue.
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=_EMPTY_JSON_ARRAY
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatPreference(ULIDPrimaryKeyMixin, Base):
    """One thing the interview learned, with how firmly it was said.

    Preferences are append-only: when the same `attribute` is captured again for
    the same chat, the new row is inserted and the old one is pointed at it
    through `superseded_by_id`. A row with `superseded_by_id IS NULL` is
    therefore the current answer, and the superseded rows keep the history.

    `attribute` is a prompt-guided vocabulary, not a database enum: the advisor
    may learn something the schema never anticipated.
    """

    __tablename__ = "chat_preferences"

    chat_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting a consultation takes its preferences with it.
        ForeignKey("chats.id", ondelete="CASCADE"),
        index=True,
    )
    attribute: Mapped[str] = mapped_column(String(ATTRIBUTE_LENGTH))
    value: Mapped[str] = mapped_column(String(VALUE_LENGTH))
    firmness: Mapped[PreferenceFirmness] = mapped_column(
        # Native PostgreSQL enum carrying the member *values* (see `User.role`).
        Enum(
            PreferenceFirmness,
            name="preference_firmness",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    # Self-reference, no relationship: non-null means this row is history.
    superseded_by_id: Mapped[str | None] = mapped_column(
        String(ULID_LENGTH), ForeignKey("chat_preferences.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
