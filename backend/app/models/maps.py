from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    origin: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)
    travel_mode: str = "drive"
    use_current_location: bool = False


class RouteResponse(BaseModel):
    origin: str
    destination: str
    travel_mode: str
    distance: str
    eta: str
    provider: str
    notes: list[str]
    origin_lat: float | None = None
    origin_lon: float | None = None
    destination_lat: float | None = None
    destination_lon: float | None = None
    geometry: list[list[float]] = Field(default_factory=list)
