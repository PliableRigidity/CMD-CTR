from pydantic import BaseModel
from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.assistant import ModeSelection
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["mode"])


class ModeUpdateRequest(BaseModel):
    mode: str


@router.get("/mode", response_model=ModeSelection)
async def get_mode(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> ModeSelection:
    return platform_router.get_mode()


@router.post("/mode", response_model=ModeSelection)
async def set_mode(
    request: ModeUpdateRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> ModeSelection:
    return platform_router.set_mode(request.mode)
