from datetime import datetime

from app.core.schemas import CamelModel


class UserRead(CamelModel):
    id: str
    username: str
    created_at: datetime
