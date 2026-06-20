"""REST API for the Node Service / Capability layer (Phase 10)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.services import (
    CapabilityExecuteRequest,
    NodeServiceCreate,
    NodeServiceModel,
    NodeServiceUpdate,
    ServiceCapabilityCreate,
    ServiceManifest,
)
from backend.app.services.capability_executor import CapabilityExecutor
from backend.app.services.service_registry import ServiceRegistry

router = APIRouter(tags=["services"])

_registry: ServiceRegistry | None = None
_executor: CapabilityExecutor | None = None


def _get_registry() -> ServiceRegistry:
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry


def _get_executor() -> CapabilityExecutor:
    global _executor
    if _executor is None:
        _executor = CapabilityExecutor()
    return _executor


# ── Service endpoints ─────────────────────────────────────────────────────────

@router.get("/services", response_model=list[NodeServiceModel])
async def list_services(node_id: str | None = None):
    """List all registered services, optionally filtered by node_id."""
    return _get_registry().list_services(node_id=node_id)


@router.get("/services/{service_id}", response_model=NodeServiceModel)
async def get_service(service_id: str):
    svc = _get_registry().get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    return svc


@router.post("/nodes/{node_id}/services", response_model=NodeServiceModel, status_code=201)
async def create_service(node_id: str, data: NodeServiceCreate):
    """Register a new service on a node."""
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    node = ns.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return _get_registry().create_service(node_id, data)


@router.put("/services/{service_id}", response_model=NodeServiceModel)
async def update_service(service_id: str, data: NodeServiceUpdate):
    svc = _get_registry().update_service(service_id, data)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    return svc


@router.delete("/services/{service_id}", status_code=204)
async def delete_service(service_id: str):
    ok = _get_registry().delete_service(service_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Service not found")


# ── Capability endpoints ──────────────────────────────────────────────────────

@router.post("/services/{service_id}/capabilities", status_code=201)
async def add_capability(service_id: str, data: ServiceCapabilityCreate):
    """Add a capability to a service."""
    svc = _get_registry().get_service(service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    cap = _get_registry().add_capability(service_id, data)
    return cap


@router.delete("/capabilities/{capability_id}", status_code=204)
async def delete_capability(capability_id: str):
    ok = _get_registry().delete_capability(capability_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Capability not found")


@router.get("/capabilities/search")
async def search_capabilities(
    capability: str,
    node: str | None = None,
    running_only: bool = False,
):
    """Find which services expose a given capability name or namespace."""
    matches = _get_registry().find_capability(
        capability, node_name=node, running_only=running_only
    )
    return {"capability": capability, "matches": [m.model_dump() for m in matches]}


@router.post("/capabilities/execute")
async def execute_capability(req: CapabilityExecuteRequest):
    """Execute a capability. Returns the transport result."""
    result = await _get_executor().execute(
        capability=req.capability,
        args=req.args,
        service_id=req.service_id,
        node_name=req.node_name,
    )
    if not result["ok"]:
        raise HTTPException(
            status_code=502 if result.get("error") else 404,
            detail=result.get("error") or result.get("summary"),
        )
    return result


@router.post("/capabilities/run")
async def run_capability(req: CapabilityExecuteRequest):
    """Execute a capability — always returns 200 with ok/summary/error for UI use."""
    result = await _get_executor().execute(
        capability=req.capability,
        args=req.args,
        service_id=req.service_id,
        node_name=req.node_name,
    )
    return result


# ── Manifest ingest (called by agent poll loop or silvia-agent push) ──────────

@router.post("/nodes/{node_id}/manifest", status_code=200)
async def ingest_manifest(node_id: str, manifest: ServiceManifest):
    """Upsert services + capabilities from a device-reported manifest."""
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    node = ns.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    result = _get_registry().ingest_manifest(node_id, manifest)
    return {"node_id": node_id, **result}
