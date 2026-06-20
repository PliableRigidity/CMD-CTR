"""Observability API — Phase 13C.

GET /api/observability/recent          — last N execution records
GET /api/observability/failures        — failure log
GET /api/observability/planner         — planner trace
GET /api/observability/health          — system health snapshot
GET /api/observability/node/{node}     — executions for a specific node
GET /api/observability/capability/{cap} — executions for a capability
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.app.services.execution_ledger import get_ledger

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/recent")
async def obs_recent(limit: int = 20, status: str = "", node: str = "", capability: str = ""):
    ledger = get_ledger()
    rows = ledger.get_recent(
        limit=min(limit, 200),
        node=node or None,
        capability=capability or None,
        status=status or None,
    )
    return {"ok": True, "data": rows, "count": len(rows)}


@router.get("/failures")
async def obs_failures(limit: int = 20):
    rows = get_ledger().get_failures(limit=min(limit, 200))
    return {"ok": True, "data": rows, "count": len(rows)}


@router.get("/planner")
async def obs_planner(limit: int = 20):
    rows = get_ledger().get_planner_trace(limit=min(limit, 200))
    return {"ok": True, "data": rows, "count": len(rows)}


@router.get("/health")
async def obs_health():
    from backend.app.services.system_health import get_overall_health
    data = get_overall_health()
    return {"ok": True, "data": data}


@router.get("/node/{node}")
async def obs_node(node: str, limit: int = 20):
    rows = get_ledger().get_recent(limit=min(limit, 100), node=node)
    return {"ok": True, "node": node, "data": rows, "count": len(rows)}


@router.get("/capability/{capability}")
async def obs_capability(capability: str, limit: int = 20):
    rows = get_ledger().get_recent(limit=min(limit, 100), capability=capability)
    return {"ok": True, "capability": capability, "data": rows, "count": len(rows)}
