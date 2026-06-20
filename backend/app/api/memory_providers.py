"""Memory Provider API — Phase 18A."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["memory-providers"])


@router.get("/memory/providers")
async def list_providers():
    from backend.app.services.memory_manager import get_memory_manager
    return get_memory_manager().providers()


@router.get("/memory/health")
async def memory_health():
    from backend.app.services.memory_manager import get_memory_manager
    return get_memory_manager().health()


@router.get("/memory/timeline")
async def memory_timeline(project: str = "", limit: int = 50):
    from backend.app.services.memory_manager import get_memory_manager
    entries = get_memory_manager().timeline(project=project, limit=limit)
    return [
        {
            "id": e.id, "provider": e.provider, "type": e.type,
            "title": e.title, "content": e.content, "project": e.project,
            "date": e.date, "source": e.source, "score": e.score,
            "metadata": e.metadata,
        }
        for e in entries
    ]


@router.get("/memory/relationships")
async def memory_relationships(entity: str = "", limit: int = 20):
    from backend.app.services.memory_manager import get_memory_manager
    return get_memory_manager().relationships(entity=entity, limit=limit)


class SearchRequest(BaseModel):
    query: str
    project: str = ""
    providers: list[str] = []
    limit: int = 20


@router.post("/memory/search")
async def memory_search(data: SearchRequest):
    from backend.app.services.memory_manager import get_memory_manager
    entries = get_memory_manager().search(
        query=data.query, project=data.project,
        providers=data.providers or None, limit=data.limit,
    )
    return [
        {
            "id": e.id, "provider": e.provider, "type": e.type,
            "title": e.title, "content": e.content, "project": e.project,
            "date": e.date, "source": e.source, "score": e.score,
            "metadata": e.metadata,
        }
        for e in entries
    ]


class StoreRequest(BaseModel):
    provider: str
    entry: dict


@router.post("/memory/store")
async def memory_store(data: StoreRequest):
    from backend.app.services.memory_manager import get_memory_manager
    result_id = get_memory_manager().store(data.provider, data.entry)
    if result_id:
        return {"ok": True, "id": result_id}
    return {"ok": False, "error": "Provider not found or store not supported."}
