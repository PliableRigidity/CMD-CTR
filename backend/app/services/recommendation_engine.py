"""Recommendation Engine — Phase 15A.

Deterministic recommendations computed from live workspace state.
No LLM calls — pure data aggregation and scoring.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("silvia.recommendations")


class RecommendationEngine:
    """Generates workspace-aware recommendations from digital twin state."""

    def what_should_i_work_on(self) -> dict[str, Any]:
        """Recommend the best project to work on right now."""
        from backend.app.services.digital_twin import get_twin
        twin = get_twin()
        priorities = twin.priorities()

        if not priorities:
            return {
                "ok": True,
                "recommendation": None,
                "summary": "No active projects found.",
                "alternatives": [],
            }

        top = priorities[0]

        reasons = self._build_reasons(top)
        tasks = self._suggested_tasks(top["name"])

        return {
            "ok": True,
            "recommendation": {
                "project": top["name"],
                "score": top["score"],
                "readiness_pct": top["readiness_pct"],
                "status": top["status"],
                "reasons": reasons,
                "suggested_tasks": tasks,
                "recommended_action": top.get("recommended_action", ""),
            },
            "alternatives": [
                {
                    "project": p["name"],
                    "score": p["score"],
                    "readiness_pct": p["readiness_pct"],
                    "status": p["status"],
                }
                for p in priorities[1:4]
            ],
            "summary": f"Recommended: {top['name']} (score {top['score']}, {top['readiness_pct']}% ready)",
        }

    def closest_to_completion(self) -> dict[str, Any]:
        """Which project is nearest to being done (highest readiness, fewest blockers)."""
        from backend.app.services.digital_twin import get_twin
        projects = get_twin().project_states()

        candidates = [
            p for p in projects
            if p["status"] not in ("blocked", "paused", "completed", "archived")
            and p["readiness_pct"] > 0
        ]
        if not candidates:
            return {"ok": True, "project": None, "summary": "No projects with readiness data."}

        candidates.sort(key=lambda p: (-p["readiness_pct"], len(p["blockers"])))
        top = candidates[0]
        return {
            "ok": True,
            "project": {
                "name": top["name"],
                "readiness_pct": top["readiness_pct"],
                "blockers": top["blockers"],
                "missing_parts": top["missing_parts"],
            },
            "summary": f"{top['name']} is closest to completion at {top['readiness_pct']}% readiness.",
        }

    def what_to_order(self) -> dict[str, Any]:
        """Parts that should be ordered — missing parts with no active order."""
        try:
            from backend.app.services.project_intelligence import ProjectIntelligence
            pi = ProjectIntelligence()
            needs = pi.get_projects_needing_orders()
            if not needs:
                return {"ok": True, "orders": [], "summary": "All missing parts have active orders or no parts are missing."}

            items = []
            for p in needs:
                for part in p["unordered_parts"]:
                    items.append({"project": p["name"], "part": part, "priority": p["priority"]})

            items.sort(key=lambda x: {"critical": 0, "high": 1, "normal": 2, "low": 3}.get(x["priority"], 2))
            return {
                "ok": True,
                "orders": items,
                "summary": f"{len(items)} part(s) across {len(needs)} project(s) need ordering.",
            }
        except Exception as e:
            return {"ok": False, "orders": [], "summary": f"Error: {e}"}

    def what_can_i_build(self) -> dict[str, Any]:
        """Projects that have all parts available and can start immediately."""
        from backend.app.services.digital_twin import get_twin
        ready = get_twin().ready_projects()
        if not ready:
            return {"ok": True, "projects": [], "summary": "No projects are fully ready to build right now."}
        return {
            "ok": True,
            "projects": ready,
            "summary": f"{len(ready)} project(s) ready to build now: {', '.join(p['name'] for p in ready)}.",
        }

    def _build_reasons(self, project: dict) -> list[str]:
        reasons = []
        if not project.get("blockers"):
            reasons.append("No current blockers")
        if project.get("readiness_pct", 0) >= 80:
            reasons.append(f"Parts {project['readiness_pct']}% available")
        elif project.get("readiness_pct", 0) > 0:
            reasons.append(f"Readiness at {project['readiness_pct']}%")
        if project.get("priority") in ("critical", "high"):
            reasons.append(f"{project['priority'].title()} priority project")
        idle = project.get("idle_days")
        if idle is not None and idle <= 3:
            reasons.append("Recently active")
        if project.get("open_tasks", 0) > 0:
            reasons.append(f"{project['open_tasks']} open task(s)")
        if project.get("status") == "active":
            reasons.append("Active status")
        mem = project.get("memory", {})
        if mem.get("milestones", 0) > 0:
            reasons.append("Has recorded milestones")
        return reasons or ["Highest composite score"]

    def _suggested_tasks(self, project_name: str) -> list[str]:
        try:
            from backend.app.services.task_service import TaskService
            tasks = TaskService().list_tasks(status="pending")
            return [
                t.title for t in tasks
                if t.project and t.project.lower() == project_name.lower()
            ][:5]
        except Exception:
            return []


_instance: RecommendationEngine | None = None


def get_engine() -> RecommendationEngine:
    global _instance
    if _instance is None:
        _instance = RecommendationEngine()
    return _instance
