"""Engineering Planner API — Phase 15B."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["planner"])


@router.get("/planner/templates")
async def list_templates():
    from backend.app.services.engineering_planner import get_planner
    return {"ok": True, "templates": get_planner().list_templates()}


@router.get("/planner/templates/{template_id}")
async def get_template(template_id: str):
    from backend.app.services.engineering_planner import get_planner
    tmpl = get_planner().get_template(template_id)
    if not tmpl:
        return {"ok": False, "error": f"Template '{template_id}' not found."}
    return {"ok": True, "template": tmpl}


@router.get("/planner/recommendations")
async def get_recommendations():
    from backend.app.services.engineering_planner import get_planner
    return get_planner().get_recommendations()


@router.get("/planner/what-can-i-build")
async def what_can_i_build():
    from backend.app.services.engineering_planner import get_planner
    return get_planner().what_can_i_build()


class DesignRequest(BaseModel):
    description: str


@router.post("/planner/design")
async def design_project(data: DesignRequest):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().design_project(data.description)


class CreateProjectRequest(BaseModel):
    name: str
    template_id: Optional[str] = None


@router.post("/planner/project")
async def create_project(data: CreateProjectRequest):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().create_project(data.name, template_id=data.template_id)


@router.post("/planner/bom")
async def generate_bom(data: DesignRequest):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().generate_bom(data.description)


@router.get("/planner/bom/{project}")
async def get_bom(project: str):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().generate_bom(project)


@router.post("/planner/roadmap")
async def generate_roadmap(data: DesignRequest):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().generate_roadmap(data.description)


@router.get("/planner/roadmap/{project}")
async def get_roadmap(project: str):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().generate_roadmap(project)


@router.post("/planner/gap-analysis")
async def gap_analysis(data: DesignRequest):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().gap_analysis(data.description)


@router.get("/planner/gap-analysis/{project}")
async def get_gap_analysis(project: str):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().gap_analysis(project)


@router.get("/planner/can-i-build/{project}")
async def can_i_build(project: str):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().can_i_build(project)


@router.get("/planner/architecture/{project}")
async def get_architecture(project: str):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().get_architecture(project)


@router.get("/planner/procurement/{project}")
async def get_procurement_plan(project: str):
    from backend.app.services.engineering_planner import get_planner
    return get_planner().procurement_plan(project)
