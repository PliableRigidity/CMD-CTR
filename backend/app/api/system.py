from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.system import AudioSetRequest, AudioState, MediaActionResponse
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/audio", response_model=AudioState)
async def get_audio_state(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AudioState:
    return platform_router.system_control_service.get_audio_state()


@router.post("/audio/set", response_model=AudioState)
async def set_audio_state(
    request: AudioSetRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AudioState:
    state = platform_router.system_control_service.set_volume(request.volume_percent)
    await platform_router.event_service.emit("Volume set", f"System volume set to {state.volume_percent}%.")
    return state


@router.post("/audio/up", response_model=AudioState)
async def volume_up(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AudioState:
    state = platform_router.system_control_service.volume_up()
    await platform_router.event_service.emit("Volume up", f"Volume raised to {state.volume_percent}%.")
    return state


@router.post("/audio/down", response_model=AudioState)
async def volume_down(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AudioState:
    state = platform_router.system_control_service.volume_down()
    await platform_router.event_service.emit("Volume down", f"Volume lowered to {state.volume_percent}%.")
    return state


@router.post("/audio/mute", response_model=AudioState)
async def mute_toggle(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> AudioState:
    state = platform_router.system_control_service.toggle_mute()
    await platform_router.event_service.emit("Mute toggled", f"Muted state is now {state.muted}.")
    return state


@router.post("/media/play-pause", response_model=MediaActionResponse)
async def media_play_pause(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> MediaActionResponse:
    result = platform_router.system_control_service.media_play_pause()
    await platform_router.event_service.emit("Media control", result.message)
    return result


@router.post("/media/next", response_model=MediaActionResponse)
async def media_next(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> MediaActionResponse:
    result = platform_router.system_control_service.media_next()
    await platform_router.event_service.emit("Media control", result.message)
    return result


@router.post("/media/previous", response_model=MediaActionResponse)
async def media_previous(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> MediaActionResponse:
    result = platform_router.system_control_service.media_previous()
    await platform_router.event_service.emit("Media control", result.message)
    return result
