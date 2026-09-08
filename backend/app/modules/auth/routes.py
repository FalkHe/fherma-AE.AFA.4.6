import structlog
from fastapi import APIRouter, Request, Response

from app.core.db import DbSession
from app.core.errors import ApiError, ErrorCode
from app.core.schemas import ErrorEnvelope
from app.core.settings import get_settings
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import CsrfAuth
from app.modules.auth.schemas import RegisterRequest, SignInRequest
from app.modules.users import service as users_service
from app.modules.users.schemas import UserRead

logger = structlog.get_logger()

router = APIRouter()


def _set_session_cookie(response: Response, *, token: str, csrf_token: str, max_age: int) -> None:
    settings = get_settings()
    response.set_cookie(
        "session",
        token,
        max_age=max_age,
        httponly=True,
        path="/",
        samesite="lax",
        secure=settings.environment == "production",
    )
    response.headers["X-CSRF-Token"] = csrf_token


@router.post(
    "/register",
    status_code=201,
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def register(payload: RegisterRequest, response: Response, db: DbSession) -> UserRead:
    user = await users_service.create_user(db, username=payload.username, password=payload.password)
    issued = await auth_service.create_session(db, user=user)
    _set_session_cookie(
        response, token=issued.token, csrf_token=issued.csrf_token, max_age=issued.max_age
    )
    return UserRead.model_validate(user)


@router.post(
    "/sign-in",
    responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def sign_in(payload: SignInRequest, response: Response, db: DbSession) -> UserRead:
    user = await users_service.verify_credentials(
        db, username=payload.username, password=payload.password
    )
    if user is None:
        logger.info("sign_in_failed", username=payload.username)
        raise ApiError(ErrorCode.INVALID_CREDENTIALS)
    issued = await auth_service.create_session(db, user=user)
    _set_session_cookie(
        response, token=issued.token, csrf_token=issued.csrf_token, max_age=issued.max_age
    )
    return UserRead.model_validate(user)


@router.post(
    "/sign-out",
    status_code=204,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def sign_out(request: Request, response: Response, auth: CsrfAuth, db: DbSession) -> None:
    token = request.cookies["session"]
    await auth_service.delete_session(db, token=token)
    settings = get_settings()
    response.delete_cookie(
        "session",
        path="/",
        samesite="lax",
        secure=settings.environment == "production",
    )
