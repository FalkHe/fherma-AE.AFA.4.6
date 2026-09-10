from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import ID_TYPE, generate_id

# Named `UserSession`, never `Session` -- that name is taken by SQLAlchemy's
# own `Session` and by the request-scoped `AsyncSession`.


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
    user_id: Mapped[str] = mapped_column(
        ID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
