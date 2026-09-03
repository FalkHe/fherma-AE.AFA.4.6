"""Schemas for the `operations` resource.

Wire shape is pinned by `docs/roadmap/phase-2/shared-knowledge.md`: resource
type `operations`, camelCase attributes, read-only. There is deliberately no
request model — operations are created and advanced by services, never over
HTTP, so the API cannot invent job state.

Note the two different `type`s: the resource object's `type` is the JSON:API
resource name (`"operations"`), while the `type` *attribute* is the job family
(`"ingestion"`, `"demo"`, …). `updated_at` is not exposed: the timestamps that
mean something to an admin are the three lifecycle ones.
"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from app.api.jsonapi import JsonApiModel, ListDocument, Resource
from app.db.models.operation import OperationStatus

OPERATION_TYPE = "operations"


class OperationAttributes(JsonApiModel):
    """The pinned attribute set of an operation."""

    # Built straight from the ORM row.
    model_config = ConfigDict(from_attributes=True)

    type: str
    status: OperationStatus
    progress: int
    message: str | None
    error: str | None
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class OperationResource(Resource[OperationAttributes]):
    """An operation resource object."""

    type: Literal["operations"] = OPERATION_TYPE


class OperationListDocument(ListDocument[OperationResource]):
    """Body of `GET /api/operations`."""
