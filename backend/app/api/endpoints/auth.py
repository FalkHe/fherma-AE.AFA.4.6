"""Registration, login, logout and the current-account endpoint.

These four routes are the whole authentication surface: there is no session
management UI and no email flow. The services raise plain exceptions; mapping
them onto status codes happens here, so the service layer stays HTTP-free.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    csrf_protect,
    current_user,
)
from app.api.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.core.config import Settings, get_settings
from app.db.models.user import User
from app.db.session import get_db_session
from app.services import session_service, user_service

router = APIRouter(tags=["auth"])

# Both cookies share these attributes. `SameSite=Lax` is a hard requirement,
# not a default: the Phase-2 `EventSource` connection can only authenticate
# with a cookie, and header auth is therefore never an option.
COOKIE_PATH = "/"
COOKIE_SAMESITE = "Lax"

# Mirrors the server-side lifetime, so the browser stops sending a cookie the
# database would reject anyway.
REMEMBER_ME_MAX_AGE = int(session_service.REMEMBER_ME_TTL.total_seconds())

# 32 random bytes, URL-safe encoded — same strength as the session token.
CSRF_TOKEN_BYTES = 32


def _to_response(user: User) -> UserResponse:
    """Project a user row onto the public response body."""
    return UserResponse(id=user.id, username=user.username, role=user.role.value)


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    *,
    session_token: str,
    csrf_token: str,
    remember_me: bool,
) -> None:
    """Set the session and CSRF cookies for a freshly created session.

    Without remember-me neither cookie gets a `Max-Age`: it lives for the
    browser session only. The server-side expiry stays authoritative either way.
    """
    max_age = REMEMBER_ME_MAX_AGE if remember_me else None
    secure = settings.environment == "production"

    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=max_age,
        path=COOKIE_PATH,
        secure=secure,
        # The SPA never needs to read it, and JavaScript must not be able to.
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        path=COOKIE_PATH,
        secure=secure,
        # Readable on purpose: the SPA copies it into the X-CSRF-Token header.
        httponly=False,
        samesite=COOKIE_SAMESITE,
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    """Expire both cookies, repeating the attributes they were set with.

    Path and SameSite must match the originals; a browser treats a differing
    pair as a different cookie and keeps the stale one.
    """
    secure = settings.environment == "production"

    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path=COOKIE_PATH,
        secure=secure,
        httponly=True,
        samesite=COOKIE_SAMESITE,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path=COOKIE_PATH,
        secure=secure,
        httponly=False,
        samesite=COOKIE_SAMESITE,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Create an account and return it, without signing the caller in.

    No session is created here on purpose: the SPA chains a login call, so there
    is exactly one place where cookies are issued.
    """
    try:
        user = await user_service.register(session, payload.username, payload.password)
    except user_service.UsernameTakenError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken.",
        ) from error

    return _to_response(user)


@router.post("/login", response_model=UserResponse, summary="Sign in")
async def login(
    payload: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    """Authenticate, create a session and set the session and CSRF cookies.

    The failure message names neither the username nor the password: which of
    the two was wrong is not the caller's business.
    """
    user = await user_service.authenticate(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    session_token, _row = await session_service.create_session(
        session, user.id, remember_me=payload.remember_me
    )
    _set_auth_cookies(
        response,
        settings,
        session_token=session_token,
        # Fresh per login: a token from a previous session is never reused.
        csrf_token=secrets.token_urlsafe(CSRF_TOKEN_BYTES),
        remember_me=payload.remember_me,
    )
    return _to_response(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(current_user), Depends(csrf_protect)],
    summary="Sign out",
)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Delete the session row and clear both cookies.

    Requires the session cookie and a matching `X-CSRF-Token` header: signing
    somebody out is a state change, so it is not exempt from CSRF protection.
    """
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token is not None:
        await session_service.revoke_by_token(session, raw_token)

    _clear_auth_cookies(response, settings)


@router.get("/me", response_model=UserResponse, summary="Read the current account")
async def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    """Return the signed-in account, with the role read fresh from the database."""
    return _to_response(user)
