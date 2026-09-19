import asyncio
import json
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.schemas import ErrorEnvelope
from app.core.settings import get_settings
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


@router.get(
    "/campaign/{run_id}/stream",
    responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def stream_campaign_run(
    run_id: str, request: Request, auth: CurrentAuth, db: DbSession
) -> StreamingResponse:
    """Says only "there is something new" (← D10) -- no content, no
    address of its own beyond that, so the client always refetches the
    transcript through `list_events`. Membership is checked here, before
    the `StreamingResponse` is ever returned, so a foreign or unknown run
    answers the ordinary error envelope instead of a stream that opens and
    immediately dies (I3).

    Settings are read through `get_settings()` inside the handler, not at
    import time, so a test can pin them small (I3).
    """
    try:
        last_id = await service.latest_event_id(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc

    settings = get_settings()
    poll_interval = settings.sse_poll_interval_seconds
    max_lifetime = settings.sse_max_lifetime_seconds

    async def _events():
        seen_id = last_id
        started = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            if time.monotonic() - started >= max_lifetime:
                return

            await asyncio.sleep(poll_interval)

            try:
                current_id = await service.latest_event_id(db, user_id=auth.user.id, run_id=run_id)
            except PlaythroughError:
                return

            if current_id != seen_id:
                seen_id = current_id
                payload = json.dumps({"type": "updated", "id": current_id}, separators=(",", ":"))
                yield f"data: {payload}\n\n"
            else:
                yield ": keepalive\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )
