"""Personal Operations REST API — reminders, tasks, calendar."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.personal import (
    CalendarEvent,
    CalendarEventCreate,
    Reminder,
    ReminderCreate,
    ReminderUpdate,
    Task,
    TaskCreate,
    TaskUpdate,
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
        message=data.message, trigger_at=data.trigger_at, recurrence=data.recurrence,
        source=data.source, task_id=data.task_id, event_id=data.event_id,
    )


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: str):
    ok = ReminderService().complete_reminder(reminder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"id": reminder_id, "completed": True}


@router.patch("/reminders/{reminder_id}", response_model=Reminder)
async def update_reminder(reminder_id: str, data: ReminderUpdate):
    svc = ReminderService()
    current = svc.get_reminder(reminder_id)
    if not current:
        raise HTTPException(status_code=404, detail={"error_type": "not_found", "message": "Reminder not found"})
    if data.snoozed_until:
        updated = svc.snooze(reminder_id, data.snoozed_until)
    elif data.trigger_at:
        updated = svc.reschedule(reminder_id, data.trigger_at)
    else:
        updated = svc._update(reminder_id, **data.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=500, detail={"error_type": "verification_failure", "message": "Reminder update was not persisted"})
    return updated


@router.post("/reminders/{reminder_id}/acknowledge", response_model=Reminder)
async def acknowledge_reminder(reminder_id: str):
    updated = ReminderService().acknowledge(reminder_id)
    if not updated: raise HTTPException(status_code=404, detail={"error_type": "not_found", "message": "Reminder not found"})
    return updated


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
        title=data.title, priority=data.priority, project=data.project,
        description=data.description, due_at=data.due_at,
        estimated_minutes=data.estimated_minutes, reminder_id=data.reminder_id,
    )


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    ok = TaskService().complete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task_id, "status": "completed"}


@router.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    task = TaskService().get_task(task_id)
    if not task: raise HTTPException(status_code=404, detail={"error_type": "not_found", "message": "Task not found"})
    return task


@router.patch("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: str, data: TaskUpdate):
    updated = TaskService().update_task(task_id, **data.model_dump(exclude_unset=True))
    if not updated: raise HTTPException(status_code=404, detail={"error_type": "not_found", "message": "Task not found"})
    return updated


@router.post("/tasks/{task_id}/reopen", response_model=Task)
async def reopen_task(task_id: str):
    svc=TaskService()
    if not svc.reopen_task(task_id): raise HTTPException(status_code=404, detail={"error_type": "not_found", "message": "Task not found"})
    return svc.get_task(task_id)


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
