import asyncio
import json
import time

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.core.db import DbSession
from app.core.errors import ApiError, ErrorCode
from app.core.schemas import ErrorEnvelope
from app.core.settings import get_settings
from app.modules.auth.dependencies import CsrfAuth, CurrentAuth
from app.modules.character import service as character_service
from app.modules.character.errors import CharacterBuildError
from app.modules.character.schemas import CharacterCreateRequest
from app.modules.playthrough import service
from app.modules.playthrough.errors import PlaythroughError
from app.modules.playthrough.schemas import (
    AdventureRunRead,
    CampaignRunOverviewRead,
    CampaignRunRead,
    CampaignRunSummaryRead,
    CharacterRead,
    EventRead,
    EventsRead,
    RenameCampaignRunRequest,
    StartCampaignRunRequest,
    TableRead,
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


@router.get("/runs", responses={401: {"model": ErrorEnvelope}})
async def list_run_summaries(auth: CurrentAuth, db: DbSession) -> list[CampaignRunSummaryRead]:
    try:
        return await service.list_run_summaries(db, user_id=auth.user.id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc


@router.get(
    "/runs/{run_id}/overview",
    responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def get_run_overview(
    run_id: str, auth: CurrentAuth, db: DbSession
) -> CampaignRunOverviewRead:
    try:
        return await service.get_run_overview(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc


@router.get(
    "/runs/{run_id}/table",
    responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def get_table(run_id: str, auth: CurrentAuth, db: DbSession) -> TableRead:
    try:
        return await service.get_table(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc


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
        422: {"model": ErrorEnvelope},
    },
)
async def create_character(
    run_id: str, auth: CsrfAuth, db: DbSession, payload: CharacterCreateRequest | None = None
) -> CharacterRead:
    """`payload` omitted -- the campaign's seed hero (today's behaviour);
    given -- built through `character_service.build_sheet` first (sprint
    009-02, WI2, AC6). An illegal spread or an unknown equipment pick
    (`CharacterBuildError`) reaches the wire as `VALIDATION_ERROR` with
    every message `build_sheet` found, not just the first."""
    sheet = None
    if payload is not None:
        try:
            sheet = character_service.build_sheet(payload)
        except CharacterBuildError as exc:
            raise ApiError(ErrorCode.VALIDATION_ERROR, details={"messages": exc.messages}) from exc
    try:
        character = await service.create_character(
            db, user_id=auth.user.id, run_id=run_id, sheet=sheet
        )
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return service.character_read(character)


@router.post(
    "/campaign/{run_id}/adventure",
    status_code=201,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
    },
)
async def enter_adventure(run_id: str, auth: CsrfAuth, db: DbSession) -> AdventureRunRead:
    try:
        adventure_run = await service.enter_adventure(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return AdventureRunRead.model_validate(adventure_run)


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
) -> EventsRead:
    try:
        events = await service.list_events(
            db, user_id=auth.user.id, run_id=run_id, after=after, limit=limit
        )
        awaiting = await service.get_awaiting(db, user_id=auth.user.id, run_id=run_id)
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc
    return EventsRead(
        events=[EventRead.model_validate(event) for event in events], awaiting=awaiting
    )


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
