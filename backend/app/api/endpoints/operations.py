"""The `operations` resource: what the admin UI reads job progress from.

Read-only by design. Operations are written by the services that run the jobs;
nothing over HTTP may create, advance or cancel one, so a browser can never
disagree with a worker about what a job did.

The whole router is admin-only (`current_admin`) — like every `/api/*` resource
in this phase, reads included. No `csrf_protect`: there is no write to protect.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import current_admin
from app.api.schemas.operations import (
    OperationAttributes,
    OperationListDocument,
    OperationResource,
)
from app.db.models.operation import Operation, OperationStatus
from app.db.session import get_db_session
from app.services import operation_service

router = APIRouter(
    prefix="/operations",
    tags=["operations"],
    dependencies=[Depends(current_admin)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

STATUS_FILTER_DESCRIPTION = "Comma-separated list of statuses: " + ", ".join(
    member.value for member in OperationStatus
)
ENTITY_TYPE_FILTER_DESCRIPTION = "Comma-separated list of entity types, e.g. `motorbike`."
ENTITY_ID_FILTER_DESCRIPTION = "Comma-separated list of entity ids."


def _resource(operation: Operation) -> OperationResource:
    """Project one operation row onto a resource object."""
    return OperationResource(
        id=operation.id, attributes=OperationAttributes.model_validate(operation)
    )


def _parse_status_filter(raw: str | None) -> list[OperationStatus] | None:
    """Turn `filter[status]` into statuses; `None` means unfiltered."""
    members = jsonapi.parse_filter(raw)
    if members is None:
        return None

    try:
        return [OperationStatus(member) for member in members]
    except ValueError as error:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail=f"{STATUS_FILTER_DESCRIPTION}.",
        ) from error


@router.get(
    "",
    response_model=OperationListDocument,
    summary="List operations",
    responses=jsonapi.error_responses(status.HTTP_400_BAD_REQUEST),
)
async def list_operations(
    session: SessionDep,
    page: jsonapi.PaginationDep,
    entity_type_filter: Annotated[
        str | None,
        Query(alias="filter[entityType]", description=ENTITY_TYPE_FILTER_DESCRIPTION),
    ] = None,
    entity_id_filter: Annotated[
        str | None,
        Query(alias="filter[entityId]", description=ENTITY_ID_FILTER_DESCRIPTION),
    ] = None,
    status_filter: Annotated[
        str | None,
        Query(alias="filter[status]", description=STATUS_FILTER_DESCRIPTION),
    ] = None,
) -> OperationListDocument:
    """Return one page of operations, newest first."""
    operations, total = await operation_service.list_operations(
        session,
        entity_types=jsonapi.parse_filter(entity_type_filter),
        entity_ids=jsonapi.parse_filter(entity_id_filter),
        statuses=_parse_status_filter(status_filter),
        limit=page.limit,
        offset=page.offset,
    )

    return OperationListDocument(
        data=[_resource(operation) for operation in operations],
        meta=jsonapi.Meta(total_count=total),
    )
