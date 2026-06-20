"""Digital Twin Engine — Phase 15A.

Builds a live workspace state by aggregating all SILVIA subsystems:
projects, hardware (inventory/orders), nodes, services, knowledge graph,
engineering memory, tasks, calendar, observability, and productivity.

No simulation — pure aggregation of current real state.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger("silvia.digital_twin")

_PRIORITY_WEIGHT = {"critical": 4, "high": 3, "normal": 2, "low": 1}
_DONE_STATUSES = frozenset({"completed", "archived", "complete", "abandoned"})


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


def _days_since(iso: str | None) -> int | None:
    dt = _parse_iso(iso)
    if dt is None:
        return None
    return max(0, (_now() - dt).days)


def _fmt_date(iso: str | None) -> str:
    dt = _parse_iso(iso)
    return dt.astimezone().strftime("%b %d") if dt else "—"


class DigitalTwin:
    """Builds live workspace snapshots from all SILVIA subsystems."""

    def workspace_status(self) -> dict[str, Any]:
        """Top-level workspace state summary."""
        projects = self._all_projects()
        nodes = self._nodes()
        orders = self._open_orders()
        tasks = self._pending_tasks()
        alerts = self._active_alerts()
        activity = self._recent_activity(limit=20)

        active = [p for p in projects if p["status"] == "active"]
        blocked = [p for p in projects if p["blockers"]]
        ready = [p for p in projects if p["readiness_pct"] >= 80 and not p["blockers"]]
        online_nodes = [n for n in nodes if n.status == "online"]

        priorities = self._rank_projects(projects)
        top = priorities[0] if priorities else None

        return {
            "summary": {
                "total_projects": len(projects),
                "active": len(active),
                "blocked": len(blocked),
                "ready": len(ready),
                "nodes_online": len(online_nodes),
                "nodes_total": len(nodes),
                "open_orders": len(orders),
                "pending_tasks": len(tasks),
                "active_alerts": len(alerts),
                "recent_actions": len(activity),
            },
            "priority_project": {
                "name": top["name"],
                "score": top["score"],
                "recommended_action": top["recommended_action"],
            } if top else None,
            "blocked_projects": [
                {"name": p["name"], "blockers": [b["description"] for b in p["blockers"][:2]]}
                for p in blocked[:5]
            ],
            "ready_projects": [
                {"name": p["name"], "readiness_pct": p["readiness_pct"]}
                for p in ready[:5]
            ],
        }

    def project_states(self) -> list[dict[str, Any]]:
        """Full enriched state for every project."""
        return self._all_projects()

    def priorities(self) -> list[dict[str, Any]]:
        """Projects ranked by composite priority score."""
        projects = self._all_projects()
        return self._rank_projects(projects)

    def daily_briefing(self) -> dict[str, Any]:
        """Comprehensive engineering daily briefing."""
        now = _now()
        projects = self._all_projects()
        priorities = self._rank_projects(projects)
        nodes = self._nodes()
        orders = self._open_orders()
        tasks = self._pending_tasks()
        alerts = self._active_alerts()
        activity = self._recent_activity(limit=10)
        calendar = self._calendar_today()
        memories = self._recent_memories(days=7)

        active = [p for p in projects if p["status"] == "active"]
        blocked = [p for p in projects if p["blockers"]]
        ready = [p for p in projects if p["readiness_pct"] >= 80 and not p["blockers"]]
        online = [n for n in nodes if n.status == "online"]
        offline = [n for n in nodes if n.status == "offline"]

        top = priorities[0] if priorities else None

        return {
            "date": now.astimezone().strftime("%A, %B %d %Y"),
            "greeting": self._greeting(now),
            "workspace": {
                "projects": len(projects),
                "active": len(active),
                "blocked": len(blocked),
                "ready": len(ready),
            },
            "infrastructure": {
                "nodes_online": len(online),
                "nodes_offline": len(offline),
                "offline_names": [n.name for n in offline],
            },
            "top_priority": {
                "name": top["name"],
                "score": top["score"],
                "readiness_pct": top["readiness_pct"],
                "recommended_action": top["recommended_action"],
            } if top else None,
            "priorities": [
                {
                    "rank": i + 1,
                    "name": p["name"],
                    "score": p["score"],
                    "status": p["status"],
                    "readiness_pct": p["readiness_pct"],
                }
                for i, p in enumerate(priorities[:5])
            ],
            "blocked_projects": [
                {
                    "name": p["name"],
                    "blockers": [b["description"] for b in p["blockers"][:3]],
                }
                for p in blocked[:5]
            ],
            "pending_orders": [
                {"part_name": o.get("part_name", ""), "status": o.get("status", ""), "eta": o.get("eta", "")}
                for o in orders[:5]
            ],
            "pending_tasks": len(tasks),
            "high_priority_tasks": [
                {"title": t.title, "project": t.project}
                for t in tasks if t.priority == "high"
            ][:5],
            "calendar_today": [
                {"title": e.get("title", ""), "start": e.get("start", "")}
                for e in calendar[:5]
            ],
            "active_alerts": [
                {"message": a.message, "severity": a.severity}
                for a in alerts[:5]
            ],
            "recent_changes": [
                {"intent": a.get("intent", ""), "message": a.get("message", ""), "timestamp": a.get("timestamp", "")}
                for a in activity[:5]
            ],
            "recent_memories": [
                {"type": m["type"], "title": m["title"], "project": m["project"]}
                for m in memories[:5]
            ],
        }

    def blocked_projects(self) -> list[dict[str, Any]]:
        """All projects with blockers."""
        projects = self._all_projects()
        return [
            {
                "name": p["name"],
                "status": p["status"],
                "priority": p["priority"],
                "blockers": p["blockers"],
                "readiness_pct": p["readiness_pct"],
            }
            for p in projects if p["blockers"]
        ]

    def ready_projects(self) -> list[dict[str, Any]]:
        """Projects with >=80% readiness and no blockers."""
        projects = self._all_projects()
        return [
            {
                "name": p["name"],
                "status": p["status"],
                "priority": p["priority"],
                "readiness_pct": p["readiness_pct"],
                "recommended_action": p["recommended_action"],
            }
            for p in projects
            if p["readiness_pct"] >= 80 and not p["blockers"] and p["status"] not in _DONE_STATUSES
        ]

    # ── Data aggregation ─────────────────────────────────────────────────────

    def _all_projects(self) -> list[dict]:
        """Build enriched state for every project by aggregating all subsystems."""
        from backend.app.services.project_service import ProjectService
        from backend.app.services.project_intelligence import ProjectIntelligence

        ps = ProjectService()
        pi = ProjectIntelligence()
        raw_projects = ps.list_projects()
        result = []

        for proj in raw_projects:
            if proj.status in _DONE_STATUSES:
                continue

            briefing = pi.get_briefing(proj.name)
            found = briefing.get("found", False)

            readiness_pct = briefing.get("readiness_pct", 0) if found else 0
            blockers = briefing.get("blockers", []) if found else []
            recommended = briefing.get("recommended_action", "") if found else ""
            parts = briefing.get("parts", {}) if found else {}
            orders = briefing.get("orders", []) if found else []
            tasks = briefing.get("tasks", {}) if found else {}
            deps = briefing.get("dependencies", []) if found else []
            memory = briefing.get("memory", {}) if found else {}

            idle_days = _days_since(proj.last_activity)

            result.append({
                "name": proj.name,
                "id": proj.id,
                "status": proj.status,
                "priority": proj.priority,
                "readiness_pct": readiness_pct,
                "blockers": blockers,
                "recommended_action": recommended,
                "parts_total": parts.get("total", 0),
                "parts_available": parts.get("available", 0),
                "missing_parts": [p["name"] for p in parts.get("missing", [])],
                "pending_orders": len(orders),
                "open_tasks": tasks.get("open", 0),
                "dependencies": deps,
                "idle_days": idle_days,
                "last_activity": _fmt_date(proj.last_activity),
                "memory": {
                    "decisions": len(memory.get("decisions", [])),
                    "lessons": len(memory.get("lessons", [])),
                    "milestones": len(memory.get("milestones", [])),
                    "risks": len(memory.get("risks", [])),
                    "failures": len(memory.get("failures", [])),
                },
                "notes": proj.notes or "",
            })

        return result

    def _rank_projects(self, projects: list[dict]) -> list[dict]:
        """Score and rank projects by composite priority."""
        scored = []
        for p in projects:
            if p["status"] in _DONE_STATUSES:
                continue
            score = self._compute_score(p)
            scored.append({**p, "score": score})
        scored.sort(key=lambda x: -x["score"])
        return scored

    def _compute_score(self, p: dict) -> int:
        """Composite priority score (higher = work on this first).

        Factors:
        - Priority weight (critical=4, high=3, normal=2, low=1) × 20
        - Readiness (0-100 scaled to 0-30)
        - No blockers bonus (+15)
        - Active status bonus (+10)
        - Recent activity bonus (active in last 3 days: +10)
        - Has open tasks bonus (+5)
        - Penalize idle projects (-5 per 7 days idle, capped at -20)
        """
        score = _PRIORITY_WEIGHT.get(p["priority"], 2) * 20
        score += int(p["readiness_pct"] * 0.3)
        if not p["blockers"]:
            score += 15
        if p["status"] == "active":
            score += 10
        idle = p.get("idle_days")
        if idle is not None:
            if idle <= 3:
                score += 10
            else:
                score -= min(20, (idle // 7) * 5)
        if p.get("open_tasks", 0) > 0:
            score += 5
        if p["status"] == "blocked":
            score -= 15
        return max(0, score)

    def _nodes(self):
        from backend.app.services.node_service import NodeService
        return NodeService().list_nodes()

    def _open_orders(self) -> list[dict]:
        try:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            return [o for o in hs.list_orders() if o.get("status") not in ("delivered", "cancelled")]
        except Exception:
            return []

    def _pending_tasks(self):
        from backend.app.services.task_service import TaskService
        return TaskService().list_tasks(status="pending")

    def _active_alerts(self):
        from backend.app.services.watch_service import WatchService
        return WatchService().list_alerts(include_dismissed=False)

    def _recent_activity(self, limit: int = 20) -> list[dict]:
        try:
            from backend.app.services.execution_ledger import get_ledger
            return get_ledger().get_recent(limit=limit, since_hours=24)
        except Exception:
            return []

    def _calendar_today(self) -> list[dict]:
        try:
            from backend.app.tools.productivity_tool import list_gcal_events
            result = list_gcal_events(date="today", days=1)
            if result.get("ok"):
                return result.get("data", {}).get("events", [])
        except Exception:
            pass
        return []

    def _recent_memories(self, days: int = 7) -> list[dict]:
        try:
            from backend.app.services.project_memory import get_memory
            return get_memory().get_recent(days=days, limit=10)
        except Exception:
            return []

    def _greeting(self, now: datetime) -> str:
        hour = now.astimezone().hour
        if hour < 12:
            return "Good morning."
        elif hour < 17:
            return "Good afternoon."
        else:
            return "Good evening."


_instance: Optional[DigitalTwin] = None


def get_twin() -> DigitalTwin:
    global _instance
    if _instance is None:
        _instance = DigitalTwin()
    return _instance
