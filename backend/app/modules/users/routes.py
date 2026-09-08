from fastapi import APIRouter, Response

from app.core.schemas import ErrorEnvelope
from app.modules.auth.dependencies import CurrentAuth
from app.modules.users.schemas import UserRead

router = APIRouter()


@router.get("/me", responses={401: {"model": ErrorEnvelope}})
async def read_current_user(response: Response, auth: CurrentAuth) -> UserRead:
    response.headers["X-CSRF-Token"] = auth.session.csrf_token
    return UserRead.model_validate(auth.user)
