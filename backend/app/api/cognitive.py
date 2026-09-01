"""Cognitive Graph API (Phase 4/5).

Exposes SILVIA's observable cognitive activity to the frontend graph:
- a snapshot (activation graph + recent events) for late-joining clients, since
  the WebSocket fan-out does not replay;
- the recent typed event stream;
- an on-demand pipeline run (plan → search → rerank → expand → compose) that
  drives real activity into the graph;
- a transient reset (clears visual state only — never any memory provider).

Live events are pushed over the existing WS at /api/ws/events with
{"type": "cognitive", ...}. This does NOT expose model chain-of-thought.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["cognitive"])
logger = logging.getLogger("silvia.api.cognitive")


class CognitiveQueryRequest(BaseModel):
    task: str
    session_id: str = "default"
    project: str = ""
    provider: str = ""


class ExtractRequest(BaseModel):
    user_text: str = ""
    assistant_text: str = ""
    session_id: str = "default"


@router.get("/cognitive/snapshot")
async def snapshot(session_id: str = "", limit: int = 200):
    from backend.app.services.cognition.events import get_cognitive_bus
    return get_cognitive_bus().snapshot(session_id=session_id, limit=limit)


@router.get("/cognitive/events")
async def events(session_id: str = "", limit: int = 200):
    from backend.app.services.cognition.events import get_cognitive_bus
    return {"events": get_cognitive_bus().recent(limit=limit, session_id=session_id)}


@router.post("/cognitive/query")
async def run_query(req: CognitiveQueryRequest):
    """Run the cognition pipeline for a task; emits the event stream and returns
    the composed context + selected/rejected breakdown."""
    from backend.app.services.cognition.pipeline import get_cognition_pipeline
    try:
        result = get_cognition_pipeline().run(
            req.task, session_id=req.session_id, project=req.project,
            provider=req.provider)
        return {"ok": True, **result}
    except Exception as e:
        logger.warning("cognitive query failed: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)}


@router.post("/cognitive/extract")
async def extract(req: ExtractRequest):
    """Extract review-gated write proposals from an interaction (no writes)."""
    from backend.app.services.cognition.pipeline import get_cognition_pipeline
    proposals = get_cognition_pipeline().extract_proposals(
        user_text=req.user_text, assistant_text=req.assistant_text,
        session_id=req.session_id)
    return {"ok": True, "proposals": proposals}


@router.post("/cognitive/reset")
async def reset():
    """Clear transient visual/activation state. Never touches persistent memory."""
    from backend.app.services.cognition.events import get_cognitive_bus
    get_cognitive_bus().reset()
    return {"ok": True}


@router.get("/cognitive/health")
async def health():
    from backend.app.services.cognition.events import get_cognitive_bus
    from backend.app.services.memory_manager import get_memory_manager
    bus = get_cognitive_bus()
    snap = bus.snapshot(limit=1)
    return {
        "ok": True,
        "memory_mode": get_memory_manager().mode(),
        "graph_nodes": len(snap["graph"]["nodes"]),
        "graph_edges": len(snap["graph"]["edges"]),
    }
