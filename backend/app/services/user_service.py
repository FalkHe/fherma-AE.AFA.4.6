"""User accounts: registration, authentication and administrative changes.

This module owns its transactions and speaks no HTTP: callers (routes in step
1.3, the CLI in step 1.5) translate the exceptions raised here into status
codes or exit codes.

Only normalised usernames exist in the database, so every entry point folds its
input the same way before touching a row.
"""

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User, UserRole
from app.services import session_service

password_hash = PasswordHash((Argon2Hasher(),))

# Verified when the username is unknown, so a failed login costs the same
# whether or not the account exists. Computed once: hashing is deliberately
# slow, and this value is not a secret.
_DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


class UsernameTakenError(Exception):
    """Raised when a registration collides with an existing username."""


class UserNotFoundError(Exception):
    """Raised when an operation names a username that does not exist."""


def normalize_username(username: str) -> str:
    """Return the single form of `username` that is ever stored or queried."""
    return username.strip().lower()


async def register(session: AsyncSession, username: str, password: str) -> User:
    """Create an account with the default role and return it.

    Raises:
        UsernameTakenError: the normalised username is already in use.
    """
    normalized = normalize_username(username)
    if await _get_by_username(session, normalized) is not None:
        raise UsernameTakenError(normalized)

    user = User(
        username=normalized,
        password_hash=password_hash.hash(password),
        role=UserRole.USER,
    )
    session.add(user)
    await session.commit()
    return user


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    """Return the user for valid credentials, `None` otherwise.

    An unknown username still pays for one hash verification (against
    `_DUMMY_HASH`), so response time does not reveal which accounts exist.
    """
    user = await _get_by_username(session, normalize_username(username))
    if user is None:
        password_hash.verify(password, _DUMMY_HASH)
        return None

    if not password_hash.verify(password, user.password_hash):
        return None
    return user


async def set_role(session: AsyncSession, username: str, role: UserRole) -> User:
    """Set the account's role and return it; a no-op change is a success.

    Demotion from admin to user revokes every session of that account, so a
    stale cookie cannot keep exercising admin routes. Promotion does not: the
    live sessions read the role fresh anyway.

    Raises:
        UserNotFoundError: no account with that username.
    """
    normalized = normalize_username(username)
    user = await _get_by_username(session, normalized)
    if user is None:
        raise UserNotFoundError(normalized)

    if user.role is role:
        return user

    is_demotion = user.role is UserRole.ADMIN and role is UserRole.USER
    user.role = role
    if is_demotion:
        # Same transaction as the role change: the account is never left
        # demoted with its admin sessions still alive.
        await session_service.delete_all_for_user(session, user.id)
    await session.commit()
    return user


async def reset_password(session: AsyncSession, username: str, new_password: str) -> User:
    """Replace the password hash and revoke every session of that account.

    Raises:
        UserNotFoundError: no account with that username.
    """
    normalized = normalize_username(username)
    user = await _get_by_username(session, normalized)
    if user is None:
        raise UserNotFoundError(normalized)

    user.password_hash = password_hash.hash(new_password)
    await session_service.delete_all_for_user(session, user.id)
    await session.commit()
    return user


async def _get_by_username(session: AsyncSession, normalized_username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == normalized_username))
    return result.scalar_one_or_none()
