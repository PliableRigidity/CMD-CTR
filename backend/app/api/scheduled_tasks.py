"""REST API for scheduled autonomous tasks."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.services.scheduled_task_service import ScheduledTaskService

router = APIRouter(tags=["scheduled-tasks"])

_service: ScheduledTaskService | None = None


def _get_service() -> ScheduledTaskService:
    global _service
    if _service is None:
        _service = ScheduledTaskService()
    return _service


class TaskCreate(BaseModel):
    name: str
    prompt: str
    interval_minutes: int


class TaskUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    interval_minutes: int | None = None
    enabled: int | None = None


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(svc: ScheduledTaskService = Depends(_get_service)):
    return svc.list_tasks()


@router.post("/scheduled-tasks", status_code=201)
async def create_scheduled_task(
    data: TaskCreate,
    svc: ScheduledTaskService = Depends(_get_service),
):
    if data.interval_minutes < 1:
        raise HTTPException(status_code=400, detail="interval_minutes must be >= 1")
    return svc.create_task(data.name, data.prompt, data.interval_minutes)


@router.put("/scheduled-tasks/{task_id}")
async def update_scheduled_task(
    task_id: str,
    data: TaskUpdate,
    svc: ScheduledTaskService = Depends(_get_service),
):
    task = svc.update_task(task_id, **data.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/scheduled-tasks/{task_id}", status_code=204)
async def delete_scheduled_task(
    task_id: str,
    svc: ScheduledTaskService = Depends(_get_service),
):
    deleted = svc.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
