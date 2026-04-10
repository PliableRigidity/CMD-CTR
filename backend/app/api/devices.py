from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.devices import DeviceStatus
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["devices"])


@router.get("/devices", response_model=list[DeviceStatus])
async def list_devices(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[DeviceStatus]:
    return platform_router.device_manager.list_devices()
