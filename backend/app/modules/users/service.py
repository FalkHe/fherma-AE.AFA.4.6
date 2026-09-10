from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.core.security import hash_password, verify_password
from app.modules.users.models import User

# Argon2 hash of a fixed dummy value. verify_credentials runs a verification
# against it on the unknown-username path, so both branches take comparable
# time (§5.4) and no enumeration signal leaks through response timing.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-parity")


def normalize_username(raw: str) -> str:
    return raw.strip().lower()


async def create_user(db: AsyncSession, *, username: str, password: str) -> User:
    normalized = normalize_username(username)
    existing = await get_user_by_username(db, username=normalized)
    if existing is not None:
        raise ApiError(ErrorCode.USERNAME_TAKEN)

    user = User(username=normalized, password_hash=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_username(db: AsyncSession, *, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == normalize_username(username)))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, *, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def verify_credentials(db: AsyncSession, *, username: str, password: str) -> User | None:
    user = await get_user_by_username(db, username=username)
    if user is None:
        verify_password(_DUMMY_PASSWORD_HASH, password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user
