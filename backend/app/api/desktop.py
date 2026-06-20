"""Desktop awareness API — trusted locations, app registry, file search, launch."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["desktop"])

_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from backend.app.services.desktop_service import DesktopService
        _svc = DesktopService()
    return _svc


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

class LocationCreate(BaseModel):
    name: str
    path: str
    aliases: list[str] = []
    tags: list[str] = []
    description: str = ""


@router.get("/desktop/locations")
async def list_locations():
    return _get_svc().list_locations()


@router.post("/desktop/locations", status_code=201)
async def add_location(body: LocationCreate):
    result = _get_svc().add_location(
        body.name, body.path, body.aliases, body.tags, body.description
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to add location")
    return result


@router.delete("/desktop/locations/{name}")
async def delete_location(name: str):
    ok = _get_svc().delete_location(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Location '{name}' not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

class AppCreate(BaseModel):
    name: str
    executable: str
    aliases: list[str] = []
    category: str = "general"
    description: str = ""


@router.get("/desktop/apps")
async def list_apps():
    return _get_svc().list_apps()


@router.post("/desktop/apps/scan")
async def scan_apps():
    return _get_svc().scan_installed_apps()


@router.get("/desktop/apps/{name}")
async def show_app(name: str):
    matches = _get_svc().find_app_matches(name, limit=5)
    if not matches:
        raise HTTPException(status_code=404, detail=f"App '{name}' not found")
    return {"count": len(matches), "matches": matches}


@router.post("/desktop/apps", status_code=201)
async def add_app(body: AppCreate):
    result = _get_svc().add_app(
        body.name, body.executable, body.aliases, body.category, body.description
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to add app")
    return result


@router.delete("/desktop/apps/{name}")
async def delete_app(name: str):
    ok = _get_svc().delete_app(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"App '{name}' not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# File search
# ---------------------------------------------------------------------------

@router.get("/desktop/files")
async def search_files(
    query: str = "",
    extension: str = "",
    location: str = "",
    max_results: int = 50,
):
    from backend.app.tools.desktop_tool import find_files
    return find_files(query=query, extension=extension, location=location, max_results=min(max_results, 200))


@router.get("/desktop/recent-files")
async def recent_files(
    location: str = "",
    max_results: int = 25,
):
    from backend.app.tools.desktop_tool import recent_files as _recent
    return _recent(location=location, max_results=min(max_results, 100))


# ---------------------------------------------------------------------------
# Open / Launch (called from the UI panel buttons)
# ---------------------------------------------------------------------------

class OpenLocationBody(BaseModel):
    name: str


class OpenAppBody(BaseModel):
    name: str


@router.post("/desktop/open/location")
async def open_location(body: OpenLocationBody):
    from backend.app.tools.desktop_tool import open_location as _open
    result = _open(body.name)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["summary"])
    return result


@router.post("/desktop/open/app")
async def open_app(body: OpenAppBody):
    from backend.app.tools.desktop_tool import open_app as _open
    result = _open(body.name)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result["summary"])
    return result
