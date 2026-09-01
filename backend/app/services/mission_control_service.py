"""Mission Control Service — aggregates all data sources into an operational picture.

All output is grounded in real data from Brain63, Projects, Tasks, Reminders,
Calendar, Watch Officer, and Node Registry. Nothing is fabricated.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


_PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}
_STALE_DAYS = 14      # project considered stale if no activity in 14 days
_FORGOTTEN_TASK_DAYS = 7   # pending task older than 7 days is potentially forgotten


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _days_ago(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return (_now() - dt).days


def _fmt_date(iso: str | None) -> str:
    if not iso:
        return "unknown"
    dt = _parse_iso(iso)
    if not dt:
        return iso
    local = dt.astimezone()
    return local.strftime("%b %d")


def _fmt_datetime(iso: str | None) -> str:
    if not iso:
        return "unknown"
    dt = _parse_iso(iso)
    if not dt:
        return iso
    local = dt.astimezone()
    return local.strftime("%b %d %H:%M")


class MissionControlService:
    """Aggregates all platform data for mission-level situational awareness."""

    def __init__(self) -> None:
        # Services are instantiated lazily per-call to avoid startup coupling
        pass

    # ── Internal data pullers ──────────────────────────────────────────────────

    def _projects(self):
        from backend.app.services.project_service import ProjectService
        return ProjectService().list_projects()

    def _pending_tasks(self):
        from backend.app.services.task_service import TaskService
        return TaskService().list_tasks(status="pending")

    def _completed_tasks_since(self, days: int = 7):
        from backend.app.services.task_service import TaskService
        cutoff = (_now() - timedelta(days=days)).isoformat()
        tasks = TaskService().list_tasks(status="all")
        return [t for t in tasks if t.status == "completed" and t.completed_at and t.completed_at >= cutoff]

    def _reminders(self):
        from backend.app.services.reminder_service import ReminderService
        return ReminderService().list_reminders(include_completed=False)

    def _due_reminders(self):
        from backend.app.services.reminder_service import ReminderService
        return ReminderService().get_due_reminders()

    def _calendar_today(self):
        from backend.app.services.calendar_service import CalendarService
        return CalendarService().get_today()

    def _calendar_week(self):
        from backend.app.services.calendar_service import CalendarService
        return CalendarService().get_upcoming(days=7)

    def _watch_alerts(self):
        from backend.app.services.watch_service import WatchService
        return WatchService().list_alerts(include_dismissed=False)

    def _nodes(self):
        from backend.app.services.node_service import NodeService
        return NodeService().list_nodes()

    def _brain63_for_project(self, brain63_key: str | None) -> list[dict]:
        if not brain63_key:
            return []
        try:
            from backend.app.services.brain63_service import Brain63Service
            from backend.config import BRAIN63_VAULT_PATH
            svc = Brain63Service(vault_path=BRAIN63_VAULT_PATH)
            results = svc.search(brain63_key, top_k=3)
            return results
        except Exception:
            return []

    # ── Briefing ───────────────────────────────────────────────────────────────

    def briefing(self) -> dict[str, Any]:
        """Full morning briefing — current operational picture."""
        now = _now()
        projects = self._projects()
        tasks = self._pending_tasks()
        due_reminders = self._due_reminders()
        events_today = self._calendar_today()
        alerts = self._watch_alerts()
        nodes = self._nodes()

        active_projects = [p for p in projects if p.status == "active"]
        blocked_projects = [p for p in projects if p.status == "blocked"]
        critical_tasks = [t for t in tasks if t.priority == "high"]
        offline_nodes = [n for n in nodes if n.status == "offline"]
        critical_alerts = [a for a in alerts if a.severity in ("critical", "warning")]

        return {
            "date": now.astimezone().strftime("%A, %B %d %Y"),
            "active_projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "priority": p.priority,
                    "status": p.status,
                    "last_activity": _fmt_date(p.last_activity),
                    "notes": p.notes or "",
                }
                for p in sorted(active_projects, key=lambda p: _PRIORITY_ORDER.get(p.priority, 2))
            ],
            "blocked_projects": [{"id": p.id, "name": p.name, "notes": p.notes or ""} for p in blocked_projects],
            "pending_tasks_count": len(tasks),
            "high_priority_tasks": [
                {"id": t.id, "title": t.title, "project": t.project}
                for t in critical_tasks
            ],
            "due_reminders": [
                {"id": r.id, "message": r.message, "trigger_at": _fmt_datetime(r.trigger_at)}
                for r in due_reminders
            ],
            "events_today": [
                {"title": e.title, "start_at": _fmt_datetime(e.start_at), "location": e.location}
                for e in events_today
            ],
            "active_alerts": [
                {"message": a.message, "severity": a.severity, "category": a.category}
                for a in critical_alerts[:5]
            ],
            "offline_nodes": [{"id": n.id, "name": n.name} for n in offline_nodes],
        }

    # ── Daily Focus ────────────────────────────────────────────────────────────

    def daily_focus(self) -> dict[str, Any]:
        """Priority-ranked work recommendations from real data."""
        now = _now()
        projects = self._projects()
        tasks = self._pending_tasks()
        due_reminders = self._due_reminders()
        alerts = self._watch_alerts()
        nodes = self._nodes()

        items: list[dict] = []

        # Tier 1: Critical watch alerts
        for a in alerts:
            if a.severity == "critical":
                items.append({"priority": 0, "source": "watch_officer", "item": a.message, "action": "Investigate alert"})

        # Tier 2: Overdue reminders
        for r in due_reminders:
            items.append({"priority": 1, "source": "reminder", "item": r.message, "action": "Due now"})

        # Tier 3: High priority tasks
        high_tasks = [t for t in tasks if t.priority == "high"]
        for t in high_tasks:
            proj = f" [{t.project}]" if t.project else ""
            items.append({"priority": 2, "source": "task", "item": f"{t.title}{proj}", "action": "Complete"})

        # Tier 4: Active critical/high projects with no recent activity
        for p in sorted(projects, key=lambda x: _PRIORITY_ORDER.get(x.priority, 2)):
            if p.status not in ("active", "blocked"):
                continue
            days_idle = _days_ago(_parse_iso(p.last_activity))
            if days_idle is None or days_idle >= 3:
                tier = 3 if p.priority in ("critical", "high") else 4
                idle_str = f"{days_idle}d idle" if days_idle is not None else "no activity logged"
                items.append({"priority": tier, "source": "project", "item": p.name, "action": f"Continue — {idle_str}"})

        # Tier 5: Offline nodes that might need attention
        offline = [n for n in nodes if n.status == "offline"]
        for n in offline:
            items.append({"priority": 5, "source": "infrastructure", "item": f"{n.name} is offline", "action": "Investigate"})

        # Tier 6: Normal priority tasks
        normal_tasks = [t for t in tasks if t.priority != "high"]
        for t in normal_tasks[:3]:
            proj = f" [{t.project}]" if t.project else ""
            items.append({"priority": 6, "source": "task", "item": f"{t.title}{proj}", "action": "Complete"})

        items.sort(key=lambda x: x["priority"])

        return {
            "date": now.astimezone().strftime("%A, %B %d"),
            "items": items[:10],  # top 10 only
            "total_pending_tasks": len(tasks),
            "total_due_reminders": len(due_reminders),
            "active_project_count": len([p for p in projects if p.status == "active"]),
        }

    # ── Weekly Review ──────────────────────────────────────────────────────────

    def weekly_review(self) -> dict[str, Any]:
        """Summary of the past 7 days and upcoming 7 days."""
        now = _now()
        week_ago = now - timedelta(days=7)

        projects = self._projects()
        pending_tasks = self._pending_tasks()
        completed_tasks = self._completed_tasks_since(days=7)
        upcoming_events = self._calendar_week()
        alerts = self._watch_alerts()
        reminders = self._reminders()

        # Projects that had activity this week
        active_this_week = [
            p for p in projects
            if p.last_activity and _parse_iso(p.last_activity) and _parse_iso(p.last_activity) >= week_ago
        ]

        # Upcoming reminders in next 7 days
        upcoming_reminders = [
            r for r in reminders
            if _parse_iso(r.trigger_at) and _parse_iso(r.trigger_at) >= now
        ]

        return {
            "period": f"{week_ago.astimezone().strftime('%b %d')} — {now.astimezone().strftime('%b %d %Y')}",
            "completed_tasks": [
                {"title": t.title, "project": t.project, "completed_at": _fmt_date(t.completed_at)}
                for t in completed_tasks
            ],
            "active_projects_this_week": [
                {"name": p.name, "status": p.status, "priority": p.priority}
                for p in active_this_week
            ],
            "all_active_projects": [
                {"name": p.name, "status": p.status, "priority": p.priority}
                for p in projects if p.status == "active"
            ],
            "pending_tasks_count": len(pending_tasks),
            "upcoming_events": [
                {"title": e.title, "start_at": _fmt_datetime(e.start_at)}
                for e in upcoming_events
            ],
            "upcoming_reminders": [
                {"message": r.message, "trigger_at": _fmt_datetime(r.trigger_at)}
                for r in sorted(upcoming_reminders, key=lambda r: r.trigger_at)[:5]
            ],
            "active_alerts_count": len(alerts),
            "critical_alerts": [
                {"message": a.message, "severity": a.severity}
                for a in alerts if a.severity in ("critical", "warning")
            ],
        }

    # ── Forgotten Items ────────────────────────────────────────────────────────

    def forgotten_items(self) -> dict[str, Any]:
        """Find things that have been dropped or ignored."""
        now = _now()
        projects = self._projects()
        tasks = self._pending_tasks()
        due_reminders = self._due_reminders()
        alerts = self._watch_alerts()

        # Stale projects
        stale_projects = []
        for p in projects:
            if p.status not in ("active", "blocked"):
                continue
            days = _days_ago(_parse_iso(p.last_activity))
            if days is None or days >= _STALE_DAYS:
                stale_projects.append({
                    "name": p.name,
                    "status": p.status,
                    "idle_days": days,
                    "last_activity": _fmt_date(p.last_activity),
                })

        # Long-pending tasks
        forgotten_tasks = []
        cutoff = (now - timedelta(days=_FORGOTTEN_TASK_DAYS)).isoformat()
        for t in tasks:
            if t.created_at < cutoff:
                age = _days_ago(_parse_iso(t.created_at))
                proj = f" [{t.project}]" if t.project else ""
                forgotten_tasks.append({
                    "title": f"{t.title}{proj}",
                    "age_days": age,
                    "priority": t.priority,
                })

        # Overdue reminders (already firing, not acted on)
        overdue_reminders = [
            {
                "message": r.message,
                "overdue_since": _fmt_datetime(r.trigger_at),
                "overdue_days": _days_ago(_parse_iso(r.trigger_at)),
            }
            for r in due_reminders
        ]

        # Old unresolved critical/warning alerts
        old_alerts = []
        for a in alerts:
            if a.severity not in ("critical", "warning"):
                continue
            age = _days_ago(_parse_iso(a.created_at))
            if age and age >= 1:
                old_alerts.append({
                    "message": a.message,
                    "severity": a.severity,
                    "age_days": age,
                })

        return {
            "stale_projects": stale_projects,
            "forgotten_tasks": sorted(forgotten_tasks, key=lambda x: -(x["age_days"] or 0)),
            "overdue_reminders": overdue_reminders,
            "old_unresolved_alerts": old_alerts,
            "has_anything": bool(stale_projects or forgotten_tasks or overdue_reminders or old_alerts),
        }

    # ── Evening Review ─────────────────────────────────────────────────────────

    def evening_review(self) -> dict[str, Any]:
        """End-of-day review: what happened today, what's outstanding."""
        now = _now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        projects = self._projects()
        all_tasks = self._completed_tasks_since(days=1)
        pending_tasks = self._pending_tasks()
        due_reminders = self._due_reminders()
        alerts = self._watch_alerts()
        nodes = self._nodes()

        # Tasks completed today
        completed_today = [t for t in all_tasks if t.completed_at and t.completed_at >= today_start]

        # Alerts generated today
        alerts_today = [
            a for a in alerts
            if a.created_at and a.created_at >= today_start
        ]

        # Projects with activity today (last_activity >= today_start)
        active_today = [
            p for p in projects
            if p.last_activity and p.last_activity >= today_start
        ]

        # Outstanding: pending tasks + overdue reminders
        high_pending = [t for t in pending_tasks if t.priority == "high"]
        offline_nodes = [n for n in nodes if n.status == "offline"]

        # Escalated reminders (those that are significantly overdue)
        from datetime import timedelta
        escalated_reminders = [
            r for r in due_reminders
            if _parse_iso(r.trigger_at) and (_now() - _parse_iso(r.trigger_at)).total_seconds() > 3600
        ]

        return {
            "date": now.astimezone().strftime("%A, %B %d %Y"),
            "completed_tasks_today": [
                {"title": t.title, "project": t.project, "priority": t.priority}
                for t in completed_today
            ],
            "projects_active_today": [
                {"name": p.name, "status": p.status, "priority": p.priority}
                for p in active_today
            ],
            "alerts_today": [
                {"message": a.message, "severity": a.severity, "category": a.category}
                for a in alerts_today[:10]
            ],
            "outstanding": {
                "pending_tasks": len(pending_tasks),
                "high_priority_tasks": [{"title": t.title, "project": t.project} for t in high_pending],
                "overdue_reminders": [
                    {"message": r.message, "overdue_since": _fmt_datetime(r.trigger_at)}
                    for r in escalated_reminders
                ],
                "offline_nodes": [{"name": n.name, "id": n.id} for n in offline_nodes],
            },
            "totals": {
                "tasks_completed": len(completed_today),
                "alerts_generated": len(alerts_today),
                "projects_touched": len(active_today),
            },
        }

    # ── Project Health ─────────────────────────────────────────────────────────

    def project_health(self) -> list[dict[str, Any]]:
        """Per-project health summary with tasks, reminders, and alerts."""
        projects = self._projects()
        tasks = self._pending_tasks()
        reminders = self._reminders()
        alerts = self._watch_alerts()

        # Index tasks by project name (case-insensitive)
        tasks_by_project: dict[str, list] = {}
        for t in tasks:
            key = (t.project or "").lower()
            tasks_by_project.setdefault(key, []).append(t)

        # Index reminders by keyword match (no formal link exists)
        # We use project name as a keyword scan
        results = []
        for p in sorted(projects, key=lambda x: _PRIORITY_ORDER.get(x.priority, 2)):
            proj_key = p.name.lower()
            proj_tasks = tasks_by_project.get(proj_key, [])
            # Also check by project id
            proj_tasks = proj_tasks or tasks_by_project.get(p.id.lower(), [])

            # Reminders mentioning project name
            proj_reminders = [r for r in reminders if proj_key in r.message.lower()]

            # Alerts mentioning project name
            proj_alerts = [a for a in alerts if proj_key in a.message.lower()]

            days_idle = _days_ago(_parse_iso(p.last_activity))
            health = "healthy"
            if p.status == "blocked":
                health = "blocked"
            elif days_idle is not None and days_idle >= _STALE_DAYS:
                health = "stale"
            elif days_idle is None:
                health = "no activity"

            results.append({
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "priority": p.priority,
                "health": health,
                "last_activity": _fmt_date(p.last_activity),
                "idle_days": days_idle,
                "pending_tasks": len(proj_tasks),
                "task_titles": [t.title for t in proj_tasks[:3]],
                "pending_reminders": len(proj_reminders),
                "active_alerts": len(proj_alerts),
                "notes": p.notes or "",
                "brain63_key": p.brain63_key,
            })

        return results
