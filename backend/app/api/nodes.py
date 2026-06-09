from fastapi import APIRouter, Depends, HTTPException

from backend.app.models.nodes import NODE_TYPES, Node, NodeCreate, NodeMetricsUpdate, NodeUpdate
from backend.app.services.node_service import NodeService

router = APIRouter(tags=["nodes"])

_service: NodeService | None = None


def _get_service() -> NodeService:
    global _service
    if _service is None:
        _service = NodeService()
    return _service


@router.get("/nodes", response_model=list[Node])
async def list_nodes(svc: NodeService = Depends(_get_service)):
    return svc.list_nodes()


@router.get("/nodes/types")
async def get_node_types():
    return NODE_TYPES


@router.post("/nodes", response_model=Node, status_code=201)
async def create_node(data: NodeCreate, svc: NodeService = Depends(_get_service)):
    return svc.create_node(data)


@router.put("/nodes/{node_id}", response_model=Node)
async def update_node(
    node_id: str,
    data: NodeUpdate,
    svc: NodeService = Depends(_get_service),
):
    node = svc.update_node(node_id, data)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.put("/nodes/{node_id}/metrics", response_model=Node)
async def update_metrics(
    node_id: str,
    metrics: NodeMetricsUpdate,
    svc: NodeService = Depends(_get_service),
):
    node = svc.update_metrics(node_id, metrics)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.post("/nodes/{node_id}/probe", response_model=Node)
async def probe_node(node_id: str, svc: NodeService = Depends(_get_service)):
    node = svc.probe_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(node_id: str, svc: NodeService = Depends(_get_service)):
    deleted = svc.delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found or protected")
