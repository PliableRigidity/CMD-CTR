"""Project Intelligence API — Phase 14A.

Endpoints for project briefings, blockers, readiness, dependencies,
cross-project queries, and knowledge graph CRUD.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.project_intelligence import ProjectIntelligence
from backend.app.services.knowledge_graph import get_graph

# Two routers — one for /projects/intelligence, one for /knowledge
router = APIRouter(tags=["project-intelligence"])
knowledge_router = APIRouter(tags=["knowledge-graph"])


# ── Project Intelligence ──────────────────────────────────────────────────────

@router.get("/projects/intelligence/{project}")
async def get_project_briefing(project: str):
    pi = ProjectIntelligence()
    data = pi.get_briefing(project)
    return {"ok": True, "data": data}


@router.get("/projects/intelligence/{project}/blockers")
async def get_project_blockers(project: str):
    pi = ProjectIntelligence()
    blockers = pi.get_blockers(project)
    return {"ok": True, "data": blockers, "count": len(blockers)}


@router.get("/projects/intelligence/{project}/readiness")
async def get_project_readiness(project: str):
    pi = ProjectIntelligence()
    data = pi.get_readiness(project)
    return {"ok": True, "data": data}


@router.get("/projects/intelligence/{project}/dependencies")
async def get_project_dependencies(project: str):
    pi = ProjectIntelligence()
    data = pi.get_dependencies(project)
    return {"ok": True, "data": data}


@router.get("/projects/using/{component}")
async def get_projects_using_component(component: str):
    pi = ProjectIntelligence()
    results = pi.get_projects_using(component)
    return {"ok": True, "data": results, "count": len(results)}


@router.get("/projects/blocked")
async def get_blocked_projects():
    pi = ProjectIntelligence()
    results = pi.get_blocked_projects()
    return {"ok": True, "data": results, "count": len(results)}


@router.get("/projects/startable")
async def get_startable_projects():
    pi = ProjectIntelligence()
    results = pi.get_startable_projects()
    return {"ok": True, "data": results, "count": len(results)}


# ── Knowledge Graph ───────────────────────────────────────────────────────────

@knowledge_router.get("/knowledge/entities")
async def list_entities(type: str = ""):
    kg = get_graph()
    entities = kg.list_entities(type=type or None)
    return {"ok": True, "data": entities, "count": len(entities)}


@knowledge_router.get("/knowledge/relationships")
async def list_relationships(entity_id: str = ""):
    kg = get_graph()
    rels = kg.list_relationships(entity_id=entity_id or None)
    return {"ok": True, "data": rels, "count": len(rels)}


@knowledge_router.get("/knowledge/graph")
async def get_full_graph():
    kg = get_graph()
    data = kg.get_nodes_edges()
    return {"ok": True, "data": data}


@knowledge_router.get("/knowledge/graph/project/{project}")
async def get_project_graph(project: str):
    kg = get_graph()
    data = kg.get_project_subgraph_nodes_edges(project)
    return {"ok": True, "data": data, "project": project}


@knowledge_router.post("/knowledge/rebuild")
async def rebuild_knowledge_graph():
    from backend.app.services.knowledge_graph import rebuild_from_data_sources
    result = rebuild_from_data_sources()
    return result


class RelationshipCreate(BaseModel):
    from_name: str
    from_type: str
    to_name: str
    to_type: str
    rel_type: str


@knowledge_router.post("/knowledge/relationships")
async def add_relationship(body: RelationshipCreate):
    from backend.app.services.knowledge_graph import ENTITY_TYPES, RELATIONSHIP_TYPES
    if body.from_type not in ENTITY_TYPES:
        raise HTTPException(400, f"Invalid from_type: {body.from_type}")
    if body.to_type not in ENTITY_TYPES:
        raise HTTPException(400, f"Invalid to_type: {body.to_type}")
    if body.rel_type not in RELATIONSHIP_TYPES:
        raise HTTPException(400, f"Invalid rel_type: {body.rel_type}")
    kg = get_graph()
    from_id = kg.upsert_entity(body.from_type, body.from_name)
    to_id = kg.upsert_entity(body.to_type, body.to_name)
    kg.add_relationship(from_id, to_id, body.rel_type)
    return {"ok": True, "from_id": from_id, "to_id": to_id, "rel_type": body.rel_type}


@knowledge_router.delete("/knowledge/relationships/{from_id}/{to_id}/{rel_type}")
async def remove_relationship(from_id: str, to_id: str, rel_type: str):
    kg = get_graph()
    kg.remove_relationship(from_id, to_id, rel_type)
    return {"ok": True}


# ── Engineering Memory (Phase 14C) ────────────────────────────────────────────

memory_router = APIRouter(tags=["project-memory"])


class MemoryRecordCreate(BaseModel):
    project: str
    type: str
    title: str
    summary: str = ""
    reasoning: str = ""
    date: str = ""
    tags: list[str] = []
    source: str = "manual"


@memory_router.get("/memory/projects")
async def list_memory_projects():
    from backend.app.services.project_memory import get_memory
    projects = get_memory().list_projects()
    return {"ok": True, "data": projects}


@memory_router.get("/memory/projects/{project}")
async def get_project_memory(project: str):
    from backend.app.services.project_memory import get_memory
    memories = get_memory().get_project_memories(project)
    counts = get_memory().get_counts_by_type(project)
    return {"ok": True, "data": memories, "count": len(memories), "by_type": counts, "project": project}


@memory_router.get("/memory/decisions/{project}")
async def get_project_decisions(project: str):
    from backend.app.services.project_memory import get_memory
    data = get_memory().get_project_memories(project, type="decision")
    return {"ok": True, "data": data, "count": len(data)}


@memory_router.get("/memory/lessons/{project}")
async def get_project_lessons(project: str):
    from backend.app.services.project_memory import get_memory
    data = get_memory().get_project_memories(project, type="lesson")
    return {"ok": True, "data": data, "count": len(data)}


@memory_router.get("/memory/failures/{project}")
async def get_project_failures(project: str):
    from backend.app.services.project_memory import get_memory
    data = get_memory().get_project_memories(project, type="failure")
    return {"ok": True, "data": data, "count": len(data)}


@memory_router.get("/memory/milestones/{project}")
async def get_project_milestones(project: str):
    from backend.app.services.project_memory import get_memory
    data = get_memory().get_project_memories(project, type="milestone")
    return {"ok": True, "data": data, "count": len(data)}


@memory_router.get("/memory/timeline/{project}")
async def get_project_timeline(project: str):
    from backend.app.services.project_memory import get_memory
    data = get_memory().get_timeline(project)
    return {"ok": True, "data": data, "count": len(data), "project": project}


@memory_router.get("/memory/search")
async def search_memory(q: str = "", project: str = ""):
    from backend.app.services.project_memory import get_memory
    if not q:
        raise HTTPException(400, "q parameter required")
    data = get_memory().search(q, project=project or None)
    return {"ok": True, "data": data, "count": len(data)}


@memory_router.get("/memory/recent")
async def get_recent_memory(days: int = 30):
    from backend.app.services.project_memory import get_memory
    data = get_memory().get_recent(days=days)
    return {"ok": True, "data": data, "count": len(data)}


@memory_router.post("/memory/record")
async def record_memory(body: MemoryRecordCreate):
    from backend.app.services.project_memory import get_memory, MEMORY_TYPES
    if body.type not in MEMORY_TYPES:
        raise HTTPException(400, f"Invalid type. Valid: {sorted(MEMORY_TYPES)}")
    mem_id = get_memory().record(
        project=body.project,
        type=body.type,
        title=body.title,
        summary=body.summary,
        reasoning=body.reasoning,
        date=body.date or None,
        tags=body.tags,
        source=body.source,
    )
    return {"ok": True, "id": mem_id}


@memory_router.delete("/memory/{mem_id}")
async def delete_memory(mem_id: str):
    from backend.app.services.project_memory import get_memory
    ok = get_memory().delete(mem_id)
    if not ok:
        raise HTTPException(404, "Memory not found")
    return {"ok": True}


@memory_router.post("/memory/import")
async def import_from_brain63(project: str = ""):
    from backend.app.services.project_memory import get_memory
    result = get_memory().import_from_brain63(project=project or None)
    return result
