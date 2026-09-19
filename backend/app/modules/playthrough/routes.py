from fastapi import APIRouter, Query

from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.schemas import ErrorEnvelope
from app.modules.auth.dependencies import CsrfAuth, CurrentAuth
from app.modules.playthrough import service
from app.modules.playthrough.errors import PlaythroughError
from app.modules.playthrough.schemas import (
    CampaignRunRead,
    CharacterRead,
    EventRead,
    RenameCampaignRunRequest,
    StartCampaignRunRequest,
)

router = APIRouter()


@router.post(
    "/campaign",
    status_code=201,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
)
async def start_campaign_run(
    payload: StartCampaignRunRequest, auth: CsrfAuth, db: DbSession
) -> CampaignRunRead:
    try:
        run = await service.start_campaign_run(
            db, user_id=auth.user.id, campaign_id=payload.campaign_id
        )
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return CampaignRunRead.model_validate(run)


@router.get("/campaign", responses={401: {"model": ErrorEnvelope}})
async def list_campaign_runs(auth: CurrentAuth, db: DbSession) -> list[CampaignRunRead]:
    try:
        runs = await service.list_campaign_runs(db, user_id=auth.user.id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return [CampaignRunRead.model_validate(run) for run in runs]


@router.get(
    "/campaign/{run_id}",
    responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def get_campaign_run(run_id: str, auth: CurrentAuth, db: DbSession) -> CampaignRunRead:
    try:
        run = await service.get_campaign_run(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return CampaignRunRead.model_validate(run)


@router.post(
    "/campaign/{run_id}/character",
    status_code=201,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
    },
)
async def create_character(run_id: str, auth: CsrfAuth, db: DbSession) -> CharacterRead:
    try:
        character = await service.create_character(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return CharacterRead.model_validate(character)


@router.patch(
    "/campaign/{run_id}",
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
    },
)
async def rename_campaign_run(
    run_id: str, payload: RenameCampaignRunRequest, auth: CsrfAuth, db: DbSession
) -> CampaignRunRead:
    try:
        run = await service.rename_campaign_run(
            db, user_id=auth.user.id, run_id=run_id, title=payload.title
        )
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return CampaignRunRead.model_validate(run)


@router.post(
    "/campaign/{run_id}/archive",
    status_code=204,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
)
async def archive_campaign_run(run_id: str, auth: CsrfAuth, db: DbSession) -> None:
    try:
        await service.archive_campaign_run(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc


@router.get(
    "/campaign/{run_id}/events",
    responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def list_events(
    run_id: str,
    auth: CurrentAuth,
    db: DbSession,
    after: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[EventRead]:
    try:
        events = await service.list_events(
            db, user_id=auth.user.id, run_id=run_id, after=after, limit=limit
        )
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return [EventRead.model_validate(event) for event in events]
