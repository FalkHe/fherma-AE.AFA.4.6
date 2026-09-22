"""The turn route over HTTP (sprint 03, WI2, I1): one call that runs a
turn for a run without the caller ever naming its kind or a dice number
-- `game.service.run_turn` alone decides that from the run's own state
(I2).

Thin by design: the route only maps `TurnRequest` to the service call and
its two error hierarchies -- `PlaythroughError` (membership, run status)
and `GameError` (the turn engine's own refusals) -- onto the one wire
envelope, same pattern as `character/routes.py`'s
`except (PlaythroughError, CreationConversationNotFoundError)`. No
commit, add or execute happens here.
"""

from typing import Any

from fastapi import APIRouter

from app.core.db import DbSession
from app.core.errors import ApiError
from app.core.schemas import ErrorEnvelope
from app.modules.auth.dependencies import CsrfAuth
from app.modules.game import service
from app.modules.game.errors import GameError
from app.modules.game.schemas import TurnRead, TurnRequest
from app.modules.playthrough.errors import PlaythroughError

router = APIRouter()


@router.post(
    "/runs/{run_id}/turn",
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
    },
)
async def run_turn(run_id: str, payload: TurnRequest, auth: CsrfAuth, db: DbSession) -> TurnRead:
    try:
        outcome = await service.run_turn(db, user_id=auth.user.id, run_id=run_id, text=payload.text)
    except (PlaythroughError, GameError) as exc:
        details: dict[str, Any] | None = getattr(exc, "details", None)
        raise ApiError(exc.code, details=details) from exc
    return TurnRead(turn_id=outcome.turn_id, kind=outcome.kind, awaiting=outcome.awaiting)
