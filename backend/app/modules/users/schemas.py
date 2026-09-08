import uuid
from datetime import datetime

from app.core.schemas import CamelModel


class UserRead(CamelModel):
    id: uuid.UUID
    username: str
    created_at: datetime
