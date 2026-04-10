from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.app.api.deps import get_router
from backend.app.models.assistant import CommandLogEntry
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["events"])


@router.get("/events/logs", response_model=list[CommandLogEntry])
async def get_logs(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[CommandLogEntry]:
    return platform_router.event_service.history()


@router.websocket("/ws/events")
async def event_stream(websocket: WebSocket) -> None:
    platform_router: AssistantPlatformRouter = websocket.app.state.router
    await platform_router.event_service.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        platform_router.event_service.disconnect(websocket)
