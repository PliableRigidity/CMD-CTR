"""Memory API — conversation history and persistent facts."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_router
from backend.app.orchestration.assistant_router import AssistantPlatformRouter

router = APIRouter(tags=["memory"])


def _mem(r: Annotated[AssistantPlatformRouter, Depends(get_router)]):
    return r.memory_service


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

@router.get("/memory/history")
async def get_history(
    session_id: str = Query(default="default-session"),
    limit: int = Query(default=50, ge=1, le=500),
    mem=Depends(_mem),
) -> dict[str, Any]:
    messages = mem.get_history(session_id, limit)
    return {"session_id": session_id, "count": len(messages), "messages": messages}


@router.get("/memory/sessions")
async def list_sessions(mem=Depends(_mem)) -> dict[str, Any]:
    sessions = mem.list_sessions()
    return {"count": len(sessions), "sessions": sessions}


@router.delete("/memory/history")
async def clear_history(
    session_id: str = Query(default="default-session"),
    mem=Depends(_mem),
) -> dict[str, Any]:
    deleted = mem.clear_session(session_id)
    return {"session_id": session_id, "deleted": deleted, "status": "cleared"}


# ---------------------------------------------------------------------------
# Persistent facts
# ---------------------------------------------------------------------------

@router.get("/memory/facts")
async def get_facts(mem=Depends(_mem)) -> dict[str, Any]:
    return {"facts": mem.all_facts()}


@router.post("/memory/facts")
async def set_fact(key: str, value: str, mem=Depends(_mem)) -> dict[str, Any]:
    mem.remember(key, value)
    return {"key": key, "value": value, "status": "saved"}
