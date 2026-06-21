from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.presence_service import get_presence

router = APIRouter(prefix="/presence", tags=["presence"])


class FocusRequest(BaseModel):
    enabled: bool | None = None


class WorkSessionRequest(BaseModel):
    project: str | None = None


@router.get("/status")
async def presence_status() -> dict:
    return get_presence().get_status()


@router.get("/context")
async def presence_context() -> dict:
    return get_presence().get_context()


@router.post("/reset")
async def presence_reset() -> dict:
    return get_presence().reset()


@router.post("/focus")
async def presence_focus(body: FocusRequest) -> dict:
    result = get_presence().toggle_focus(body.enabled)
    return {"focus_mode": result}


@router.post("/work-session/start")
async def start_work_session(body: WorkSessionRequest) -> dict:
    return get_presence().start_work_session(body.project)


@router.post("/work-session/end")
async def end_work_session() -> dict:
    return get_presence().end_work_session()
