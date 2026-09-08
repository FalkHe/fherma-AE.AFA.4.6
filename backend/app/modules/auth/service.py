from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_token, hash_token
from app.core.settings import get_settings
from app.modules.auth.models import UserSession
from app.modules.users.models import User


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    max_age: int


async def create_session(db: AsyncSession, *, user: User) -> IssuedSession:
    settings = get_settings()
    token = generate_token()
    csrf_token = generate_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds)

    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token=csrf_token,
        expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return IssuedSession(token=token, csrf_token=csrf_token, max_age=settings.session_ttl_seconds)


async def resolve_session(db: AsyncSession, *, token: str) -> UserSession | None:
    stmt = select(UserSession).where(UserSession.token_hash == hash_token(token))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if session.expires_at < datetime.now(UTC):
        return None
    return session


async def delete_session(db: AsyncSession, *, token: str) -> None:
    stmt = select(UserSession).where(UserSession.token_hash == hash_token(token))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is not None:
        await db.delete(session)
    await db.commit()
