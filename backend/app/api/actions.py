from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.actions import ActionExecutionRequest, ActionExecutionResponse, ActionDescriptor
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("", response_model=list[ActionDescriptor])
async def list_actions(
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[ActionDescriptor]:
    return platform_router.action_service.list_actions()


@router.post("/open-app", response_model=ActionExecutionResponse)
async def open_app(
    request: ActionExecutionRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> ActionExecutionResponse:
    result = platform_router.action_service.open_registered_app(request.action_id or "", request.args)
    await platform_router.event_service.emit(
        "App action",
        result.message,
        level="info" if result.success else "error",
    )
    return result


@router.post("/open-url", response_model=ActionExecutionResponse)
async def open_url(
    request: ActionExecutionRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> ActionExecutionResponse:
    result = platform_router.action_service.open_url(request.target or "")
    await platform_router.event_service.emit(
        "URL action",
        result.message,
        level="info" if result.success else "error",
    )
    return result


@router.post("/execute", response_model=ActionExecutionResponse)
async def execute_action_alias(
    request: ActionExecutionRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> ActionExecutionResponse:
    result = platform_router.action_service.execute_alias(request.target or request.action_id or "")
    await platform_router.event_service.emit(
        "Alias action",
        result.message,
        level="info" if result.success else "error",
    )
    return result
