from pydantic import BaseModel, Field


class AudioState(BaseModel):
    available: bool
    volume_percent: int | None = Field(default=None, ge=0, le=100)
    muted: bool | None = None
    backend: str


class AudioSetRequest(BaseModel):
    volume_percent: int = Field(..., ge=0, le=100)


class MediaActionResponse(BaseModel):
    success: bool
    action: str
    message: str
