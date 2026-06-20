"""Brain63 Steward API — Phase 18B."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["brain63"])


@router.get("/brain63/drafts")
async def list_drafts():
    from backend.app.services.brain_steward import get_brain_steward
    return get_brain_steward().get_drafts()


@router.get("/brain63/health")
async def brain63_health():
    from backend.app.services.brain_steward import get_brain_steward
    return get_brain_steward().get_health()


@router.get("/brain63/coverage")
async def brain63_coverage(project: str = ""):
    from backend.app.services.brain_steward import get_brain_steward
    return get_brain_steward().get_coverage(project=project)


class DraftRequest(BaseModel):
    type: str
    project: str
    title: str
    detail: str = ""
    reason: str = ""
    session_id: str = ""


@router.post("/brain63/draft")
async def create_draft(data: DraftRequest):
    from backend.app.services.brain_steward import get_brain_steward
    bs = get_brain_steward()

    if data.type == "decision":
        draft = bs.draft_decision(data.project, data.title, reason=data.reason)
    elif data.type in ("lesson", "lesson_learned"):
        draft = bs.draft_lesson(data.project, data.title, detail=data.detail)
    elif data.type == "milestone":
        draft = bs.draft_milestone(data.project, data.title, detail=data.detail)
    elif data.type == "roadmap":
        draft = bs.draft_roadmap_update(data.project, data.title)
    else:
        return {"ok": False, "error": f"Unknown draft type: {data.type}"}

    wf = bs.create_draft_workflow(draft, session_id=data.session_id)
    return {"ok": True, "draft": draft, "workflow": wf}


class ApprovalAction(BaseModel):
    code: str


@router.post("/brain63/approve")
async def approve_draft(data: ApprovalAction):
    from backend.app.services.workflow_engine import get_workflow_engine
    from backend.app.services.brain_steward import get_brain_steward
    we = get_workflow_engine()
    result = we.approve(data.code)
    if not result.get("ok"):
        return result
    draft = result.get("tool_args", {})
    if draft:
        we.mark_executing(data.code)
        commit_result = get_brain_steward().commit(draft)
        if commit_result.get("ok"):
            we.mark_completed(data.code, "committed")
        else:
            we.mark_failed(data.code, commit_result.get("error", "commit failed"))
        return {"ok": True, "commit": commit_result, "workflow": data.code}
    return {"ok": False, "error": "No draft data in workflow"}


@router.post("/brain63/reject")
async def reject_draft(data: ApprovalAction):
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine().reject(data.code)


@router.get("/brain63/diff/{code}")
async def get_diff(code: str):
    from backend.app.services.workflow_engine import get_workflow_engine
    wf = get_workflow_engine().get(code)
    if not wf:
        return {"error": f"Workflow '{code}' not found"}
    return {
        "code": wf.get("code", ""),
        "title": wf.get("title", ""),
        "before": wf.get("before_state", ""),
        "after": wf.get("after_state", ""),
        "diff": wf.get("diff_text", ""),
        "changes": wf.get("changes", {}),
    }
