"""Schemas for the `manufacturers` resource.

Wire shape is pinned by `docs/roadmap/stage-01/phase-2b/shared-knowledge.md`: resource
type `manufacturers`, camelCase attributes `name`, `slug`, `description`,
`logoPath`, `createdAt`, `updatedAt` — `null` for the two columns no writer
fills yet.

**Read-only on purpose**, so there is no request model here: a brand row is
created only by `manufacturer_service.get_or_create` (extraction and the
`catalogue set-manufacturer` CLI). `logoPath` is the MEDIA_DIR-relative path of
the model, not a URL — nothing serves brand logos yet.

`BuildinglinesDocument` (step 6.20, ui-spec API-5) is not a JSON:API resource
document — it backs one admin-only read (`GET
/api/manufacturers/{id}/buildinglines`), so its body is the plain `{"data": […
of str]}` shape the step pins, not a `Resource`/`type`/`attributes` envelope.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api.jsonapi import Document, JsonApiModel, ListDocument, Resource

MANUFACTURER_TYPE = "manufacturers"


class ManufacturerAttributes(JsonApiModel):
    """The pinned attribute set of a manufacturer."""

    # Built straight from the ORM row: every attribute is a column.
    model_config = ConfigDict(from_attributes=True)

    name: str
    slug: str
    description: str | None
    logo_path: str | None
    created_at: datetime
    updated_at: datetime


class ManufacturerResource(Resource[ManufacturerAttributes]):
    """A manufacturer resource object."""

    type: Literal["manufacturers"] = MANUFACTURER_TYPE


class ManufacturerDocument(Document[ManufacturerResource]):
    """Body of `GET /api/manufacturers/{id}`."""


class ManufacturerListDocument(ListDocument[ManufacturerResource]):
    """Body of `GET /api/manufacturers`."""


class BuildinglinesDocument(BaseModel):
    """Body of `GET /api/manufacturers/{id}/buildinglines`: `{"data": [...]}`."""

    model_config = ConfigDict(extra="forbid")

    data: list[str]
