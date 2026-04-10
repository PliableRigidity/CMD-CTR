from typing import Any, Literal

from pydantic import BaseModel, Field


AssistantMode = Literal["auto", "conversation", "decision"]


class AssistantRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    mode: AssistantMode = "auto"
    goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    session_id: str = "default-session"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStatus(BaseModel):
    name: str
    role: str
    state: str
    confidence: int | None = None
    summary: str | None = None


class CommandLogEntry(BaseModel):
    timestamp: str
    title: str
    detail: str
    level: str = "info"


class SourceReference(BaseModel):
    title: str
    url: str
    source: str
    snippet: str | None = None
    published_at: str | None = None
    category: str | None = None


class AssistantResponse(BaseModel):
    mode: Literal["conversation", "decision"]
    answer: str
    reasoning: str | None = None
    confidence: float | None = None
    processing_time_ms: float
    title: str = "Assistant Response"
    sources: list[SourceReference] = Field(default_factory=list)
    agents: list[AgentStatus] = Field(default_factory=list)
    logs: list[CommandLogEntry] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class ModeSelection(BaseModel):
    active_mode: Literal["conversation", "decision"] = "conversation"
    available_modes: list[str] = Field(default_factory=lambda: ["conversation", "decision"])
    reason: str = "Manual default"
