"""Safety Engine — Phase 17A.

Classifies every tool action by risk level and gates execution
through the approval framework when required.

Risk levels:
  0 = READ     — view-only, no side effects
  1 = LOW      — benign side effects (open app, launch browser)
  2 = MODERATE — mutable but reversible (edit project, modify inventory)
  3 = HIGH     — infrastructure changes (restart service, SSH, git ops)
  4 = CRITICAL — destructive / irreversible (delete, shutdown, mass ops)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger("silvia.safety")

READ = 0
LOW = 1
MODERATE = 2
HIGH = 3
CRITICAL = 4

_LEVEL_NAMES = {READ: "read", LOW: "low", MODERATE: "moderate", HIGH: "high", CRITICAL: "critical"}
_LEVEL_FROM_NAME = {v: k for k, v in _LEVEL_NAMES.items()}

# ── Capability Risk Registry ────────────────────────────────────────────────
# Every known tool mapped to its risk level.
# Tools not listed default to MODERATE (safe by default = require approval).

_RISK_REGISTRY: dict[str, int] = {
    # ── READ (level 0) — view-only, never require approval ──────────────
    "get_time": READ,
    "get_time_in": READ,
    "get_weather": READ,
    "get_stock_price": READ,
    "search_web": READ,
    "list_nodes": READ,
    "list_nodes_by_type": READ,
    "get_node_info": READ,
    "get_node_ip": READ,
    "get_node_telemetry": READ,
    "ping_node": READ,
    "verify_node": READ,
    "refresh_nodes": READ,
    "get_system_specs": READ,
    "get_network_info": READ,
    "get_process_info": READ,
    "get_watch_alerts": READ,
    "list_reminders": READ,
    "list_tasks": READ,
    "get_calendar_today": READ,
    "get_upcoming_events": READ,
    "list_gcal_events": READ,
    "list_emails": READ,
    "search_emails": READ,
    "show_productivity_status": READ,
    "list_services": READ,
    "list_components": READ,
    "list_hw_projects": READ,
    "list_orders": READ,
    "list_projects": READ,
    "list_part_projects": READ,
    "list_project_parts": READ,
    "list_imports": READ,
    "list_locations": READ,
    "list_apps": READ,
    "list_running_apps": READ,
    "list_launch_preferences": READ,
    "list_scheduled_tasks": READ,
    "hw_inventory_summary": READ,
    "search_hardware": READ,
    "show_missing_parts": READ,
    "show_project_readiness": READ,
    "build_readiness_check": READ,
    "component_usage_stats": READ,
    "show_inventory_impact": READ,
    "show_imported_components": READ,
    "show_imported_projects": READ,
    "recommend_orders": READ,
    "forgotten_items": READ,
    "blocked_projects": READ,
    "startable_projects": READ,
    "project_briefing": READ,
    "project_blockers": READ,
    "project_readiness": READ,
    "project_dependencies": READ,
    "projects_using": READ,
    "show_knowledge_graph": READ,
    "get_project_memory": READ,
    "get_project_timeline": READ,
    "search_project_memory": READ,
    "workspace_status": READ,
    "workspace_priorities": READ,
    "daily_briefing": READ,
    "show_blocked_projects": READ,
    "show_ready_projects": READ,
    "what_should_i_work_on": READ,
    "what_to_order": READ,
    "closest_to_completion": READ,
    "reconcile_project_orders": READ,
    "rich_output": READ,
    "show_workspace_context": READ,
    "show_active_project": READ,
    "show_active_file": READ,
    "show_active_application": READ,
    "show_recent_sessions": READ,
    "show_last_session": READ,
    "show_accomplishments": READ,
    "continue_project": READ,
    "show_recent_actions": READ,
    "show_failures": READ,
    "show_planner_trace": READ,
    "show_capability_health": READ,
    "explain_last_action": READ,
    "fleet_status": READ,
    "show_fleet_offline": READ,
    "show_fleet_unhealthy": READ,
    "show_fleet_groups": READ,
    "semantic_search": READ,
    "show_app": READ,
    "show_app_runtime": READ,
    "app_status": READ,
    "show_launch_target": READ,
    "recent_files": READ,
    "find_files": READ,
    "list_project_templates": READ,
    "planner_what_can_i_build": READ,
    "planner_can_i_build": READ,
    "planner_gap_analysis": READ,
    "planner_architecture": READ,
    "planner_procurement": READ,
    "generate_bom": READ,
    "generate_roadmap_plan": READ,
    "plan_project": READ,
    "morning_briefing": READ,
    "daily_focus": READ,
    "evening_review": READ,
    "weekly_review": READ,
    "project_health": READ,
    "connect_google": READ,
    "get_hw_project": READ,
    "list_workflows": READ,
    "show_pending_workflows": READ,
    "show_workflow_history": READ,
    "get_workflow": READ,
    "show_memory_providers": READ,
    "show_memory_health": READ,
    "show_memory_timeline": READ,
    "show_memory_relationships": READ,
    "unified_memory_search": READ,
    "show_brain63_health": READ,
    "show_brain63_coverage": READ,
    "show_brain63_drafts": READ,
    "update_brain63_roadmap": READ,

    # ── LOW (level 1) — benign side effects ─────────────────────────────
    "open_app": LOW,
    "open_board": LOW,
    "open_url": LOW,
    "open_location": LOW,
    "open_target": LOW,
    "open_kicad_project": LOW,
    "close_app": LOW,
    "set_reminder": LOW,
    "complete_reminder": LOW,
    "complete_task": LOW,
    "set_launch_preference": LOW,
    "restore_workspace": LOW,
    "scan_apps": LOW,
    "fusion": LOW,

    # ── MODERATE (level 2) — mutable but reversible ─────────────────────
    "add_task": MODERATE,
    "add_node": MODERATE,
    "add_component": MODERATE,
    "add_order": MODERATE,
    "update_node_ip": MODERATE,
    "update_component": MODERATE,
    "update_order_status": MODERATE,
    "update_project_status": MODERATE,
    "update_hw_project_status": MODERATE,
    "update_ssh_profile": LOW,
    "create_project": MODERATE,
    "create_hw_project": MODERATE,
    "planner_create_project": MODERATE,
    "assign_part_to_project": MODERATE,
    "mark_item_acquired": MODERATE,
    "record_project_memory": MODERATE,
    "import_bom": MODERATE,
    "import_inventory": MODERATE,
    "import_brain63_memory": MODERATE,
    "register_node_preset": MODERATE,
    "add_node_service": MODERATE,
    "rename_node_service": MODERATE,
    "schedule_task": MODERATE,
    "disable_scheduled_task": MODERATE,
    "deduplicate_nodes": MODERATE,
    "merge_nodes": MODERATE,
    "create_calendar_event": MODERATE,
    "draft_email": MODERATE,

    # ── HIGH (level 3) — infrastructure changes ─────────────────────────
    # ssh_node risk is set dynamically in SafetyEngine.classify() based on SSH_REQUIRES_APPROVAL
    "run_command": HIGH,
    "execute_capability": HIGH,
    "send_node_command": HIGH,
    "send_bulk_command": HIGH,
    "fleet_action": HIGH,
    "remove_node_service": HIGH,

    # ── CRITICAL (level 4) — destructive / irreversible ─────────────────
    "delete_node": CRITICAL,
    "delete_task": CRITICAL,
    "delete_reminder": CRITICAL,
    "delete_scheduled_task": CRITICAL,
    "delete_calendar_event": CRITICAL,
    "send_email": CRITICAL,
}

# Dangerous command patterns — always CRITICAL regardless of tool
_DANGEROUS_PATTERNS = [
    re.compile(r"delete\s+(?:all|every)", re.I),
    re.compile(r"remove\s+all", re.I),
    re.compile(r"shutdown\s+all", re.I),
    re.compile(r"format\s+drive", re.I),
    re.compile(r"factory\s+reset", re.I),
    re.compile(r"wipe\s+(?:all|everything)", re.I),
    re.compile(r"drop\s+(?:all|table|database)", re.I),
]


class SafetyEngine:
    """Classifies tool actions by risk and determines approval requirements."""

    def classify(self, tool_name: str, args: dict | None = None,
                 query: str = "") -> dict[str, Any]:
        """Classify a tool call's risk level.

        Returns:
            {
                "tool": str,
                "risk_level": int,
                "risk_name": str,
                "requires_approval": bool,
                "reason": str,
            }
        """
        level = _RISK_REGISTRY.get(tool_name, MODERATE)

        # SSH risk is configurable — default LOW (direct execution)
        if tool_name == "ssh_node" and tool_name not in _RISK_REGISTRY:
            from backend.config import SSH_REQUIRES_APPROVAL
            level = HIGH if SSH_REQUIRES_APPROVAL else LOW

        # Check for dangerous patterns in the original query
        if query:
            for pat in _DANGEROUS_PATTERNS:
                if pat.search(query):
                    level = max(level, CRITICAL)
                    break

        # Context-based escalation
        level = self._contextual_escalation(tool_name, args or {}, level)

        requires = self._requires_approval(level)

        return {
            "tool": tool_name,
            "risk_level": level,
            "risk_name": _LEVEL_NAMES.get(level, "unknown"),
            "requires_approval": requires,
            "reason": self._build_reason(tool_name, level, args or {}),
        }

    def gate(self, tool_name: str, args: dict | None = None,
             query: str = "") -> dict[str, Any]:
        """Gate a tool call — returns classification + whether to proceed.

        If approval is required, the caller should create a pending approval
        instead of executing the tool.
        """
        classification = self.classify(tool_name, args, query)

        # Check active policy
        from backend.app.services.policy_engine import get_policy_engine
        policy = get_policy_engine()
        policy_check = policy.check(tool_name, classification["risk_level"])

        if not policy_check["allowed"]:
            classification["blocked"] = True
            classification["block_reason"] = policy_check["reason"]
            classification["requires_approval"] = False
            return classification

        classification["blocked"] = False
        return classification

    def _requires_approval(self, level: int) -> bool:
        """Determine if a risk level requires approval."""
        return level >= HIGH

    def _contextual_escalation(self, tool: str, args: dict, level: int) -> int:
        """Escalate risk based on specific arguments."""
        # Bulk operations are always at least HIGH
        if tool == "send_bulk_command":
            level = max(level, HIGH)
            cmd = args.get("command", "").lower()
            if cmd in ("emergency_stop", "reboot", "shutdown"):
                level = CRITICAL

        # Fleet actions are at least HIGH
        if tool == "fleet_action":
            level = max(level, HIGH)

        # Node commands: some are more dangerous
        if tool == "send_node_command":
            cmd = args.get("command", "").lower()
            if cmd in ("reboot", "shutdown", "emergency_stop", "factory_reset"):
                level = max(level, CRITICAL)
            elif cmd in ("arm", "disarm"):
                level = max(level, HIGH)

        # SSH with destructive commands
        if tool == "run_command":
            cmd = args.get("command", "").lower()
            if any(d in cmd for d in ("rm -rf", "mkfs", "dd if=", "shutdown", "reboot", "format")):
                level = CRITICAL

        # Email send is always critical (already set, but reinforce)
        if tool == "send_email":
            level = CRITICAL

        return level

    def _build_reason(self, tool: str, level: int, args: dict) -> str:
        """Human-readable reason for the classification."""
        if level == READ:
            return "Read-only operation."
        if level == LOW:
            return "Low-risk operation with benign side effects."
        if level == MODERATE:
            return "Modifies data but changes are reversible."
        if level == HIGH:
            target = args.get("node", args.get("project", args.get("name", "")))
            return f"Infrastructure change{' on ' + target if target else ''}. Approval required."
        if level == CRITICAL:
            target = args.get("node", args.get("project", args.get("name", "")))
            return f"Critical/destructive action{' targeting ' + target if target else ''}. Approval required."
        return "Unknown risk level."

    def get_registry_summary(self) -> dict[str, Any]:
        """Summary of the risk registry for diagnostics."""
        counts = {name: 0 for name in _LEVEL_NAMES.values()}
        for tool, level in _RISK_REGISTRY.items():
            counts[_LEVEL_NAMES[level]] += 1
        unregistered = 0
        return {
            "total_registered": len(_RISK_REGISTRY),
            "by_level": counts,
            "default_level": "moderate",
        }


_instance: Optional[SafetyEngine] = None


def get_safety_engine() -> SafetyEngine:
    global _instance
    if _instance is None:
        _instance = SafetyEngine()
    return _instance
