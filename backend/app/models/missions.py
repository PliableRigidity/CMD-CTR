from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Mission(BaseModel):
    id: str
    code: str
    name: str
    description: str
    status: Literal["active", "monitoring", "paused"] = "active"
    relevance_keywords: list[str] = []


class MissionRelevance(BaseModel):
    mission_id: str
    code: str
    mission_name: str
    score: int  # 0–10
