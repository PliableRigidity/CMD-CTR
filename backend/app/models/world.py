from pydantic import BaseModel, Field


class WorldEvent(BaseModel):
    id: str
    title: str
    country: str
    primary_country: str | None = None
    secondary_countries: list[str] = Field(default_factory=list)
    region_scope: str = "global"
    is_global: bool = False
    region: str
    severity: str
    summary: str
    tags: list[str]
    updated_at: str
    source_name: str | None = None
    source_url: str | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    importance_score: float | None = None
    confidence_score: float | None = None
    freshness_score: float | None = None
    final_rank: float | None = None
    board_priority: str | None = None
    badge: str | None = None
