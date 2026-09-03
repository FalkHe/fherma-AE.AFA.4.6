"""Shared FastAPI dependencies: authentication, authorisation and CSRF.

The cookie and the CSRF header are read from the `Request` instead of being
declared as `Cookie`/`Header` parameters: they are transport plumbing the
browser fills in automatically, and declaring them would push them into the
OpenAPI schema and therefore into the generated frontend client's call sites.
"""

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User, UserRole
from app.db.session import get_db_session
from app.services import session_service

SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Return the account behind the `session` cookie, or fail with 401.

    This is the **default guard for all future `/api/*` routers**; only
    `/health` and `/ready` stay outside it, because the Compose health checks
    call them without cookies.

    The user row is loaded fresh on every request (in `resolve_session`), so a
    role change takes effect on sessions that already exist.
    """
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    user = None if raw_token is None else await session_service.resolve_session(session, raw_token)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return user


async def current_admin(user: Annotated[User, Depends(current_user)]) -> User:
    """Return the account only if it is an admin, otherwise fail with 403.

    401 means "not signed in", 403 means "signed in, insufficient role" — the
    SPA guards are UX only, this dependency is the real boundary.
    """
    if user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


async def csrf_protect(request: Request) -> None:
    """Reject a cookie-authenticated write whose CSRF token does not match.

    Double-submit pattern: the `csrf_token` cookie is readable by the SPA, which
    copies it into the `X-CSRF-Token` header. A cross-site attacker can send the
    cookie but cannot read it, so it cannot produce the header.

    Required on `logout` and every future authenticated write; `login` and
    `register` are exempt because no session exists yet.
    """
    header_token = request.headers.get(CSRF_HEADER_NAME)
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)

    if (
        header_token is None
        or cookie_token is None
        or not secrets.compare_digest(header_token, cookie_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid.",
        )
