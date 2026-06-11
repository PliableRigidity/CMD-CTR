from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class WatchAlertCreate(BaseModel):
    message: str
    category: str = "system"   # infra | intel | mission | system | security
    severity: str = "info"     # info | warning | critical
    rule_key: Optional[str] = None


class WatchAlert(BaseModel):
    id: str
    message: str
    category: str
    severity: str
    created_at: str
    dismissed: bool = False
    rule_key: Optional[str] = None
