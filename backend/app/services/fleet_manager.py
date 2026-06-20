"""Fleet management service — Phase 13B.

Aggregates the node registry + watch alerts into fleet-level views:
status summary, health scoring, group filtering, and bulk capability execution.
"""
from __future__ import annotations

from typing import Optional

from backend.app.services.node_service import NodeService
from backend.app.services.service_registry import ServiceRegistry
from backend.app.services.watch_service import WatchService

_CPU_WARN  = 85.0
_RAM_WARN  = 85.0
_DISK_WARN = 88.0
_TEMP_WARN = 75.0

# NL phrase → node type mapping (singular, lower-case)
_NL_TYPE_MAP = [
    (("raspberry pi", "raspberrypi", "raspberry-pi", "rpi"), "raspberry-pi"),
    (("vps", "vp"),                                           "vps"),
    (("nas",),                                                "nas"),
    (("server",),                                             "server"),
    (("workstation",),                                        "workstation"),
    (("drone", "uav", "quadcopter"),                          "drone"),
    (("robot", "rover"),                                      "robot"),
    (("esp32", "esp"),                                        "esp32"),
    (("container",),                                          "container"),
    (("virtual machine", "vm"),                               "vm"),
    (("cyberdeck",),                                          "cyberdeck"),
    (("edge device", "edge-device", "edge"),                  "edge-device"),
    (("sensor network", "sensor-network", "sensor"),          "sensor-network"),
]

_TAG_KEYWORDS = [
    "production", "prod", "development", "dev", "staging",
    "lab", "mobile", "test", "core", "ai", "exit-node", "storage",
]


def normalize_fleet_filter(phrase: str) -> tuple[str, str]:
    """Convert a natural-language group phrase → (filter_type, filter_value).

    Returns ("type", "raspberry-pi"), ("tag", "production"), ("all", ""), etc.
    """
    raw = phrase.lower().strip()
    p   = raw.rstrip("s").strip()  # strip plural ("nodes" → "node")

    # "all nodes", "all devices", "everything", "everywhere"
    _ALL_WORDS = {"node", "all", "everything", "everywhere", "device", "machine",
                  "all node", "all device", "all machine"}
    if p in _ALL_WORDS or raw in _ALL_WORDS:
        return "all", ""

    if p in ("offline", "online", "unknown"):
        return "status", p

    for keywords, type_val in _NL_TYPE_MAP:
        if any(kw in p for kw in keywords):
            return "type", type_val

    for tag in _TAG_KEYWORDS:
        if tag in p:
            return "tag", tag

    # Fallback: treat as type, kebab-ify
    return "type", p.replace(" ", "-")


def _node_health(node, alert_rule_keys: list[str]) -> str:
    """Return 'healthy' | 'warning' | 'critical' | 'unknown' for a node."""
    if node.status == "offline":
        return "critical"
    if node.status not in ("online", "offline", "unknown"):
        return "unknown"

    prefix = f"node:{node.id}:"
    node_alert_keys = [k for k in alert_rule_keys if k.startswith(prefix)]

    # Any critical alert → critical
    if any("critical" in k.lower() for k in node_alert_keys):
        return "critical"

    # Metric thresholds
    if any([
        node.cpu         is not None and node.cpu         >= _CPU_WARN,
        node.ram         is not None and node.ram         >= _RAM_WARN,
        node.disk        is not None and node.disk        >= _DISK_WARN,
        node.temperature is not None and node.temperature >= _TEMP_WARN,
    ]):
        return "warning"

    if node_alert_keys:
        return "warning"

    if node.status == "online":
        return "healthy"
    return "unknown"


def _node_summary(node, alert_rule_keys: list[str]) -> dict:
    health = _node_health(node, alert_rule_keys)
    issues = []
    if node.cpu         is not None and node.cpu         >= _CPU_WARN:
        issues.append(f"CPU {node.cpu:.0f}%")
    if node.ram         is not None and node.ram         >= _RAM_WARN:
        issues.append(f"RAM {node.ram:.0f}%")
    if node.disk        is not None and node.disk        >= _DISK_WARN:
        issues.append(f"Disk {node.disk:.0f}%")
    if node.temperature is not None and node.temperature >= _TEMP_WARN:
        issues.append(f"Temp {node.temperature:.0f}°C")
    return {
        "id":          node.id,
        "name":        node.name,
        "type":        node.type,
        "status":      node.status,
        "health":      health,
        "issues":      issues,
        "tags":        node.tags,
        "cpu":         node.cpu,
        "ram":         node.ram,
        "disk":        node.disk,
        "temperature": node.temperature,
        "agent_url":   node.agent_url,
    }


class FleetManager:
    def __init__(self) -> None:
        self._nodes    = NodeService()
        self._registry = ServiceRegistry()
        self._watch    = WatchService()

    # ── Fleet status ──────────────────────────────────────────────────────────

    def get_fleet_status(self) -> dict:
        nodes    = self._nodes.list_nodes()
        alerts   = self._watch.get_active_by_prefix("node:")
        rule_keys = [a.rule_key for a in alerts if a.rule_key]

        total   = len(nodes)
        online  = sum(1 for n in nodes if n.status == "online")
        offline = sum(1 for n in nodes if n.status == "offline")
        unknown = total - online - offline

        healths  = [_node_health(n, rule_keys) for n in nodes]
        healthy  = healths.count("healthy")
        warning  = healths.count("warning")
        critical = healths.count("critical")
        h_unknown = healths.count("unknown")

        # Health score: 100 − penalties for offline/critical/warning nodes
        if total > 0:
            score = max(0, round(
                100
                - (critical / total) * 50
                - (warning  / total) * 20
                - (offline  / total) * 30
            ))
        else:
            score = 100

        # Aggregate avg metrics across online nodes with live telemetry
        online_with_cpu  = [n for n in nodes if n.status == "online" and n.cpu  is not None]
        online_with_ram  = [n for n in nodes if n.status == "online" and n.ram  is not None]
        online_with_disk = [n for n in nodes if n.status == "online" and n.disk is not None]
        avg_cpu  = round(sum(n.cpu  for n in online_with_cpu)  / len(online_with_cpu),  1) if online_with_cpu  else None
        avg_ram  = round(sum(n.ram  for n in online_with_ram)  / len(online_with_ram),  1) if online_with_ram  else None
        avg_disk = round(sum(n.disk for n in online_with_disk) / len(online_with_disk), 1) if online_with_disk else None

        active_alerts = self._watch.get_active_by_prefix("")
        return {
            "total":         total,
            "online":        online,
            "offline":       offline,
            "unknown":       unknown,
            "healthy":       healthy,
            "warning":       warning,
            "critical":      critical,
            "h_unknown":     h_unknown,
            "health_score":  score,
            "active_alerts": len(active_alerts),
            "avg_cpu":       avg_cpu,
            "avg_ram":       avg_ram,
            "avg_disk":      avg_disk,
        }

    # ── Node grouping ─────────────────────────────────────────────────────────

    def get_fleet_groups(self) -> dict:
        nodes    = self._nodes.list_nodes()
        alerts   = self._watch.get_active_by_prefix("node:")
        rule_keys = [a.rule_key for a in alerts if a.rule_key]

        # Group by type
        by_type: dict[str, list] = {}
        for n in nodes:
            by_type.setdefault(n.type, []).append(_node_summary(n, rule_keys))

        # Group by tag
        by_tag: dict[str, list] = {}
        for n in nodes:
            for tag in n.tags:
                by_tag.setdefault(tag, []).append(_node_summary(n, rule_keys))

        # Group by registered service name
        all_svcs = self._registry.list_services()
        node_to_services: dict[str, set[str]] = {}
        for svc in all_svcs:
            node_to_services.setdefault(svc.node_id, set()).add(svc.name)

        by_service: dict[str, list] = {}
        for svc in all_svcs:
            by_service.setdefault(svc.name, [])
        for n in nodes:
            for svc_name in node_to_services.get(n.id, set()):
                by_service.setdefault(svc_name, []).append(_node_summary(n, rule_keys))
        by_service = {k: v for k, v in by_service.items() if v}

        return {"by_type": by_type, "by_tag": by_tag, "by_service": by_service}

    # ── Filtered views ────────────────────────────────────────────────────────

    def get_offline_nodes(self) -> list[dict]:
        nodes    = self._nodes.list_nodes()
        rule_keys = [a.rule_key for a in self._watch.get_active_by_prefix("node:") if a.rule_key]
        return [_node_summary(n, rule_keys) for n in nodes if n.status == "offline"]

    def get_unhealthy_nodes(self) -> list[dict]:
        nodes    = self._nodes.list_nodes()
        rule_keys = [a.rule_key for a in self._watch.get_active_by_prefix("node:") if a.rule_key]
        return [
            _node_summary(n, rule_keys)
            for n in nodes
            if _node_health(n, rule_keys) in ("warning", "critical")
        ]

    def filter_nodes(self, filter_type: str, filter_value: str) -> list:
        """Return Node objects matching the given fleet filter."""
        nodes = self._nodes.list_nodes()
        fv = filter_value.lower().strip()

        if filter_type == "all" or not filter_type:
            return nodes
        if filter_type == "status":
            return [n for n in nodes if n.status.lower() == fv]
        if filter_type == "type":
            return [n for n in nodes
                    if fv in n.type.lower() or n.type.lower() in fv]
        if filter_type == "tag":
            return [n for n in nodes if any(fv in t.lower() for t in n.tags)]
        if filter_type == "service":
            svcs = self._registry.list_services()
            nodes_with = {s.node_id for s in svcs if fv in s.name.lower()}
            return [n for n in nodes if n.id in nodes_with]
        return nodes

    def get_filtered_nodes(self, filter_type: str, filter_value: str) -> list[dict]:
        """Like filter_nodes but returns summary dicts."""
        nodes    = self.filter_nodes(filter_type, filter_value)
        rule_keys = [a.rule_key for a in self._watch.get_active_by_prefix("node:") if a.rule_key]
        return [_node_summary(n, rule_keys) for n in nodes]

    # ── Bulk capability execution ─────────────────────────────────────────────

    async def execute_fleet_action(
        self,
        capability: str,
        filter_type: str,
        filter_value: str,
        args: Optional[dict] = None,
        dry_run: bool = True,
        _intent: str = "",
    ) -> dict:
        """Execute a capability across all nodes matching the filter.

        When dry_run=True, resolves targets but does not dispatch.
        Returns a dict with results list, per-node ok/message, and aggregate counts.
        """
        import asyncio
        import time as _time
        from backend.app.services.capability_executor import CapabilityExecutor
        from backend.app.services.execution_ledger import get_ledger
        _t0 = _time.monotonic()

        target_nodes = self.filter_nodes(filter_type, filter_value)
        target_names = [n.name for n in target_nodes]

        if not target_nodes:
            filter_desc = f"{filter_type}={filter_value}" if filter_value else "all nodes"
            return {
                "ok":           False,
                "capability":   capability,
                "filter_type":  filter_type,
                "filter_value": filter_value,
                "dry_run":      dry_run,
                "target_nodes": [],
                "results":      [],
                "succeeded":    0,
                "failed":       0,
                "summary":      f"No nodes found matching {filter_desc}",
                "error":        "No matching nodes",
            }

        if dry_run:
            service_hint = f" (service: {args['service']})" if args and args.get("service") else ""
            dr = {
                "ok":           True,
                "capability":   capability,
                "filter_type":  filter_type,
                "filter_value": filter_value,
                "dry_run":      True,
                "target_nodes": target_names,
                "results":      [],
                "succeeded":    0,
                "failed":       0,
                "summary":      (
                    f"[DRY RUN] Would execute '{capability}'{service_hint} "
                    f"on {len(target_nodes)} node(s): {', '.join(target_names)}"
                ),
            }
            get_ledger().log_execution(
                intent=_intent, capability=capability, tool="fleet_action",
                status="dry_run",
                message=dr["summary"],
                metadata={"filter_type": filter_type, "filter_value": filter_value,
                          "target_count": len(target_nodes), "targets": target_names},
            )
            return dr

        executor = CapabilityExecutor()

        async def _exec_one(node) -> dict:
            result = await executor.execute(
                capability, args=args or {}, node_name=node.name, _intent=_intent,
            )
            return {
                "node":      node.name,
                "ok":        result["ok"],
                "message":   result.get("summary", ""),
                "simulated": (result.get("data") or {}).get("simulated", False),
            }

        results = list(await asyncio.gather(*[_exec_one(n) for n in target_nodes]))
        succeeded = sum(1 for r in results if r["ok"])
        failed    = len(results) - succeeded
        service_hint = f" ({args['service']})" if args and args.get("service") else ""
        final = {
            "ok":           failed == 0,
            "capability":   capability,
            "filter_type":  filter_type,
            "filter_value": filter_value,
            "dry_run":      False,
            "target_nodes": target_names,
            "results":      results,
            "succeeded":    succeeded,
            "failed":       failed,
            "summary":      (
                f"Fleet '{capability}'{service_hint} — "
                f"{succeeded}/{len(results)} succeeded"
            ),
        }
        get_ledger().log_execution(
            intent=_intent, capability=capability, tool="fleet_action",
            status="success" if failed == 0 else "partial",
            duration_ms=int((_time.monotonic() - _t0) * 1000),
            message=final["summary"],
            metadata={"filter_type": filter_type, "filter_value": filter_value,
                      "succeeded": succeeded, "failed": failed,
                      "targets": target_names},
        )
        return final
