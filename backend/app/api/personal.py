"""Personal Operations REST API — reminders, tasks, calendar."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.personal import (
    CalendarEvent,
    CalendarEventCreate,
    Reminder,
    ReminderCreate,
    Task,
    TaskCreate,
)
from backend.app.services.calendar_service import CalendarService
from backend.app.services.reminder_service import ReminderService
from backend.app.services.task_service import TaskService

router = APIRouter(tags=["personal"])

# ── Reminders ────────────────────────────────────────────────────────────────

@router.get("/reminders", response_model=list[Reminder])
async def list_reminders(include_completed: bool = False):
    return ReminderService().list_reminders(include_completed)


@router.post("/reminders", response_model=Reminder, status_code=201)
async def create_reminder(data: ReminderCreate):
    return ReminderService().create_reminder(
        message=data.message, trigger_at=data.trigger_at, recurrence=data.recurrence
    )


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str):
    ok = ReminderService().complete_reminder(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"id": reminder_id, "completed": True}


@router.delete("/reminders/{reminder_id}", status_code=204)
async def delete_reminder(reminder_id: str):
    ok = ReminderService().delete_reminder(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")


# ── Tasks ─────────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[Task])
async def list_tasks(status: str = "pending"):
    return TaskService().list_tasks(status)


@router.post("/tasks", response_model=Task, status_code=201)
async def create_task(data: TaskCreate):
    return TaskService().create_task(
        title=data.title, priority=data.priority, project=data.project
    )


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    ok = TaskService().complete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task_id, "status": "done"}


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    ok = TaskService().delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")


# ── Calendar ──────────────────────────────────────────────────────────────────

@router.get("/calendar/today", response_model=list[CalendarEvent])
async def calendar_today():
    return CalendarService().get_today()


@router.get("/calendar/upcoming", response_model=list[CalendarEvent])
async def calendar_upcoming(days: int = 7):
    return CalendarService().get_upcoming(days)


@router.post("/calendar/events", response_model=CalendarEvent, status_code=201)
async def create_event(data: CalendarEventCreate):
    return CalendarService().create_event(data)


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_event(event_id: str):
    ok = CalendarService().delete_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Event not found")
