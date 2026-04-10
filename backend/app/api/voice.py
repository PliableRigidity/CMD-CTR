from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.voice import VoiceStateUpdate, VoiceStatus
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["voice"])


@router.get("/voice/status", response_model=VoiceStatus)
async def voice_status(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> VoiceStatus:
    return platform_router.voice_service.status()


@router.post("/voice/state", response_model=VoiceStatus)
async def update_voice_state(
    request: VoiceStateUpdate,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> VoiceStatus:
    status = platform_router.voice_service.update(request)
    await platform_router.event_service.emit(
        "Voice state",
        f"Listening={status.listening}, speaking={status.speaking}, speech_enabled={status.speech_enabled}.",
    )
    return status
