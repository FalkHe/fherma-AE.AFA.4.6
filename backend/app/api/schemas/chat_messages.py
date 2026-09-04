"""Schemas for the `chat-messages` resource: one turn of a consultation.

Wire shape is pinned by `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Persisted
JSONB shapes, §JSON:API resources): resource type `chat-messages`, attributes
`role`, `body`, `toolCalls`, `sources`, `recommendations`, `createdAt`.

**The three JSONB attributes are typed, not opaque.** They are *stored* in
exactly the camelCase shapes the item models below describe, so nothing is
re-mapped at read time — but declaring the models instead of `list[dict]` is
what puts `ToolCall`, `MessageSource` and `Recommendation` into the OpenAPI
schema, and therefore into the generated client the chat UI renders from. The
consequence for every writer of those columns: **it must emit every key of these
models**, camelCase, or the read path fails loudly. `arguments` and `result` of
a tool call stay open objects — their shape is the tool's business, and the UI
has a generic renderer for anything unstyled.

The create request carries `{chatId, body}`. `chatId` is an **attribute, not a
JSON:API relationship**: the internal JSON:API layer has no relationship
machinery, and this is the pinned simplification. `body` is validated here and
nowhere else — `chat_service.append_user_message` stores what it is given
verbatim, so this schema is the boundary that strips it, rejects a blank one and
enforces the pinned 4000-character ceiling.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.jsonapi import Document, JsonApiModel, ListDocument, Resource
from app.api.schemas.products import PriceBand, SpecCategory
from app.db.models.base import ULID_LENGTH
from app.db.models.chat import ChatMessageRole

CHAT_MESSAGE_TYPE = "chat-messages"

# A schema constant, deliberately not config: it is part of the wire contract
# the SPA's composer counts against.
BODY_MAX_LENGTH = 4000

# Canonical Crockford base32 alphabet (excludes I, L, O, U — never emitted by
# `new_ulid`), so a syntactically impossible id is a 422 before it ever
# reaches a lookup; an unknown-but-well-formed id still answers 404.
CHAT_ID_PATTERN = r"^[0-9A-HJKMNP-TV-Z]+$"


class ToolCallStatus(StrEnum):
    """How an executed tool call ended."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolCall(JsonApiModel):
    """One tool the advisor executed for this turn, with its outcome.

    Every executed call is recorded — the retrieval and comparison tools graders
    look for, and the write tools (`record_preference`, `flag_unknown_bike`,
    `present_recommendations`) alike.
    """

    id: str
    tool: str
    # Open objects on purpose: each tool has its own argument and result shape.
    arguments: dict[str, Any]
    result: dict[str, Any]
    status: ToolCallStatus
    error: str | None


class MessageSource(JsonApiModel):
    """One knowledge-base chunk backing this answer.

    Provenance, not prose: the UI shows title, heading path and a link, and the
    `chunkId` is what ties a claim back to the ingested document it came from.
    """

    chunk_id: str
    motorbike_id: str
    source_document_id: str
    source_url: str | None
    source_title: str
    heading_path: str | None
    score: float


class RecommendationKeySpecs(JsonApiModel):
    """The specification snippet a recommendation card shows.

    Every field is nullable: a missing verified specification stays missing —
    the advisor never guesses a number.
    """

    category: SpecCategory | None
    engine_cc: int | None
    power_kw: float | None
    wet_weight_kg: float | None
    seat_height_mm: int | None
    price_band: PriceBand | None


class Recommendation(JsonApiModel):
    """One recommended model, snapshotted when the answer was written.

    A write-time snapshot rather than a catalogue reference: plain users cannot
    read `/api/products` in this phase, so the card has to be self-contained.
    Staleness is accepted.
    """

    motorbike_id: str
    name: str
    image_url: str | None
    rationale: str
    matched_preferences: list[str]
    key_specs: RecommendationKeySpecs


class ChatMessageAttributes(JsonApiModel):
    """The pinned attribute set of a message.

    The three traces are empty lists on a user message and on an assistant
    message that needed no tools.
    """

    # Built straight from the ORM row; the JSONB columns already hold the
    # camelCase shapes of the item models.
    model_config = ConfigDict(from_attributes=True)

    role: ChatMessageRole
    body: str
    tool_calls: list[ToolCall]
    sources: list[MessageSource]
    recommendations: list[Recommendation]
    created_at: datetime


class ChatMessageResource(Resource[ChatMessageAttributes]):
    """A message resource object."""

    type: Literal["chat-messages"] = CHAT_MESSAGE_TYPE


class ChatMessageDocument(Document[ChatMessageResource]):
    """Body of `POST /api/chat-messages`."""


class ChatMessageListDocument(ListDocument[ChatMessageResource]):
    """Body of `GET /api/chat-messages`."""


class ChatMessageCreateAttributes(JsonApiModel):
    """What a customer may send: which consultation, and what they said."""

    model_config = ConfigDict(extra="forbid")

    chat_id: Annotated[
        str,
        Field(
            min_length=ULID_LENGTH,
            max_length=ULID_LENGTH,
            pattern=CHAT_ID_PATTERN,
            description="ULID of the consultation this message belongs to.",
        ),
    ]
    body: Annotated[
        str,
        Field(
            min_length=1,
            max_length=BODY_MAX_LENGTH,
            description=f"The customer's message, at most {BODY_MAX_LENGTH} characters.",
        ),
    ]

    @field_validator("body")
    @classmethod
    def check_body_is_not_blank(cls, value: str) -> str:
        """Trim the message and reject one that is only whitespace."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message body must not be blank.")
        return stripped


class ChatMessageCreateResource(BaseModel):
    """The resource object of a create request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["chat-messages"] = CHAT_MESSAGE_TYPE
    attributes: ChatMessageCreateAttributes


class ChatMessageCreateRequest(BaseModel):
    """Body of `POST /api/chat-messages`."""

    model_config = ConfigDict(extra="forbid")

    data: ChatMessageCreateResource
