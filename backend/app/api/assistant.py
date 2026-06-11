from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

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


@router.post("/chat/stream")
async def chat_stream(
    request: AssistantRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> StreamingResponse:
    async def generate():
        async for chunk in platform_router.conversation_service.handle_stream(request):
            yield f"data: {chunk}\n\n"
        await platform_router.event_service.emit("Chat response", "Handled streaming conversation.")

    return StreamingResponse(generate(), media_type="text/event-stream")
