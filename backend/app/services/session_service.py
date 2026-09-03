"""Server-side sessions: opaque tokens, resolution and revocation.

The raw token is returned to the caller once, at creation, and never stored:
the database only ever holds its sha256 digest. Expiry is decided when the
session is created and is never extended — there is deliberately no sliding
expiration, so a stolen cookie cannot be kept alive indefinitely.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.session import Session
from app.db.models.user import User

SESSION_TTL = timedelta(hours=24)
REMEMBER_ME_TTL = timedelta(days=30)

# 32 random bytes, URL-safe encoded (~43 characters).
TOKEN_BYTES = 32


def hash_token(raw_token: str) -> str:
    """Return the digest under which `raw_token` is stored and looked up."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_session(
    session: AsyncSession, user_id: str, remember_me: bool = False
) -> tuple[str, Session]:
    """Create a session for `user_id` and return `(raw_token, row)`.

    The raw token is the only copy in existence once this returns; callers put
    it in the cookie and must not persist it anywhere else.
    """
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    ttl = REMEMBER_ME_TTL if remember_me else SESSION_TTL
    row = Session(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        remember_me=remember_me,
        expires_at=datetime.now(UTC) + ttl,
    )
    session.add(row)
    await session.commit()
    return raw_token, row


async def resolve_session(session: AsyncSession, raw_token: str) -> User | None:
    """Return the user behind `raw_token`, or `None` if it is not usable.

    An expired session is deleted on the way out: expiry is enforced lazily
    here instead of by a scheduled job. The user row is loaded fresh on every
    call, so a role change takes effect on sessions that already exist.
    """
    row = await _get_by_token_hash(session, hash_token(raw_token))
    if row is None:
        return None

    if row.expires_at <= datetime.now(UTC):
        await session.delete(row)
        await session.commit()
        return None

    result = await session.execute(select(User).where(User.id == row.user_id))
    return result.scalar_one_or_none()


async def revoke_by_token(session: AsyncSession, raw_token: str) -> None:
    """Delete the session identified by `raw_token`, if it still exists."""
    await session.execute(delete(Session).where(Session.token_hash == hash_token(raw_token)))
    await session.commit()


async def revoke_all_for_user(session: AsyncSession, user_id: str) -> None:
    """Delete every session of `user_id`, logging the account out everywhere."""
    await delete_all_for_user(session, user_id)
    await session.commit()


async def delete_all_for_user(session: AsyncSession, user_id: str) -> None:
    """Issue the revoke-everything DELETE **without committing**.

    For callers that revoke as part of a wider change (see `user_service`) and
    therefore own the transaction; use `revoke_all_for_user` otherwise.
    """
    await session.execute(delete(Session).where(Session.user_id == user_id))


async def _get_by_token_hash(session: AsyncSession, token_hash: str) -> Session | None:
    result = await session.execute(select(Session).where(Session.token_hash == token_hash))
    return result.scalar_one_or_none()
