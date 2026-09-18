from fastapi import APIRouter

from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.schemas import ErrorEnvelope
from app.modules.auth.dependencies import CsrfAuth, CurrentAuth
from app.modules.playthrough import service
from app.modules.playthrough.errors import PlaythroughError
from app.modules.playthrough.schemas import CampaignRunRead, StartCampaignRunRequest

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
