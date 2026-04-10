from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

SearchCategory = Literal["general", "news", "docs", "maps", "sports", "tech", "science", "economy", "politics", "conflict", "environment"]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    category: SearchCategory = "general"
    limit: int = Field(default=5, ge=1, le=10)


class SearchResult(BaseModel):
    rank: int
    title: str
    url: str
    source: str
    snippet: str = ""
    published_at: str | None = None
    category: SearchCategory = "general"
    score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    category: SearchCategory
    results: list[SearchResult]


class ArticleRequest(BaseModel):
    url: str
    summarize: bool = True


class ArticleDocument(BaseModel):
    title: str
    url: str
    source: str
    published_at: str | None = None
    author: str | None = None
    summary: str = ""
    content: str = ""
    excerpt: str = ""
    language: str | None = None
    image_url: str | None = None


class EventFeedRequest(BaseModel):
    query: str = "latest world news"
    limit: int = Field(default=6, ge=1, le=12)
    category: SearchCategory = "news"


class NormalizedEvent(BaseModel):
    id: str
    title: str
    url: str
    source: str
    summary: str
    country: str
    primary_country: str | None = None
    secondary_countries: list[str] = Field(default_factory=list)
    region_scope: Literal["country", "regional", "global", "non-geographic"] = "global"
    is_global: bool = False
    region: str
    entities: list[str]
    category: str
    severity: str
    published_at: str | None = None
    highlight_color: str = "#63d2ff"
    latitude: float | None = None
    longitude: float | None = None


class EventFeedResponse(BaseModel):
    query: str
    events: list[NormalizedEvent]


class BrowserAction(BaseModel):
    action: Literal["open", "click", "type", "extract"]
    target: str
    value: str | None = None


class BrowserSessionSnapshot(BaseModel):
    status: str
    current_url: str | None = None
    extracted_text: str | None = None
