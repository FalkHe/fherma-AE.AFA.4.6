from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.db import DbSession
from app.core.errors import ApiError, ErrorCode
from app.core.security import tokens_equal
from app.modules.auth import service as auth_service
from app.modules.auth.models import UserSession
from app.modules.users import service as users_service
from app.modules.users.models import User


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession


async def require_auth(request: Request, db: DbSession) -> AuthContext:
    token = request.cookies.get("session")
    if token is None:
        raise ApiError(ErrorCode.NOT_AUTHENTICATED)

    session = await auth_service.resolve_session(db, token=token)
    if session is None:
        raise ApiError(ErrorCode.SESSION_EXPIRED)

    user = await users_service.get_user_by_id(db, user_id=session.user_id)
    if user is None:
        raise ApiError(ErrorCode.SESSION_EXPIRED)

    return AuthContext(user=user, session=session)


CurrentAuth = Annotated[AuthContext, Depends(require_auth)]


async def require_csrf(request: Request, auth: CurrentAuth) -> AuthContext:
    header = request.headers.get("X-CSRF-Token")
    if not header or not tokens_equal(header, auth.session.csrf_token):
        raise ApiError(ErrorCode.CSRF_TOKEN_INVALID)
    return auth


CsrfAuth = Annotated[AuthContext, Depends(require_csrf)]
