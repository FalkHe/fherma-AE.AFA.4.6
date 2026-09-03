"""The `users` table: one account per row."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, ULIDPrimaryKeyMixin

USERNAME_LENGTH = 32
# Argon2 hashes are far shorter, but the column must survive a parameter or
# algorithm change without a migration.
PASSWORD_HASH_LENGTH = 255


class UserRole(StrEnum):
    """Authorisation level of an account."""

    USER = "user"
    ADMIN = "admin"


class User(ULIDPrimaryKeyMixin, Base):
    """A registered account.

    `username` is stored in its normalised (stripped, lowercased) form only, so
    case-insensitive uniqueness is just the unique index on this column.
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(USERNAME_LENGTH), unique=True)
    password_hash: Mapped[str] = mapped_column(String(PASSWORD_HASH_LENGTH))
    role: Mapped[UserRole] = mapped_column(
        # Native PostgreSQL enum. `values_callable` makes the type carry the
        # member *values* ('user', 'admin'); the default would use the member
        # names ('USER', 'ADMIN').
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        server_default=UserRole.USER.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
