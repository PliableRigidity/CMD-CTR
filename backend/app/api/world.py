from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_router
from backend.app.models.world import WorldEvent
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.world.rss_ingestor import rss_ingestor


router = APIRouter(tags=["world"])


@router.get("/world/events", response_model=list[WorldEvent])
async def list_world_events(
    live: bool = Query(default=False),
    category: str | None = Query(default=None),
    country: str | None = Query(default=None),
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> list[WorldEvent]:
    if live:
        events = await rss_ingestor.ingest()
    else:
        events = platform_router.world_events_service.list_events()
        
    if category and category != "all" and category != "":
        events = [event for event in events if event.category == category]
    
    if country and country != "All regions" and country != "":
        if country == "Global":
            events = [event for event in events if event.is_global]
        else:
            events = [event for event in events if event.primary_country == country or event.country == country]
            
    return events
