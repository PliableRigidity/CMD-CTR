"""Conversation mode request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ConversationRequest(BaseModel):
    """Request for conversation mode."""
    query: str = Field(..., min_length=1, max_length=10000)
    history: Optional[List[dict]] = Field(default_factory=list)
    personality: str = Field(default="helpful", pattern="^(helpful|creative|analytical|friendly)$")
    context: Optional[dict] = None


class ConversationResponse(BaseModel):
    """Response from conversation mode."""
    answer: str
    confidence: Optional[float] = None
    follow_up_suggestions: Optional[List[str]] = None
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
