"""Workspace Digital Twin API — Phase 15A + 16A Screen Awareness."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["workspace"])


@router.get("/workspace/status")
async def workspace_status():
    from backend.app.services.digital_twin import get_twin
    return get_twin().workspace_status()


@router.get("/workspace/projects")
async def workspace_projects():
    from backend.app.services.digital_twin import get_twin
    return get_twin().project_states()


@router.get("/workspace/priorities")
async def workspace_priorities():
    from backend.app.services.digital_twin import get_twin
    return get_twin().priorities()


@router.get("/workspace/recommendations")
async def workspace_recommendations():
    from backend.app.services.recommendation_engine import get_engine
    return get_engine().what_should_i_work_on()


@router.get("/workspace/briefing")
async def workspace_briefing():
    from backend.app.services.digital_twin import get_twin
    return get_twin().daily_briefing()


@router.get("/workspace/blocked")
async def workspace_blocked():
    from backend.app.services.digital_twin import get_twin
    return get_twin().blocked_projects()


@router.get("/workspace/ready")
async def workspace_ready():
    from backend.app.services.digital_twin import get_twin
    return get_twin().ready_projects()


@router.get("/workspace/order-recommendations")
async def workspace_order_recommendations():
    from backend.app.services.recommendation_engine import get_engine
    return get_engine().what_to_order()


@router.get("/workspace/closest")
async def workspace_closest():
    from backend.app.services.recommendation_engine import get_engine
    return get_engine().closest_to_completion()


@router.get("/workspace/reconcile/{project}")
async def workspace_reconcile(project: str):
    from backend.app.services.project_reconciler import get_reconciler
    return get_reconciler().reconcile_project(project)


class MarkAcquiredRequest(BaseModel):
    items: list[str]
    state: str = "owned"


@router.post("/workspace/reconcile/{project}/mark")
async def workspace_mark_acquired(project: str, data: MarkAcquiredRequest):
    from backend.app.services.project_reconciler import get_reconciler
    return get_reconciler().mark_acquired(project, data.items, state=data.state)


# ── Screen Awareness (Phase 16A) ────────────────────────────────────────────

@router.get("/workspace/context")
async def workspace_context():
    from backend.app.services.workspace_awareness import get_awareness
    return get_awareness().get_context()


@router.get("/workspace/context/project")
async def workspace_active_project():
    from backend.app.services.workspace_awareness import get_awareness
    return get_awareness().get_active_project()


@router.get("/workspace/context/file")
async def workspace_active_file():
    from backend.app.services.workspace_awareness import get_awareness
    return get_awareness().get_active_file()


@router.get("/workspace/context/application")
async def workspace_active_application():
    from backend.app.services.workspace_awareness import get_awareness
    return get_awareness().get_active_application()


@router.get("/workspace/context/sessions")
async def workspace_recent_sessions(hours: int = 24, limit: int = 20):
    from backend.app.services.workspace_awareness import get_awareness
    return get_awareness().get_recent_sessions(hours=hours, limit=limit)


@router.get("/workspace/context/recent-projects")
async def workspace_recent_projects(hours: int = 24):
    from backend.app.services.workspace_awareness import get_awareness
    return get_awareness().get_recent_projects(hours=hours)


# ── Session Continuity (Phase 16B) ──────────────────────────────────────────

@router.get("/workspace/sessions")
async def list_sessions(hours: int = 48, limit: int = 20):
    from backend.app.services.session_manager import get_session_manager
    sm = get_session_manager()
    sm.build_sessions_from_log()
    return sm.get_recent_sessions(hours=hours, limit=limit)


@router.get("/workspace/sessions/{project}")
async def project_sessions(project: str, limit: int = 10):
    from backend.app.services.session_manager import get_session_manager
    return get_session_manager().get_project_sessions(project, limit=limit)


@router.get("/workspace/recent")
async def recent_activity(hours: int = 24):
    from backend.app.services.session_manager import get_session_manager
    sm = get_session_manager()
    sm.build_sessions_from_log()
    return sm.get_accomplishments(hours=hours)


@router.get("/workspace/profile/{project}")
async def get_workspace_profile(project: str):
    from backend.app.services.session_manager import get_session_manager
    profile = get_session_manager().get_profile(project)
    if not profile:
        return {"ok": False, "error": f"No profile for '{project}'."}
    return {"ok": True, "profile": profile}


@router.get("/workspace/continue/{project}")
async def continue_project(project: str):
    from backend.app.services.session_manager import get_session_manager
    return get_session_manager().continue_project(project)


class RestoreRequest(BaseModel):
    project: str


@router.post("/workspace/restore")
async def restore_workspace(data: RestoreRequest):
    from backend.app.services.workspace_restore import get_restore
    return get_restore().restore(data.project)


@router.post("/workspace/save")
async def save_session():
    from backend.app.services.session_manager import get_session_manager
    return get_session_manager().capture_current()
