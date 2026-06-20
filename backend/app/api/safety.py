"""Safety & Approvals API — Phase 17A."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["safety"])


@router.get("/approvals")
async def list_approvals(limit: int = 50):
    from backend.app.services.approval_manager import get_approval_manager
    return get_approval_manager().get_all(limit=limit)


@router.get("/approvals/pending")
async def pending_approvals(session_id: str = ""):
    from backend.app.services.approval_manager import get_approval_manager
    return get_approval_manager().get_pending(session_id=session_id)


class ApprovalAction(BaseModel):
    code: str


@router.post("/approvals/approve")
async def approve_action(data: ApprovalAction):
    from backend.app.services.approval_manager import get_approval_manager
    return get_approval_manager().approve(data.code)


@router.post("/approvals/reject")
async def reject_action(data: ApprovalAction):
    from backend.app.services.approval_manager import get_approval_manager
    return get_approval_manager().reject(data.code)


@router.get("/safety/policies")
async def list_policies():
    from backend.app.services.policy_engine import get_policy_engine
    return get_policy_engine().list_profiles()


@router.get("/safety/policy")
async def active_policy():
    from backend.app.services.policy_engine import get_policy_engine
    pe = get_policy_engine()
    name = pe.get_active_profile()
    return pe.get_profile_detail(name)


class SetPolicyRequest(BaseModel):
    profile: str


@router.post("/safety/policy")
async def set_policy(data: SetPolicyRequest):
    from backend.app.services.policy_engine import get_policy_engine
    return get_policy_engine().set_profile(data.profile)


@router.get("/safety/registry")
async def safety_registry():
    from backend.app.services.safety_engine import get_safety_engine
    return get_safety_engine().get_registry_summary()
