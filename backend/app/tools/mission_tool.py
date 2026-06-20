"""Mission Control tool — aggregates all platform data for SILVIA briefings."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _svc():
    from backend.app.services.mission_control_service import MissionControlService
    return MissionControlService()


def _make_result(ok: bool, tool: str, summary: str, data: dict, error: str = "") -> dict:
    return {"ok": ok, "tool": tool, "summary": summary, "data": data, "error": error}


def morning_briefing() -> dict:
    try:
        data = _svc().briefing()
        active = len(data["active_projects"])
        tasks = data["pending_tasks_count"]
        reminders = len(data["due_reminders"])
        alerts = len(data["active_alerts"])
        parts = []
        if active:
            parts.append(f"{active} active project{'s' if active != 1 else ''}")
        if tasks:
            parts.append(f"{tasks} pending task{'s' if tasks != 1 else ''}")
        if reminders:
            parts.append(f"{reminders} reminder{'s' if reminders != 1 else ''} due")
        if alerts:
            parts.append(f"{alerts} alert{'s' if alerts != 1 else ''}")
        summary = f"Briefing ready: {', '.join(parts) or 'all clear'}."
        return _make_result(True, "morning_briefing", summary, data)
    except Exception as exc:
        logger.exception("morning_briefing failed")
        return _make_result(False, "morning_briefing", f"Briefing unavailable: {exc}", {}, str(exc))


def daily_focus() -> dict:
    try:
        data = _svc().daily_focus()
        count = len(data["items"])
        summary = f"Found {count} prioritised item{'s' if count != 1 else ''} for today."
        return _make_result(True, "daily_focus", summary, data)
    except Exception as exc:
        logger.exception("daily_focus failed")
        return _make_result(False, "daily_focus", f"Focus unavailable: {exc}", {}, str(exc))


def weekly_review() -> dict:
    try:
        data = _svc().weekly_review()
        completed = len(data["completed_tasks"])
        summary = f"Weekly review ready: {completed} task{'s' if completed != 1 else ''} completed this week."
        return _make_result(True, "weekly_review", summary, data)
    except Exception as exc:
        logger.exception("weekly_review failed")
        return _make_result(False, "weekly_review", f"Weekly review unavailable: {exc}", {}, str(exc))


def forgotten_items() -> dict:
    try:
        data = _svc().forgotten_items()
        total = (
            len(data["stale_projects"])
            + len(data["forgotten_tasks"])
            + len(data["overdue_reminders"])
            + len(data["old_unresolved_alerts"])
        )
        summary = f"Found {total} forgotten or overdue item{'s' if total != 1 else ''}." if total else "Nothing appears to be forgotten."
        return _make_result(True, "forgotten_items", summary, data)
    except Exception as exc:
        logger.exception("forgotten_items failed")
        return _make_result(False, "forgotten_items", f"Scan unavailable: {exc}", {}, str(exc))


def project_health() -> dict:
    try:
        projects = _svc().project_health()
        summary = f"Project health report: {len(projects)} project{'s' if len(projects) != 1 else ''}."
        return _make_result(True, "project_health", summary, {"projects": projects})
    except Exception as exc:
        logger.exception("project_health failed")
        return _make_result(False, "project_health", f"Health check unavailable: {exc}", {}, str(exc))


def evening_review() -> dict:
    try:
        data = _svc().evening_review()
        totals = data.get("totals", {})
        parts = []
        done = totals.get("tasks_completed", 0)
        if done:
            parts.append(f"{done} task{'s' if done != 1 else ''} completed")
        touched = totals.get("projects_touched", 0)
        if touched:
            parts.append(f"{touched} project{'s' if touched != 1 else ''} active today")
        gen = totals.get("alerts_generated", 0)
        if gen:
            parts.append(f"{gen} alert{'s' if gen != 1 else ''} generated")
        summary = f"Evening review: {', '.join(parts) or 'quiet day'}."
        return _make_result(True, "evening_review", summary, data)
    except Exception as exc:
        logger.exception("evening_review failed")
        return _make_result(False, "evening_review", f"Evening review unavailable: {exc}", {}, str(exc))


def list_projects(status: str = "") -> dict:
    try:
        from backend.app.services.project_service import ProjectService
        svc = ProjectService()
        projects = svc.list_projects(status=status if status else None)
        summary = f"{len(projects)} project{'s' if len(projects) != 1 else ''} found."
        return _make_result(True, "list_projects", summary, {
            "projects": [p.model_dump() for p in projects]
        })
    except Exception as exc:
        logger.exception("list_projects failed")
        return _make_result(False, "list_projects", f"Could not list projects: {exc}", {}, str(exc))


def create_project(name: str, status: str = "active", priority: str = "normal",
                   brain63_key: str = "", notes: str = "") -> dict:
    try:
        from backend.app.services.project_service import ProjectService, ProjectCreate
        data = ProjectCreate(
            name=name, status=status, priority=priority,
            brain63_key=brain63_key or None, notes=notes or None,
        )
        project = ProjectService().create_project(data)
        return _make_result(True, "create_project", f"Project '{name}' created.", {"project": project.model_dump()})
    except Exception as exc:
        logger.exception("create_project failed")
        return _make_result(False, "create_project", f"Failed to create project: {exc}", {}, str(exc))


def update_project_status(name: str, status: str) -> dict:
    try:
        from backend.app.services.project_service import ProjectService, ProjectUpdate
        svc = ProjectService()
        project = svc.find_by_name(name)
        if not project:
            return _make_result(False, "update_project_status", f"Project '{name}' not found.", {})
        updated = svc.update_project(project.id, ProjectUpdate(status=status))
        return _make_result(True, "update_project_status", f"Project '{name}' set to {status}.", {"project": updated.model_dump() if updated else {}})
    except Exception as exc:
        logger.exception("update_project_status failed")
        return _make_result(False, "update_project_status", f"Update failed: {exc}", {}, str(exc))
