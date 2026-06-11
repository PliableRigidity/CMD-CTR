"""Models for Phase 6A — Personal Operations Layer."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Reminders ────────────────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    message: str
    trigger_at: str       # ISO UTC datetime
    recurrence: str = "once"   # "once" | "daily" | "weekly:N" | "monthly:N"


class Reminder(BaseModel):
    id: str
    message: str
    trigger_at: str
    recurrence: str = "once"
    completed: bool = False
    created_at: str
    last_fired_at: Optional[str] = None


# ── Tasks ─────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    priority: str = "normal"   # "low" | "normal" | "high"
    project: Optional[str] = None


class Task(BaseModel):
    id: str
    title: str
    status: str = "pending"    # "pending" | "done"
    priority: str = "normal"
    project: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ── Calendar ──────────────────────────────────────────────────────────────────

class CalendarEventCreate(BaseModel):
    title: str
    start_at: str              # ISO UTC datetime
    end_at: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    source: str = "local"


class CalendarEvent(BaseModel):
    id: str
    title: str
    start_at: str
    end_at: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    source: str = "local"
    created_at: str
