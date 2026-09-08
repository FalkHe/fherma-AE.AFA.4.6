from fastapi import APIRouter

from app.core.schemas import CamelModel

router = APIRouter()


class HealthRead(CamelModel):
    status: str


@router.get("")
async def read_health() -> HealthRead:
    return HealthRead(status="ok")
