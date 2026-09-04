"""Schemas for the `chats` resource: one consultation with the advisor.

Wire shape is pinned by `docs/roadmap/stage-01/phase-3/shared-knowledge.md`: resource
type `chats`, camelCase attributes `title`, `activeOperationId`, `createdAt`,
`updatedAt`.

Two deliberate absences:

* **`deletedAt` is not an attribute.** The soft delete is invisible on the wire:
  a deleted consultation is simply gone (404), so there is nothing to render and
  no un-delete path to hint at.
* **There is no patch model.** Renaming is out of scope this phase, and the
  title is derived from the first user message — nothing about a consultation is
  user-editable.

A create request therefore carries an **empty attributes object**: a
consultation is created empty and the advisor speaks first. The object is still
required and still `extra="forbid"`, so a client that invents an attribute (a
title, say) gets a 422 instead of a silent no-op.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api.jsonapi import Document, JsonApiModel, ListDocument, Resource

CHAT_TYPE = "chats"


class ChatAttributes(JsonApiModel):
    """The pinned attribute set of a consultation."""

    # Built straight from the ORM row.
    model_config = ConfigDict(from_attributes=True)

    title: str | None
    # Non-null exactly while a response turn is in flight; the SPA's typing
    # indicator is driven by this attribute and by nothing else.
    active_operation_id: str | None
    created_at: datetime
    # Doubles as last activity: the service bumps it on every message append.
    updated_at: datetime


class ChatResource(Resource[ChatAttributes]):
    """A consultation resource object."""

    type: Literal["chats"] = CHAT_TYPE


class ChatDocument(Document[ChatResource]):
    """Body of `GET`/`POST` on a single consultation."""


class ChatListDocument(ListDocument[ChatResource]):
    """Body of `GET /api/chats`."""


class ChatCreateAttributes(JsonApiModel):
    """No attributes at all — a consultation is created empty."""

    model_config = ConfigDict(extra="forbid")


class ChatCreateResource(BaseModel):
    """The resource object of a create request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["chats"] = CHAT_TYPE
    attributes: ChatCreateAttributes


class ChatCreateRequest(BaseModel):
    """Body of `POST /api/chats`."""

    model_config = ConfigDict(extra="forbid")

    data: ChatCreateResource
