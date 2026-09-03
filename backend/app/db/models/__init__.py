"""SQLAlchemy models.

Importing this package must register every model on `Base.metadata`; Alembic's
`env.py` relies on that for autogenerate.
"""

from app.db.models.base import Base, ULIDPrimaryKeyMixin, new_ulid
from app.db.models.chat import (
    Chat,
    ChatMessage,
    ChatMessageRole,
    ChatPreference,
    PreferenceFirmness,
)
from app.db.models.chunk import Chunk
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.motorbike_spec import MotorbikeSpec, SpecKind
from app.db.models.motorbike_used_price import MotorbikeUsedPrice
from app.db.models.operation import Operation, OperationStatus
from app.db.models.session import Session
from app.db.models.source_document import SourceDocument, SourceType
from app.db.models.user import User, UserRole

__all__ = [
    "Base",
    "Chat",
    "ChatMessage",
    "ChatMessageRole",
    "ChatPreference",
    "Chunk",
    "ImageStatus",
    "Manufacturer",
    "Motorbike",
    "MotorbikeImage",
    "MotorbikeSpec",
    "MotorbikeStatus",
    "MotorbikeUsedPrice",
    "Operation",
    "OperationStatus",
    "PreferenceFirmness",
    "Session",
    "SourceDocument",
    "SourceType",
    "SpecKind",
    "ULIDPrimaryKeyMixin",
    "User",
    "UserRole",
    "new_ulid",
]
