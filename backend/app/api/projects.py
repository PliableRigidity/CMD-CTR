"""Project Registry REST API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.models.project import Project, ProjectCreate, ProjectUpdate
from backend.app.services.project_service import ProjectService

router = APIRouter(tags=["projects"])


def _svc() -> ProjectService:
    return ProjectService()


@router.get("/projects", response_model=list[Project])
async def list_projects(status: str = ""):
    return _svc().list_projects(status=status or None)


@router.post("/projects", response_model=Project, status_code=201)
async def create_project(data: ProjectCreate):
    return _svc().create_project(data)


@router.get("/projects/{project_id}", response_model=Project)
async def get_project(project_id: str):
    p = _svc().get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.put("/projects/{project_id}", response_model=Project)
async def update_project(project_id: str, data: ProjectUpdate):
    p = _svc().update_project(project_id, data)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.post("/projects/{project_id}/touch")
async def touch_project(project_id: str):
    _svc().touch_activity(project_id)
    return {"ok": True}


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str):
    if not _svc().delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
