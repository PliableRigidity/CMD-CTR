from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_router
from backend.app.models.missions import Mission, MissionRelevance
from backend.app.orchestration.assistant_router import AssistantPlatformRouter

router = APIRouter(tags=["missions"])


@router.get("/missions", response_model=list[Mission])
async def list_missions(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[Mission]:
    return platform_router.mission_service.list_missions()


@router.get("/missions/score", response_model=list[MissionRelevance])
async def score_event(
    text: str = Query(..., description="Event text to score against active missions"),
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[MissionRelevance]:
    return platform_router.mission_service.score_event(text)
