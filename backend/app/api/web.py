from fastapi import APIRouter, Depends

from backend.app.api.deps import get_router
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.web.schemas.models import (
    ArticleDocument,
    ArticleRequest,
    EventFeedRequest,
    EventFeedResponse,
    SearchRequest,
    SearchResponse,
)


router = APIRouter(prefix="/web", tags=["web"])


@router.post("/search", response_model=SearchResponse)
async def search_web(
    request: SearchRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> SearchResponse:
    return await platform_router.web_service.search(request)


@router.post("/article", response_model=ArticleDocument)
async def fetch_article(
    request: ArticleRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> ArticleDocument:
    return await platform_router.web_service.fetch_article(request)


@router.post("/events", response_model=EventFeedResponse)
async def get_event_feed(
    request: EventFeedRequest,
    platform_router: AssistantPlatformRouter = Depends(get_router),
) -> EventFeedResponse:
    return await platform_router.web_service.get_event_feed(request)
