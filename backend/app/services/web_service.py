from __future__ import annotations

import httpx

from backend.app.models.assistant import SourceReference
from backend.app.web.browse.controller import BrowserAutomationProvider, NullBrowserAutomationProvider
from backend.app.web.fetch.extractor import ArticleExtractor
from backend.app.web.news.extractor import EventExtractor
from backend.app.web.schemas.models import (
    ArticleDocument,
    ArticleRequest,
    BrowserAction,
    BrowserSessionSnapshot,
    EventFeedRequest,
    EventFeedResponse,
    SearchRequest,
    SearchResponse,
)
from backend.app.web.search.providers import (
    BingRssSearchProvider,
    GoogleNewsRssSearchProvider,
    SearchProvider,
)


class WebIntelligenceService:
    def __init__(
        self,
        search_provider: SearchProvider | None = None,
        browser_provider: BrowserAutomationProvider | None = None,
    ) -> None:
        self.default_search_provider = search_provider or BingRssSearchProvider()
        self.news_search_provider = GoogleNewsRssSearchProvider()
        self.article_extractor = ArticleExtractor()
        self.event_extractor = EventExtractor()
        self.browser_provider = browser_provider or NullBrowserAutomationProvider()
        self._geo_cache: dict[str, tuple[float | None, float | None]] = {}

    async def search(self, request: SearchRequest) -> SearchResponse:
        provider = self.news_search_provider if request.category == "news" else self.default_search_provider
        results = await provider.search(request)
        return SearchResponse(query=request.query, category=request.category, results=results)

    async def fetch_article(self, request: ArticleRequest) -> ArticleDocument:
        return await self.article_extractor.fetch_article(request.url, summarize=request.summarize)

    async def get_event_feed(self, request: EventFeedRequest) -> EventFeedResponse:
        search_response = await self.search(
            SearchRequest(
                query=self._event_query_for_category(request.query, request.category),
                category="news",
                limit=request.limit,
            )
        )
        events = []
        for result in search_response.results:
            article = None
            if result.source.lower() not in {"news.google.com", "google news"} and "news.google.com" not in result.url:
                try:
                    article = await self.fetch_article(ArticleRequest(url=result.url, summarize=True))
                except Exception:
                    article = None
            event = self.event_extractor.extract_event(result, article)
            event.latitude, event.longitude = await self._resolve_country_coordinates(event.primary_country, event.is_global)
            events.append(event)
        return EventFeedResponse(query=request.query, events=events)

    async def browse(self, action: BrowserAction) -> BrowserSessionSnapshot:
        return await self.browser_provider.perform(action)

    def to_sources(self, search_response: SearchResponse) -> list[SourceReference]:
        return [
            SourceReference(
                title=result.title,
                url=result.url,
                source=result.source,
                snippet=result.snippet,
                published_at=result.published_at,
                category=result.category,
            )
            for result in search_response.results
        ]

    async def _resolve_country_coordinates(self, country: str | None, is_global: bool) -> tuple[float | None, float | None]:
        if is_global or not country or country in {"Global", ""}:
            return (None, None)
        if country in self._geo_cache:
            return self._geo_cache[country]

        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": "AssistantCommandCenter/1.0 (world event geocoder)"},
            follow_redirects=True,
        ) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": country, "format": "jsonv2", "limit": 1},
            )
            response.raise_for_status()
        results = response.json()
        if not results:
            self._geo_cache[country] = (None, None)
            return self._geo_cache[country]
        coords = (float(results[0]["lat"]), float(results[0]["lon"]))
        self._geo_cache[country] = coords
        return coords

    def _event_query_for_category(self, query: str, category: str) -> str:
        query_map = {
            "general": "latest world news",
            "news": "latest world news",
            "politics": "latest politics world news",
            "conflict": "latest conflict and security news",
            "economy": "latest economy and markets news",
            "tech": "latest technology and AI news",
            "science": "latest science and space news",
            "environment": "latest climate environment and disaster news",
            "sports": "latest sports news Formula 1 F1 football tennis",
        }
        return query_map.get(category, query or "latest world news")
