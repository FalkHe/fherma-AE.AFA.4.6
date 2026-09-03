"""The `sessions` table: one row per active login."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

# A sha256 digest in hexadecimal form is always 64 characters.
TOKEN_HASH_LENGTH = 64


class Session(ULIDPrimaryKeyMixin, Base):
    """A server-side session backing one `session` cookie.

    Only the sha256 hash of the opaque token is stored: the raw token exists in
    the cookie alone, so a leaked database dump cannot be replayed. Expiry is
    fixed at creation time and never extended.
    """

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting an account must take its sessions with it.
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    remember_me: Mapped[bool] = mapped_column(Boolean, server_default=false())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
