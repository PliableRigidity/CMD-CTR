"""System Diagnostics — deep health check for every SILVIA subsystem."""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("silvia.diagnostics")

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"


def _db_ok() -> dict:
    try:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.execute("SELECT 1")
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        return {"status": "OK", "tables": len(tables), "path": str(DB_PATH)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


async def _ollama_ok() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get("http://localhost:11434/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {"status": "OK", "models_loaded": len(models), "models": models[:10]}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _node_registry() -> dict:
    try:
        from backend.app.services.node_service import NodeService
        ns = NodeService()
        nodes = ns.list_nodes()
        online = sum(1 for n in nodes if n.status == "online")
        return {"status": "OK", "total": len(nodes), "online": online}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _service_registry() -> dict:
    try:
        from backend.app.services.service_registry import ServiceRegistry
        sr = ServiceRegistry()
        services = sr.list_services()
        return {"status": "OK", "total": len(services)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _capability_registry() -> dict:
    try:
        from backend.app.services.capability_service import get_capability_block
        block = get_capability_block()
        return {"status": "OK", "has_block": bool(block)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _hardware_inventory() -> dict:
    try:
        from backend.app.services.hardware_service import HardwareService
        hs = HardwareService()
        parts = hs.list_parts()
        return {"status": "OK", "total": len(parts)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _hardware_projects() -> dict:
    try:
        from backend.app.services.hardware_service import HardwareService
        hs = HardwareService()
        projects = hs.list_projects()
        return {"status": "OK", "total": len(projects)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _project_registry() -> dict:
    try:
        from backend.app.services.project_service import ProjectService
        ps = ProjectService()
        projects = ps.list_projects()
        return {"status": "OK", "total": len(projects)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _gmail_status() -> dict:
    try:
        from backend.app.services.productivity.google_provider import GoogleProvider
        from backend.app.services.productivity.auth_service import AuthService
        auth = AuthService()
        gp = GoogleProvider(auth)
        if gp.is_authenticated():
            email = gp.whoami()
            return {"status": "OK", "authenticated": True, "account": email or "connected"}
        return {"status": "NOT_CONFIGURED", "authenticated": False, "detail": "Google OAuth not authenticated"}
    except Exception as e:
        return {"status": "NOT_CONFIGURED", "error": str(e)}


def _calendar_status() -> dict:
    try:
        from backend.app.services.productivity.google_provider import GoogleProvider
        from backend.app.services.productivity.auth_service import AuthService
        auth = AuthService()
        gp = GoogleProvider(auth)
        if gp.is_authenticated():
            return {"status": "OK", "authenticated": True}
        return {"status": "NOT_CONFIGURED", "authenticated": False}
    except Exception as e:
        return {"status": "NOT_CONFIGURED", "error": str(e)}


def _telegram_status() -> dict:
    try:
        from backend.config import TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
        from backend.app.services.telegram_bridge import get_bridge, _read_lock
        bridge = get_bridge()
        lock = _read_lock()
        if not TELEGRAM_ENABLED:
            return {"status": "DISABLED"}
        if not TELEGRAM_BOT_TOKEN:
            return {"status": "NOT_CONFIGURED", "detail": "TELEGRAM_BOT_TOKEN not set"}
        running = bridge.running if bridge else False
        return {
            "status": "OK" if running else "WARNING",
            "running": running,
            "lock_held": lock is not None,
            "allowed_users": len(TELEGRAM_ALLOWED_USER_IDS),
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _reminder_status() -> dict:
    try:
        from backend.app.services.reminder_service import ReminderService
        rs = ReminderService()
        active = rs.list_reminders(include_completed=False)
        due = rs.get_due_reminders()
        completed = rs.list_reminders(include_completed=True)
        stuck = [r for r in due if r.recurrence == "once"]
        return {
            "status": "WARNING" if stuck else "OK",
            "active": len(active),
            "due_now": len(due),
            "stuck": len(stuck),
            "total_ever": len(completed),
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _task_status() -> dict:
    try:
        from backend.app.services.mission_service import MissionService
        ms = MissionService()
        tasks = ms.list_tasks()
        return {"status": "OK", "total": len(tasks)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _workflow_engine() -> dict:
    try:
        from backend.app.services.workflow_engine import get_workflow_engine
        we = get_workflow_engine()
        pending = we.get_pending()
        all_wf = we.get_all(limit=100)
        return {"status": "OK", "pending": len(pending), "total": len(all_wf)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _approval_engine() -> dict:
    try:
        from backend.app.services.approval_manager import get_approval_manager
        am = get_approval_manager()
        pending = am.get_pending()
        return {"status": "OK", "pending": len(pending)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _knowledge_graph() -> dict:
    try:
        from backend.app.services.knowledge_graph import get_knowledge_graph
        kg = get_knowledge_graph()
        summary = kg.get_summary()
        return {"status": "OK", "entities": summary.get("entity_count", 0), "relationships": summary.get("relationship_count", 0)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _project_memory() -> dict:
    try:
        from backend.app.services.project_memory import get_memory
        pm = get_memory()
        projects = pm.list_projects()
        return {"status": "OK", "projects": len(projects)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _digital_twin() -> dict:
    try:
        from backend.app.services.digital_twin import get_twin
        dt = get_twin()
        return {"status": "OK"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _engineering_planner() -> dict:
    try:
        from backend.app.services.engineering_planner import get_planner
        ep = get_planner()
        templates = ep.list_templates()
        return {"status": "OK", "templates": len(templates)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _brain63_provider() -> dict:
    try:
        from backend.config import BRAIN63_VAULT_PATH
        vault = Path(BRAIN63_VAULT_PATH)
        if not vault.exists():
            return {"status": "NOT_CONFIGURED", "detail": f"Vault path not found: {vault}"}
        md_count = len(list(vault.rglob("*.md")))
        return {"status": "OK", "vault": str(vault), "markdown_files": md_count}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _memory_manager() -> dict:
    try:
        from backend.app.services.memory_manager import get_memory_manager
        mm = get_memory_manager()
        providers = mm.list_providers()
        return {"status": "OK", "providers": len(providers)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _brain_steward() -> dict:
    try:
        from backend.app.services.brain_steward import get_brain_steward
        bs = get_brain_steward()
        return {"status": "OK"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _workspace_awareness() -> dict:
    try:
        from backend.app.services.workspace_awareness import get_awareness
        wa = get_awareness()
        return {"status": "OK"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _workspace_restore() -> dict:
    try:
        from backend.app.services.workspace_restore import get_restore
        wr = get_restore()
        return {"status": "OK"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _ssh_profiles() -> dict:
    try:
        from backend.app.services.node_service import NodeService
        ns = NodeService()
        nodes = ns.list_nodes()
        with_ssh = [n for n in nodes if n.ssh_username]
        with_addr = [n for n in nodes if n.hostname or n.ip]
        return {
            "status": "OK",
            "nodes_with_ssh_username": len(with_ssh),
            "nodes_with_address": len(with_addr),
            "profiles": [{"name": n.name, "username": n.ssh_username, "host": n.hostname or n.ip} for n in with_ssh],
        }
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _voice_pipeline() -> dict:
    try:
        from backend.app.services.voice_service import VoiceService
        vs = VoiceService()
        status = vs.get_status()
        return {
            "status": "OK" if status.get("stt_available") or status.get("tts_available") else "NOT_CONFIGURED",
            "stt_available": status.get("stt_available", False),
            "tts_available": status.get("tts_available", False),
        }
    except Exception as e:
        return {"status": "NOT_CONFIGURED", "error": str(e)}


def _watch_officer() -> dict:
    try:
        from backend.app.services.watch_service import WatchService
        ws = WatchService()
        active = ws.get_active_alerts()
        return {"status": "OK", "active_alerts": len(active)}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _fleet_manager() -> dict:
    try:
        from backend.app.services.fleet_manager import FleetManager
        fm = FleetManager()
        return {"status": "OK"}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _observability_ledger() -> dict:
    try:
        from backend.app.services.execution_ledger import get_ledger
        ledger = get_ledger()
        recent = ledger.get_recent(limit=1)
        return {"status": "OK", "has_entries": len(recent) > 0}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


def _config_summary() -> dict:
    from backend.config import (
        SSH_REQUIRES_APPROVAL, SILVIA_SAFE_MODE,
        TELEGRAM_ENABLED, API_KEY,
        BRAIN_STEWARD_AUTODRAFT,
    )
    return {
        "SSH_REQUIRES_APPROVAL": SSH_REQUIRES_APPROVAL,
        "SILVIA_SAFE_MODE": SILVIA_SAFE_MODE,
        "TELEGRAM_ENABLED": TELEGRAM_ENABLED,
        "API_KEY_SET": bool(API_KEY),
        "BRAIN_STEWARD_AUTODRAFT": BRAIN_STEWARD_AUTODRAFT,
    }


async def run_full_diagnostics() -> dict[str, Any]:
    """Run all subsystem checks and return structured results."""
    started = time.time()

    results: dict[str, Any] = {}
    results["config"] = _config_summary()
    results["database"] = _db_ok()
    results["ollama"] = await _ollama_ok()
    results["node_registry"] = _node_registry()
    results["service_registry"] = _service_registry()
    results["capability_registry"] = _capability_registry()
    results["hardware_inventory"] = _hardware_inventory()
    results["hardware_projects"] = _hardware_projects()
    results["project_registry"] = _project_registry()
    results["gmail"] = _gmail_status()
    results["calendar"] = _calendar_status()
    results["telegram"] = _telegram_status()
    results["reminders"] = _reminder_status()
    results["tasks"] = _task_status()
    results["workflow_engine"] = _workflow_engine()
    results["approval_engine"] = _approval_engine()
    results["observability_ledger"] = _observability_ledger()
    results["knowledge_graph"] = _knowledge_graph()
    results["project_memory"] = _project_memory()
    results["digital_twin"] = _digital_twin()
    results["engineering_planner"] = _engineering_planner()
    results["brain63"] = _brain63_provider()
    results["memory_manager"] = _memory_manager()
    results["brain_steward"] = _brain_steward()
    results["workspace_awareness"] = _workspace_awareness()
    results["workspace_restore"] = _workspace_restore()
    results["ssh_profiles"] = _ssh_profiles()
    results["voice_pipeline"] = _voice_pipeline()
    results["watch_officer"] = _watch_officer()
    results["fleet_manager"] = _fleet_manager()

    elapsed = time.time() - started

    ok = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "OK")
    warn = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "WARNING")
    fail = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "FAILED")
    disabled = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "DISABLED")
    not_conf = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "NOT_CONFIGURED")

    results["_summary"] = {
        "ok": ok,
        "warning": warn,
        "failed": fail,
        "disabled": disabled,
        "not_configured": not_conf,
        "total_checked": ok + warn + fail + disabled + not_conf,
        "elapsed_ms": int(elapsed * 1000),
    }

    return results


def format_diagnostics(results: dict[str, Any]) -> str:
    """Render diagnostics as readable text."""
    lines = ["SILVIA System Diagnostics", "=" * 40, ""]

    summary = results.get("_summary", {})
    lines.append(f"OK: {summary.get('ok', 0)}  Warning: {summary.get('warning', 0)}  "
                 f"Failed: {summary.get('failed', 0)}  Disabled: {summary.get('disabled', 0)}  "
                 f"Not Configured: {summary.get('not_configured', 0)}")
    lines.append(f"Checked {summary.get('total_checked', 0)} subsystems in {summary.get('elapsed_ms', 0)}ms")
    lines.append("")

    config = results.get("config", {})
    if config:
        lines.append("Configuration")
        lines.append("-" * 30)
        for k, v in config.items():
            lines.append(f"  {k}: {v}")
        lines.append("")

    status_icons = {"OK": "+", "WARNING": "!", "FAILED": "X", "DISABLED": "-", "NOT_CONFIGURED": "?"}

    for key, val in results.items():
        if key.startswith("_") or key == "config":
            continue
        if not isinstance(val, dict) or "status" not in val:
            continue
        status = val["status"]
        icon = status_icons.get(status, "?")
        name = key.replace("_", " ").title()
        detail_parts = []
        for dk, dv in val.items():
            if dk == "status":
                continue
            if isinstance(dv, list) and len(dv) > 5:
                detail_parts.append(f"{dk}={len(dv)} items")
            else:
                detail_parts.append(f"{dk}={dv}")
        detail = ", ".join(detail_parts) if detail_parts else ""
        lines.append(f"[{icon}] {name}: {status}" + (f"  ({detail})" if detail else ""))

    return "\n".join(lines)
