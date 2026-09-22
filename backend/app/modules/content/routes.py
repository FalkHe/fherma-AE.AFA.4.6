from fastapi import APIRouter

from app.core.schemas import ErrorEnvelope
from app.modules.auth.dependencies import CurrentAuth
from app.modules.content import service
from app.modules.content.schemas import CampaignSummaryRead

router = APIRouter()


@router.get("/campaigns", responses={401: {"model": ErrorEnvelope}})
async def list_campaigns(auth: CurrentAuth) -> list[CampaignSummaryRead]:
    return [
        CampaignSummaryRead(
            id=loaded.campaign.id,
            title=loaded.campaign.title,
            summary=loaded.campaign.summary,
            adventure_count=len(loaded.adventures),
        )
        for loaded in service.list_catalogue()
    ]
