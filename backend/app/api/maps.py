from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.models.maps import RouteRequest, RouteResponse
from backend.app.orchestration.assistant_router import AssistantPlatformRouter


router = APIRouter(tags=["maps"])


@router.post("/maps/route", response_model=RouteResponse)
async def get_route(
    request: RouteRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> RouteResponse:
    route = await platform_router.maps_service.get_route(request)
    await platform_router.event_service.emit(
        "Navigation request",
        f"Route computed from {route.origin} to {route.destination}.",
    )
    return route
