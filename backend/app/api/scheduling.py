"""Canonical scheduling API used by chat and SILVIA V2."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.models.personal import CalendarEventCreate
from backend.app.services.calendar_service import CalendarService
from backend.app.services.datetime_service import parse_datetime, parse_event_request
from backend.app.services.reminder_service import ReminderService
from backend.app.services.task_service import TaskService
from backend.app.tools.time_tool import get_user_timezone

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


class NaturalRequest(BaseModel):
    text: str


class EventPatch(BaseModel):
    title: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    timezone: str | None = None
    all_day: bool | None = None


@router.post("/parse")
async def parse(value: NaturalRequest):
    return parse_datetime(value.text).model_dump()


@router.post("/events/natural", status_code=201)
async def create_natural_event(value: NaturalRequest):
    try:
        title, parsed = parse_event_request(value.text)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, detail={"error_type": "parse_error", "message": str(exc)}) from exc
    all_day = parsed.resolved_time is None and bool(
        "all day" in value.text.lower() or
        any(word in title.lower() for word in ("birthday", "anniversary", "holiday"))
    )
    if parsed.resolved_time is None and not all_day:
        raise HTTPException(409, detail={"error_type": "needs_time", "message": f"What time is {title}?"})
    start = parsed.resolved_date if all_day else parsed.utc_iso
    event = CalendarService().create_event(CalendarEventCreate(
        title=title, start_at=start or "", timezone=parsed.timezone, all_day=all_day,
    ))
    verified = CalendarService().get_event(event.id)
    if not verified:
        raise HTTPException(500, detail={"error_type": "verification_failure", "message": "Event was not persisted"})
    return verified


@router.patch("/events/{event_id}")
async def update_event(event_id: str, value: EventPatch):
    updated = CalendarService().update_event(event_id, **value.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, detail={"error_type": "not_found", "message": "Event not found"})
    return updated


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(event_id: str):
    if not CalendarService().delete_event(event_id):
        raise HTTPException(404, detail={"error_type": "not_found", "message": "Event not found"})


@router.get("/overview")
async def overview(start: str, end: str) -> dict[str, Any]:
    tz_name, tz = get_user_timezone(), ZoneInfo(get_user_timezone())
    try:
        start_dt = datetime.combine(datetime.fromisoformat(start).date(), time.min, tz)
        end_dt = datetime.combine(datetime.fromisoformat(end).date(), time.min, tz)
    except ValueError as exc:
        raise HTTPException(422, detail="Dates must use YYYY-MM-DD") from exc
    events = CalendarService().get_events(start_dt, end_dt)
    tasks = TaskService().list_tasks("all")
    reminders = ReminderService().list_reminders(False)
    task_data = [item.model_dump() for item in tasks if item.due_at and start <= item.due_at[:10] < end]
    reminder_data = [item.model_dump() for item in reminders if start <= item.trigger_at[:10] < end]
    event_data = [item.model_dump() for item in events]
    marked = sorted({item["start_at"][:10] for item in event_data} |
                    {item["due_at"][:10] for item in task_data} |
                    {item["trigger_at"][:10] for item in reminder_data})
    return {"timezone": tz_name, "events": event_data, "tasks": task_data,
            "reminders": reminder_data, "marked_dates": marked, "calendar_status": "available"}
