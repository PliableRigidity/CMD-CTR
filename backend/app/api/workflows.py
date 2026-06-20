"""Workflows API — Phase 17B."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["workflows"])


@router.get("/workflows")
async def list_workflows(limit: int = 50, status: str = ""):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().get_all(limit=limit, status=status)


@router.get("/workflows/pending")
async def pending_workflows(session_id: str = ""):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().get_pending(session_id=session_id)


@router.get("/workflows/history")
async def workflow_history(limit: int = 50):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().get_history(limit=limit)


@router.get("/workflows/{code}")
async def get_workflow(code: str):
    from backend.app.services.workflow_engine import get_workflow_engine
    wf = get_workflow_engine().get(code)
    if not wf:
        return {"error": f"Workflow '{code}' not found."}
    return wf


class WorkflowAction(BaseModel):
    code: str


@router.post("/workflows/approve")
async def approve_workflow(data: WorkflowAction):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().approve(data.code)


@router.post("/workflows/reject")
async def reject_workflow(data: WorkflowAction):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().reject(data.code)


@router.post("/workflows/cancel")
async def cancel_workflow(data: WorkflowAction):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().cancel(data.code)
