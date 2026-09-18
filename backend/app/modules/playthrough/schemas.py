from datetime import datetime

from pydantic import Field

from app.core.schemas import CamelModel


class StartCampaignRunRequest(CamelModel):
    campaign_id: str = Field(min_length=1, max_length=64)


class CampaignRunRead(CamelModel):
    """The run row, not its state -- `id, campaignId, contentVersion,
    title, status, createdAt` and nothing else (I2)."""

    id: str
    campaign_id: str
    content_version: str
    title: str | None
    status: str
    created_at: datetime
