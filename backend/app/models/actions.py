from pydantic import BaseModel, Field


class ActionDescriptor(BaseModel):
    id: str
    label: str
    kind: str
    target: str
    description: str
    enabled: bool = True
    aliases: list[str] = Field(default_factory=list)


class ActionExecutionRequest(BaseModel):
    action_id: str | None = None
    target: str | None = None
    args: list[str] = Field(default_factory=list)


class ActionExecutionResponse(BaseModel):
    success: bool
    action: str
    message: str
    opened_target: str | None = None
    details: dict | None = None
