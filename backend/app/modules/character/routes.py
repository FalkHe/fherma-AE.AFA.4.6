"""The character creation chat over HTTP (sprint 009-05, WI1): one write
that starts a conversation for a run, one that sends a single player
message. Both answer `CreationReply` -- the Keeper's words plus the sheet
so far, the step reached and whether it can be saved (← AC3), so the page
never needs a second read.

Thin by design: everything that touches `app.state` or the database goes
through one `character_service` function per route
(`start_creation`/`send_creation_message`), which alone knows the
conversation-record shape and the agent lifecycle (← research Decision 1).
No commit, add or execute happens here."""

from fastapi import APIRouter, Request

from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.schemas import ErrorEnvelope
from app.modules.auth.dependencies import CsrfAuth
from app.modules.character import service as character_service
from app.modules.character.errors import CreationConversationNotFoundError
from app.modules.character.schemas import CreationReply, SendCreationMessageRequest
from app.modules.playthrough.errors import PlaythroughError

router = APIRouter()


@router.post(
    "/runs/{run_id}/creation",
    status_code=201,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
    },
)
async def start_creation(
    run_id: str, request: Request, auth: CsrfAuth, db: DbSession
) -> CreationReply:
    try:
        return await character_service.start_creation(
            db, request.app.state, user_id=auth.user.id, run_id=run_id
        )
    except PlaythroughError as exc:
        raise ApiError(exc.code) from exc


@router.post(
    "/creation/{conversation_id}/messages",
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def send_creation_message(
    conversation_id: str,
    payload: SendCreationMessageRequest,
    request: Request,
    auth: CsrfAuth,
    db: DbSession,
) -> CreationReply:
    try:
        return await character_service.send_creation_message(
            db,
            request.app.state,
            conversation_id=conversation_id,
            user_id=auth.user.id,
            text=payload.text,
        )
    except (PlaythroughError, CreationConversationNotFoundError) as exc:
        raise ApiError(exc.code) from exc
