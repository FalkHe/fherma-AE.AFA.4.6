"""Schemas for the `documents` resource.

Wire shape is pinned by `docs/roadmap/phase-2/shared-knowledge.md`: resource
type `documents`, camelCase attributes, read-only. Documents are written by
ingestion only — there is deliberately no request model, so no admin can edit
the prose the extraction and the knowledge base were built from.

`raw_path` is **not** exposed: it points into the server's `DATA_DIR` and the
review screen renders `contentMarkdown`. The rest of the row is provenance, and
all of it ships, because judging a document means knowing where it came from.
"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from app.api.jsonapi import JsonApiModel, ListDocument, Resource
from app.db.models.source_document import SourceType

DOCUMENT_TYPE = "documents"


class DocumentAttributes(JsonApiModel):
    """The pinned attribute set of a source document."""

    # Built straight from the ORM row.
    model_config = ConfigDict(from_attributes=True)

    source_type: SourceType
    source_url: str | None
    source_title: str
    content_markdown: str
    fetched_at: datetime
    created_at: datetime


class DocumentResource(Resource[DocumentAttributes]):
    """A source-document resource object."""

    type: Literal["documents"] = DOCUMENT_TYPE


class DocumentListDocument(ListDocument[DocumentResource]):
    """Body of `GET /api/documents`."""
