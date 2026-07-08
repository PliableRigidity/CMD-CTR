"""KOSINE API — Phase 19.

Status, Brain63→KOSINE migration (preview/apply/backup/restore), write audit,
and the autonomous maintenance loop (suggestions only).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("silvia.api.kosine")

router = APIRouter(prefix="/kosine", tags=["kosine"])


# ── status / health ────────────────────────────────────────────────────────────

@router.get("/status")
async def kosine_status():
    from backend import config
    from backend.app.memory import kosine_client as kc

    available = kc.is_available()
    obj_count = None
    if available:
        try:
            obj_count = len(kc.get_client().list_objects(limit=100000) or [])
        except Exception:
            obj_count = None
    from backend.app.services.memory_manager import get_memory_manager
    return {
        "enabled": config.KOSINE_ENABLED,
        "primary": config.KOSINE_PRIMARY,
        "writes_allowed": config.KOSINE_ALLOW_WRITES,
        "maintenance_autodraft": config.KOSINE_MAINTENANCE_AUTODRAFT,
        "mode": "rest" if config.KOSINE_BASE_URL else "in_process",
        "db_path": config.KOSINE_DB_PATH,
        "base_url": config.KOSINE_BASE_URL or None,
        "available": available,
        "last_error": kc.last_error(),
        "object_count": obj_count,
        "priority": get_memory_manager()._priority,
    }


# ── migration ────────────────────────────────────────────────────────────────

class MigrateRequest(BaseModel):
    backup: bool = True


@router.post("/migrate/preview")
async def migrate_preview():
    from backend.app.services import kosine_migration as km
    try:
        return {"ok": True, **km.preview()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/migrate")
async def migrate_apply(data: MigrateRequest):
    from backend.app.services import kosine_migration as km
    try:
        return {"ok": True, **km.migrate(backup=data.backup)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/backups")
async def list_backups():
    from backend.app.services import kosine_migration as km
    try:
        return {"ok": True, "backups": km.list_backups()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class RestoreRequest(BaseModel):
    backup_name: str
    confirm: bool = False


@router.post("/restore")
async def restore(data: RestoreRequest):
    from backend.app.services import kosine_migration as km
    try:
        return {"ok": True, **km.restore(data.backup_name, confirm=data.confirm)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── audit ────────────────────────────────────────────────────────────────────

@router.get("/audit")
async def audit(limit: int = 50):
    from backend.app.memory import kosine_audit as ka
    return {"records": ka.read_audit(limit=limit), "path": str(ka.audit_path())}


# ── maintenance (suggestions only) ───────────────────────────────────────────

@router.get("/maintenance/scan")
async def maintenance_scan(limit: int = 100):
    """Read-only scan: detect stale/incomplete/orphan/duplicate objects."""
    from backend.app.services import kosine_maintenance as kmnt
    try:
        return {"ok": True, "findings": kmnt.scan(limit=limit)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class MaintenanceRunRequest(BaseModel):
    draft: bool = False  # when True (and autodraft allowed) create suggestion workflows


@router.post("/maintenance/run")
async def maintenance_run(data: MaintenanceRunRequest):
    from backend.app.services import kosine_maintenance as kmnt
    try:
        return {"ok": True, **kmnt.run(draft=data.draft)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── suggestions (approval-gated apply) ────────────────────────────────────────

@router.get("/suggestions")
async def list_suggestions(limit: int = 50):
    """List KOSINE suggestion workflows (drafts + resolved)."""
    from backend.app.services.workflow_engine import get_workflow_engine
    from backend.app.services.kosine_apply import SUGGESTION_CATEGORY
    wfs = [w for w in get_workflow_engine().get_all(limit=200)
           if w.get("category") == SUGGESTION_CATEGORY][:limit]
    return {"ok": True, "suggestions": wfs, "count": len(wfs)}


class ApplyRequest(BaseModel):
    approve: bool = False   # approve the workflow first, then apply
    dry_run: bool = False   # validate + preview only; no write, no status change


@router.post("/suggestions/{code}/apply")
async def apply_suggestion(code: str, data: ApplyRequest = ApplyRequest()):
    from backend.app.services import kosine_apply as ka
    try:
        return ka.apply_suggestion(code, approve=data.approve, dry_run=data.dry_run, actor="user")
    except Exception as e:
        return {"ok": False, "code": code, "error": str(e)}
