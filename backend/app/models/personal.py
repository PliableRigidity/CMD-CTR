"""Models for Phase 6A — Personal Operations Layer."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Reminders ────────────────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    message: str
    trigger_at: str       # ISO UTC datetime
    recurrence: str = "once"   # "once" | "daily" | "weekly:N" | "monthly:N"
    source: str = "chat"
    task_id: Optional[str] = None
    event_id: Optional[str] = None


class ReminderUpdate(BaseModel):
    message: Optional[str] = None
    trigger_at: Optional[str] = None
    recurrence: Optional[str] = None
    snoozed_until: Optional[str] = None


class Reminder(BaseModel):
    id: str
    message: str
    trigger_at: str
    recurrence: str = "once"
    completed: bool = False
    created_at: str
    last_fired_at: Optional[str] = None
    status: str = "scheduled"
    updated_at: Optional[str] = None
    delivered_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    snoozed_until: Optional[str] = None
    delivery_status: str = "pending"
    delivery_error: Optional[str] = None
    source: str = "chat"
    task_id: Optional[str] = None
    event_id: Optional[str] = None


# ── Tasks ─────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "normal"   # "low" | "normal" | "high"
    project: Optional[str] = None
    due_at: Optional[str] = None
    estimated_minutes: Optional[int] = None
    reminder_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    project: Optional[str] = None
    due_at: Optional[str] = None
    estimated_minutes: Optional[int] = None
    reminder_id: Optional[str] = None


class Task(BaseModel):
    id: str
    title: str
    status: str = "open"
    description: Optional[str] = None
    priority: str = "normal"
    project: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    due_at: Optional[str] = None
    estimated_minutes: Optional[int] = None
    reminder_id: Optional[str] = None
    completed_at: Optional[str] = None
    cancelled_at: Optional[str] = None


# ── Calendar ──────────────────────────────────────────────────────────────────

class CalendarEventCreate(BaseModel):
    title: str
    start_at: str              # ISO UTC datetime
    end_at: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    source: str = "local"
    timezone: str = "UTC"
    all_day: bool = False
    external_calendar_id: Optional[str] = None


class CalendarEvent(BaseModel):
    id: str
    title: str
    start_at: str
    end_at: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    source: str = "local"
    created_at: str
    timezone: str = "UTC"
    all_day: bool = False
    external_calendar_id: Optional[str] = None
    updated_at: Optional[str] = None
