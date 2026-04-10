from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.assistant import AssistantRequest, AssistantResponse
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["decision"])


@router.post("/decision", response_model=AssistantResponse)
async def decision(
    request: AssistantRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AssistantResponse:
    request.mode = "decision"
    response = await platform_router.handle(request)
    await platform_router.event_service.emit(
        "Decision response",
        "Completed decision mode request.",
        level="info" if "error" not in response.payload else "error",
    )
    return response
