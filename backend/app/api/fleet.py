"""Fleet Management API — Phase 13B.

Endpoints:
  GET  /api/fleet/status        — aggregate health score + counts
  GET  /api/fleet/groups        — nodes grouped by type / tag / service
  GET  /api/fleet/offline       — nodes currently offline
  GET  /api/fleet/unhealthy     — nodes in warning or critical state
  GET  /api/fleet/nodes         — filtered node list (?filter_type=type&filter_value=raspberry-pi)
  POST /api/fleet/action        — bulk capability execution (dry_run: bool field)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from backend.app.services.fleet_manager import FleetManager
from pydantic import BaseModel

router = APIRouter(prefix="/fleet", tags=["fleet"])


def _fm() -> FleetManager:
    return FleetManager()


# ── Models ─────────────────────────────────────────────────────────────────────

class FleetActionRequest(BaseModel):
    capability:   str
    filter_type:  str = "all"
    filter_value: str = ""
    service_name: Optional[str] = None
    args:         Optional[dict] = None
    dry_run:      bool = True


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
async def fleet_status():
    """Fleet health score, online/offline counts, avg CPU/RAM/Disk."""
    data = _fm().get_fleet_status()
    return {"ok": True, "data": data}


@router.get("/groups")
async def fleet_groups():
    """Nodes grouped by type, tag, and running service."""
    data = _fm().get_fleet_groups()
    return {"ok": True, "data": data}


@router.get("/offline")
async def fleet_offline():
    """All nodes currently offline."""
    nodes = _fm().get_offline_nodes()
    return {"ok": True, "data": {"nodes": nodes, "count": len(nodes)}}


@router.get("/unhealthy")
async def fleet_unhealthy():
    """Nodes in warning or critical health state."""
    nodes = _fm().get_unhealthy_nodes()
    return {"ok": True, "data": {"nodes": nodes, "count": len(nodes)}}


@router.get("/nodes")
async def fleet_filter_nodes(filter_type: str = "all", filter_value: str = ""):
    """Filtered node list — filter_type: all|type|tag|service|status."""
    nodes = _fm().get_filtered_nodes(filter_type, filter_value)
    return {"ok": True, "data": {"nodes": nodes, "count": len(nodes),
                                  "filter_type": filter_type, "filter_value": filter_value}}


@router.post("/action")
async def fleet_action(req: FleetActionRequest):
    """Execute a capability across all nodes matching the fleet filter.

    Set dry_run=true (default) to preview targets without dispatching.
    Set dry_run=false to execute for real.
    """
    args = req.args or {}
    if req.service_name and "service" not in args:
        args["service"] = req.service_name

    result = await _fm().execute_fleet_action(
        capability=req.capability,
        filter_type=req.filter_type,
        filter_value=req.filter_value,
        args=args,
        dry_run=req.dry_run,
    )
    return result
