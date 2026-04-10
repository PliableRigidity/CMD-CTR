from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.assistant import AssistantRequest, AssistantResponse
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["assistant"])


@router.post("/chat", response_model=AssistantResponse)
async def chat(
    request: AssistantRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AssistantResponse:
    response = await platform_router.handle(request)
    await platform_router.event_service.emit(
        "Chat response",
        f"Handled query in {response.mode} mode.",
    )
    return response
