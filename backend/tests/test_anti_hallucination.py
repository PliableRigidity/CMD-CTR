"""
Anti-hallucination test suite (Rule 12).

All tests are deterministic — they target render functions and the data-fence
layer, NOT the LLM. A test fails if fabricated content can appear in output
even when the input data is empty or absent.

Run with:  python -m pytest backend/tests/test_anti_hallucination.py -v
"""

import sys
import os
import types
import unittest

# ---------------------------------------------------------------------------
# Minimal import shim — ConversationService has many async deps we don't need
# for testing pure render methods. We import only the class and patch the
# parts that require live services.
# ---------------------------------------------------------------------------
# Ensure repo root is on the path when running from any CWD.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _make_service():
    """Return an instance of ConversationService with all I/O deps stubbed."""
    # Stub every external module that would fail on import in a test context.
    _STUBS = [
        "anthropic", "openai", "aiohttp", "fastapi", "starlette",
        "backend.app.services.voice_service",
        "backend.app.services.brain63_service",
        "backend.app.services.event_service",
        "backend.app.services.node_service",
        "backend.app.services.hermes_service",
        "backend.app.services.mission_service",
        "backend.app.services.action_service",
        "backend.app.services.web_service",
        "backend.app.services.decision_service",
        "backend.app.services.conversation_state",
        "backend.app.services.persona",
        "backend.app.tools.node_tool",
        "backend.app.tools.planner",
        "backend.app.tools.time_tool",
        "backend.config",
    ]
    for name in _STUBS:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)

    # Provide minimal config attributes that the module reads at import time.
    cfg = sys.modules["backend.config"]
    for attr in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENWEATHER_API_KEY",
                 "ANTHROPIC_MODEL", "OPENAI_STT_MODEL", "OPENAI_TTS_VOICE",
                 "API_KEY", "NOTIFICATION_WEBHOOK_URL"):
        if not hasattr(cfg, attr):
            setattr(cfg, attr, "")

    from backend.app.services.conversation_service import ConversationService  # noqa: PLC0415

    # Instantiate with all-None deps — we only call synchronous render methods.
    svc = ConversationService.__new__(ConversationService)
    return svc


# Lazy singleton so the import shim runs once.
_SVC = None


def _svc():
    global _SVC
    if _SVC is None:
        _SVC = _make_service()
    return _SVC


# ---------------------------------------------------------------------------
# Helper phrases that MUST NOT appear in any output when data is absent.
# These are hallucination markers — words an LLM would invent when guessing.
# ---------------------------------------------------------------------------
_HALLUCINATION_PHRASES = [
    "it appears",
    "likely",
    "probably",
    "typically",
    "usually",
    "seems to be",
    "may be",
    "might be",
    "should be",
    "could be",
    "based on",
    "as expected",
    "in progress",          # must not appear unless data says so
    "recently",             # temporal fabrication
    "a few",                # quantity fabrication
    "several",              # quantity fabrication
]


def _assert_no_hallucination(text: str, test_name: str):
    """Fail if any hallucination marker appears in the output text."""
    low = text.lower()
    found = [p for p in _HALLUCINATION_PHRASES if p in low]
    if found:
        raise AssertionError(
            f"[{test_name}] Hallucination markers in output: {found}\n"
            f"Output was:\n{text}"
        )


# ---------------------------------------------------------------------------
# _context_has_data
# ---------------------------------------------------------------------------
class TestContextHasData(unittest.TestCase):
    """Verify the empty-data short-circuit detector."""

    def setUp(self):
        from backend.app.services.conversation_service import ConversationService
        self._fn = ConversationService._context_has_data

    def test_empty_string(self):
        self.assertFalse(self._fn(""))

    def test_header_only(self):
        self.assertFalse(self._fn("OPERATIONAL BRIEFING — Today\n\nAll clear."))

    def test_bullet_item_detected(self):
        self.assertTrue(self._fn("PROJECTS:\n  • Alpha project [HIGH]"))

    def test_tick_item_detected(self):
        self.assertTrue(self._fn("COMPLETED:\n  ✓ Finished task"))

    def test_cross_item_detected(self):
        self.assertTrue(self._fn("  ✗ Failed item"))

    def test_tilde_item_detected(self):
        self.assertTrue(self._fn("  ~ Stale project"))

    def test_alert_item_detected(self):
        self.assertTrue(self._fn("[WARNING] CPU above threshold"))

    def test_critical_item_detected(self):
        self.assertTrue(self._fn("[CRITICAL] Disk full"))

    def test_numbered_priority_item_detected(self):
        self.assertTrue(self._fn("  1. [TASK] Fix the thing  — Do it now"))

    def test_whitespace_only(self):
        self.assertFalse(self._fn("   \n   \n  "))

    def test_all_clear_message_is_not_data(self):
        briefing = "OPERATIONAL BRIEFING — Today\n\nAll clear — no active items requiring attention."
        self.assertFalse(self._fn(briefing))


# ---------------------------------------------------------------------------
# _render_node_telemetry — empty / no-telemetry cases
# ---------------------------------------------------------------------------
class TestRenderNodeTelemetry(unittest.TestCase):

    def test_node_error_response(self):
        result = {"ok": False, "error": "Node not found."}
        out = _svc()._render_node_telemetry(result)
        self.assertIn("Node not found", out)
        _assert_no_hallucination(out, "telemetry_error")

    def test_node_error_fallback_message(self):
        result = {"ok": False}
        out = _svc()._render_node_telemetry(result)
        self.assertIn("No telemetry found", out)
        _assert_no_hallucination(out, "telemetry_fallback")

    def test_node_no_metrics(self):
        """A node that is online but has sent no telemetry must say so explicitly."""
        result = {
            "ok": True,
            "data": {
                "name": "testnode",
                "status": "online",
                "cpu": None,
                "ram": None,
                "disk": None,
                "temperature": None,
                "uptime": None,
                "agent_url": None,
            },
        }
        out = _svc()._render_node_telemetry(result)
        self.assertIn("No telemetry received yet", out)
        _assert_no_hallucination(out, "telemetry_no_metrics")

    def test_node_empty_registry(self):
        result = {"ok": True, "data": {"nodes": []}}
        out = _svc()._render_node_telemetry(result)
        self.assertIn("No nodes in registry", out)
        _assert_no_hallucination(out, "telemetry_empty_registry")

    def test_node_with_metrics_shows_values(self):
        result = {
            "ok": True,
            "data": {
                "name": "mynode",
                "status": "online",
                "cpu": 42.0,
                "ram": 67.0,
                "disk": None,
                "temperature": None,
                "uptime": 3661,
            },
        }
        out = _svc()._render_node_telemetry(result)
        self.assertIn("42%", out)
        self.assertIn("67%", out)
        # Disk not in data → must NOT appear
        self.assertNotIn("Disk:", out)


# ---------------------------------------------------------------------------
# _render_node_info — task with no details / notes
# ---------------------------------------------------------------------------
class TestRenderNodeInfo(unittest.TestCase):

    def test_node_not_found(self):
        result = {"ok": False, "error": "Node alpha not found."}
        out = _svc()._render_node_info(result)
        self.assertIn("not found", out.lower())
        _assert_no_hallucination(out, "node_info_not_found")

    def test_node_no_notes(self):
        # _render_node_info uses result["node"] for the display name and
        # result["data"] for probe/IP details; it doesn't render the notes
        # field itself — that's tested via _render_node_telemetry and the
        # full info view. We confirm the call succeeds and produces no
        # fabricated text given minimal real data.
        result = {
            "ok": True,
            "node": "mynode",
            "data": {
                "status": "online",
                "ip": "100.1.2.3",
                "ip_source": "tailscale",
                "latency_ms": 0.1,
                "probe_error": None,
            },
        }
        out = _svc()._render_node_info(result)
        self.assertIn("mynode", out)
        self.assertIn("online", out)
        _assert_no_hallucination(out, "node_info_no_notes")
        self.assertNotIn("configured", out.lower())
        self.assertNotIn("standard", out.lower())


# ---------------------------------------------------------------------------
# _render_briefing_for_llm — empty data produces "all clear", not fabrication
# ---------------------------------------------------------------------------
class TestRenderBriefingForLLM(unittest.TestCase):

    def test_all_empty_gives_all_clear(self):
        data = {
            "date": "2026-06-14",
            "active_projects": [],
            "blocked_projects": [],
            "high_priority_tasks": [],
            "pending_tasks_count": 0,
            "due_reminders": [],
            "events_today": [],
            "active_alerts": [],
            "offline_nodes": [],
        }
        out = _svc()._render_briefing_for_llm(data)
        self.assertIn("All clear", out)
        _assert_no_hallucination(out, "briefing_all_empty")

    def test_projects_appear_in_output(self):
        data = {
            "date": "2026-06-14",
            "active_projects": [
                {"name": "Alpha", "priority": "high", "last_activity": "unknown", "notes": None}
            ],
            "blocked_projects": [],
            "high_priority_tasks": [],
            "pending_tasks_count": 0,
            "due_reminders": [],
            "events_today": [],
            "active_alerts": [],
            "offline_nodes": [],
        }
        out = _svc()._render_briefing_for_llm(data)
        self.assertIn("Alpha", out)
        self.assertIn("ACTIVE PROJECTS", out)

    def test_no_active_projects_section_when_empty(self):
        data = {
            "date": "2026-06-14",
            "active_projects": [],
            "blocked_projects": [],
            "high_priority_tasks": [],
            "pending_tasks_count": 0,
            "due_reminders": [],
            "events_today": [],
            "active_alerts": [],
            "offline_nodes": [],
        }
        out = _svc()._render_briefing_for_llm(data)
        self.assertNotIn("ACTIVE PROJECTS", out)


# ---------------------------------------------------------------------------
# _render_evening_for_llm — completed tasks section is honest when empty
# ---------------------------------------------------------------------------
class TestRenderEveningForLLM(unittest.TestCase):

    def test_no_completed_tasks_says_none(self):
        data = {
            "date": "2026-06-14",
            "completed_tasks_today": [],
            "projects_active_today": [],
            "alerts_today": [],
            "totals": {},
            "outstanding": {"pending_tasks": 0, "high_priority_tasks": []},
        }
        out = _svc()._render_evening_for_llm(data)
        self.assertIn("No tasks marked done today", out)
        _assert_no_hallucination(out, "evening_no_completed")

    def test_completed_tasks_listed(self):
        data = {
            "date": "2026-06-14",
            "completed_tasks_today": [
                {"title": "Write report", "project": "Alpha"},
                {"title": "Deploy fix", "project": None},
            ],
            "projects_active_today": [],
            "alerts_today": [],
            "totals": {},
            "outstanding": {"pending_tasks": 0, "high_priority_tasks": []},
        }
        out = _svc()._render_evening_for_llm(data)
        self.assertIn("Write report", out)
        self.assertIn("Deploy fix", out)
        self.assertIn("[Alpha]", out)


# ---------------------------------------------------------------------------
# _render_weekly_for_llm — no activity means honest "None recorded"
# ---------------------------------------------------------------------------
class TestRenderWeeklyForLLM(unittest.TestCase):

    def test_no_completed_tasks(self):
        data = {
            "period": "2026-06-08 to 2026-06-14",
            "completed_tasks": [],
            "active_projects_this_week": [],
            "all_active_projects": [],
            "pending_tasks_count": 0,
            "upcoming_events": [],
            "upcoming_reminders": [],
            "critical_alerts": [],
            "active_alerts_count": 0,
        }
        out = _svc()._render_weekly_for_llm(data)
        self.assertIn("None recorded this week", out)
        _assert_no_hallucination(out, "weekly_no_activity")

    def test_projects_with_activity(self):
        data = {
            "period": "2026-06-08 to 2026-06-14",
            "completed_tasks": [],
            "active_projects_this_week": [{"name": "Beta", "priority": "medium"}],
            "all_active_projects": [],
            "pending_tasks_count": 0,
            "upcoming_events": [],
            "upcoming_reminders": [],
            "critical_alerts": [],
            "active_alerts_count": 0,
        }
        out = _svc()._render_weekly_for_llm(data)
        self.assertIn("Beta", out)
        self.assertIn("PROJECTS WITH ACTIVITY", out)


# ---------------------------------------------------------------------------
# _render_focus_for_llm — empty items list produces honest message
# ---------------------------------------------------------------------------
class TestRenderFocusForLLM(unittest.TestCase):

    def test_no_items(self):
        data = {
            "date": "2026-06-14",
            "items": [],
            "total_pending_tasks": 0,
            "total_due_reminders": 0,
            "active_project_count": 0,
        }
        out = _svc()._render_focus_for_llm(data)
        self.assertIn("No specific priorities identified", out)
        _assert_no_hallucination(out, "focus_empty")

    def test_items_appear(self):
        data = {
            "date": "2026-06-14",
            "items": [
                {"source": "task", "item": "Fix login bug", "action": "Complete today"},
            ],
            "total_pending_tasks": 1,
            "total_due_reminders": 0,
            "active_project_count": 0,
        }
        out = _svc()._render_focus_for_llm(data)
        self.assertIn("Fix login bug", out)
        self.assertIn("[TASK]", out)


# ---------------------------------------------------------------------------
# _render_project_health — empty project list
# ---------------------------------------------------------------------------
class TestRenderProjectHealth(unittest.TestCase):

    def test_empty_projects(self):
        out = _svc()._render_project_health([])
        self.assertIn("No projects found", out)
        _assert_no_hallucination(out, "project_health_empty")

    def test_project_appears(self):
        projects = [{
            "name": "Omega",
            "priority": "high",
            "status": "active",
            "health": "healthy",
            "last_activity": "2026-06-13",
            "idle_days": 1,
            "pending_tasks": 3,
            "active_alerts": 0,
            "task_titles": ["Fix bug", "Write docs"],
            "notes": None,
        }]
        out = _svc()._render_project_health(projects)
        self.assertIn("Omega", out)
        self.assertIn("✓", out)
        self.assertIn("3 pending tasks", out)

    def test_blocked_project_shows_cross(self):
        projects = [{
            "name": "Stuck",
            "priority": "low",
            "status": "blocked",
            "health": "blocked",
            "last_activity": "2026-05-01",
            "idle_days": 44,
            "pending_tasks": 0,
            "active_alerts": 1,
            "task_titles": [],
            "notes": "Waiting on vendor",
        }]
        out = _svc()._render_project_health(projects)
        self.assertIn("✗", out)
        self.assertIn("Waiting on vendor", out)


# ---------------------------------------------------------------------------
# _render_forgotten — clean slate vs. data-populated
# ---------------------------------------------------------------------------
class TestRenderForgotten(unittest.TestCase):

    def test_nothing_forgotten(self):
        data = {"has_anything": False}
        out = _svc()._render_forgotten(data)
        self.assertIn("Nothing appears to be forgotten", out)
        _assert_no_hallucination(out, "forgotten_clean")

    def test_stale_projects_listed(self):
        data = {
            "has_anything": True,
            "stale_projects": [
                {"name": "OldProj", "status": "active", "last_activity": "2026-04-01", "idle_days": 74}
            ],
            "forgotten_tasks": [],
            "overdue_reminders": [],
            "old_unresolved_alerts": [],
        }
        out = _svc()._render_forgotten(data)
        self.assertIn("OldProj", out)
        self.assertIn("74d", out)


# ---------------------------------------------------------------------------
# _render_watch_alerts — empty alert list
# ---------------------------------------------------------------------------
class TestRenderWatchAlerts(unittest.TestCase):

    def test_no_alerts(self):
        result = {"ok": True, "data": {"alerts": [], "total": 0}}
        out = _svc()._render_watch_alerts(result)
        self.assertNotIn("CPU", out)
        self.assertNotIn("Warning", out.title())
        _assert_no_hallucination(out, "watch_alerts_empty")

    def test_alert_appears(self):
        result = {
            "ok": True,
            "data": {
                "alerts": [
                    {
                        "severity": "warning",
                        "category": "infra",
                        "message": "CPU on carrera at 91%",
                        "node": "carrera",
                        "created_at": "2026-06-14T10:00:00",
                        "rule": "cpu_high",
                        "value": 91.0,
                        "threshold": 90.0,
                    }
                ],
                "total": 1,
            },
        }
        out = _svc()._render_watch_alerts(result)
        self.assertIn("carrera", out)
        self.assertIn("91", out)


# ---------------------------------------------------------------------------
# Fabrication boundary test: outputs must not contain values not in the input
# ---------------------------------------------------------------------------
class TestFabricationBoundary(unittest.TestCase):
    """Verify that render functions never output values not present in input data."""

    def test_telemetry_does_not_invent_cpu_value(self):
        """If cpu is None, the CPU line must not appear with any value."""
        result = {
            "ok": True,
            "data": {
                "name": "ghost",
                "status": "online",
                "cpu": None,
                "ram": 55.0,
                "disk": None,
                "temperature": None,
                "uptime": None,
            },
        }
        out = _svc()._render_node_telemetry(result)
        self.assertNotIn("CPU", out)
        self.assertIn("55%", out)  # RAM is present, must appear

    def test_briefing_does_not_invent_task_count(self):
        """If pending_tasks_count=0 and no tasks, no task count must appear."""
        data = {
            "date": "2026-06-14",
            "active_projects": [],
            "blocked_projects": [],
            "high_priority_tasks": [],
            "pending_tasks_count": 0,
            "due_reminders": [],
            "events_today": [],
            "active_alerts": [],
            "offline_nodes": [],
        }
        out = _svc()._render_briefing_for_llm(data)
        # Must not mention any task count since it's zero
        self.assertNotIn("tasks pending", out)
        self.assertNotIn("1 task", out)
        self.assertNotIn("2 task", out)

    def test_evening_does_not_invent_project_activity(self):
        """If projects_active_today=[], no project must appear in the output."""
        data = {
            "date": "2026-06-14",
            "completed_tasks_today": [],
            "projects_active_today": [],
            "alerts_today": [],
            "totals": {},
            "outstanding": {"pending_tasks": 0, "high_priority_tasks": []},
        }
        out = _svc()._render_evening_for_llm(data)
        self.assertNotIn("PROJECTS TOUCHED", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
