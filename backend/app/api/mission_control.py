"""Mission Control REST API — aggregated operational picture endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from backend.app.services.mission_control_service import MissionControlService

router = APIRouter(tags=["mission_control"])


def _svc() -> MissionControlService:
    return MissionControlService()


@router.get("/mission/briefing")
async def get_briefing():
    return _svc().briefing()


@router.get("/mission/focus")
async def get_focus():
    return _svc().daily_focus()


@router.get("/mission/weekly")
async def get_weekly_review():
    return _svc().weekly_review()


@router.get("/mission/forgotten")
async def get_forgotten():
    return _svc().forgotten_items()


@router.get("/mission/health")
async def get_project_health():
    return _svc().project_health()


@router.get("/mission/evening")
async def get_evening_review():
    return _svc().evening_review()
