"""The `documents` resource: the ingested prose behind one catalogue entry.

Read-only by design — documents are written by ingestion, and the review screen
only ever reads them back, so there is no route that could edit the text the
extraction and the knowledge base were derived from.

`filter[product]` is **required**: a document only means something next to the
model it was fetched for, and the whole corpus is neither paged nor searchable
here. Ordering is the pinned one (`document_service` owns it): the Wikipedia
article first, then oldest to newest — the order the review screen reads in.

The whole router is admin-only (`current_admin`), like every `/api/*` resource
in this phase. No `csrf_protect`: there is no write to protect.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import current_admin
from app.api.schemas.documents import (
    DocumentAttributes,
    DocumentListDocument,
    DocumentResource,
)
from app.db.models.source_document import SourceDocument
from app.db.session import get_db_session
from app.services import document_service

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(current_admin)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

PRODUCT_FILTER_DESCRIPTION = "ULID of the product whose documents to return (required)."


def _resource(document: SourceDocument) -> DocumentResource:
    """Project one document row onto a resource object."""
    return DocumentResource(id=document.id, attributes=DocumentAttributes.model_validate(document))


def _product_id(raw: str | None) -> str:
    """Return the single product id `filter[product]` carries.

    Absent is a client error rather than "everything": listing every document of
    the catalogue is not a use case, and silently doing it would ship megabytes
    of Markdown.
    """
    members = jsonapi.parse_filter(raw)
    if members is None:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="missing-filter",
            detail="filter[product] is required: documents are listed per product.",
        )
    if len(members) != 1:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail="filter[product] takes exactly one product id.",
        )
    return members[0]


@router.get(
    "",
    response_model=DocumentListDocument,
    summary="List the source documents of one product",
    responses=jsonapi.error_responses(status.HTTP_400_BAD_REQUEST),
)
async def list_documents(
    session: SessionDep,
    product_filter: Annotated[
        str | None,
        Query(alias="filter[product]", description=PRODUCT_FILTER_DESCRIPTION),
    ] = None,
) -> DocumentListDocument:
    """Return every document of one product, Wikipedia first, then oldest first.

    Unpaginated on purpose: ingestion stores a handful of documents per model
    (one Wikipedia article plus at most six web sources), and the review screen
    needs the complete list to build its document picker.
    """
    documents = await document_service.list_for_motorbike(session, _product_id(product_filter))

    return DocumentListDocument(
        data=[_resource(document) for document in documents],
        meta=jsonapi.Meta(total_count=len(documents)),
    )
