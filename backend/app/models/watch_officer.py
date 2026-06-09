from __future__ import annotations

from pydantic import BaseModel


class WatchAlertCreate(BaseModel):
    message: str
    category: str = "system"   # infra | intel | mission | system | security
    severity: str = "info"     # info | warning | critical


class WatchAlert(BaseModel):
    id: str
    message: str
    category: str
    severity: str
    created_at: str
    dismissed: bool = False
