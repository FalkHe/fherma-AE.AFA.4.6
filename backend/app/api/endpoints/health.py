"""Liveness and readiness endpoints.

`/health` answers "is this process alive?" and therefore performs no I/O.
`/ready` answers "can this process serve traffic?" and checks PostgreSQL.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.health import HealthResponse, ReadinessResponse
from app.db.session import get_db_session
from app.services.readiness import is_database_reachable

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    """Report that the process is alive."""
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def ready(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReadinessResponse:
    """Report whether PostgreSQL is reachable; 503 when it is not."""
    if not await is_database_reachable(session):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="unavailable", database="unavailable")

    return ReadinessResponse(status="ready", database="ok")
