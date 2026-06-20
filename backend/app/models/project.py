"""Project Registry models."""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, field_validator


class ProjectCreate(BaseModel):
    name: str
    status: str = "active"       # active | paused | complete | blocked
    priority: str = "normal"     # critical | high | normal | low
    tags: list[str] = []
    brain63_key: Optional[str] = None
    notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None
    brain63_key: Optional[str] = None
    notes: Optional[str] = None


class Project(BaseModel):
    id: str
    name: str
    status: str = "active"
    priority: str = "normal"
    tags: list[str] = []
    brain63_key: Optional[str] = None
    notes: Optional[str] = None
    last_activity: Optional[str] = None
    created_at: str
    updated_at: str

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v or []
