from datetime import datetime

from pydantic import BaseModel, Field

from app.core.schemas import CamelModel
from app.modules.content.schemas import Abilities


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


class CharacterState(BaseModel):
    """The character's `state` column (I5), written whole from the seed
    sheet and never mutated in place -- a plain `BaseModel`, not a
    `CamelModel`: this is storage, not wire shape. Carried items keep the
    column's `{}` default; only the character has no `template_id` to
    carry this data instead."""

    abilities: Abilities
    race: str
    character_class: str
    background: str
    appearance: str
