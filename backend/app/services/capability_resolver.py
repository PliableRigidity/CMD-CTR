"""Capability resolution layer — Phase 13A.

Separates resolution (find → validate → return best match) from
execution (run the transport). The executor calls the resolver;
the resolver never runs anything.
"""
from __future__ import annotations

from typing import Optional

from backend.app.services.service_registry import ServiceRegistry


class CapabilityResolver:
    """Resolve a capability reference to an executable CapabilityMatch.

    Resolution order:
    1. Find services exposing the capability (optional: filtered to a node)
    2. Prefer running services over stopped ones
    3. If service_name given, prefer the named service
    4. Return best match or a structured error dict
    """

    def __init__(self) -> None:
        self._registry = ServiceRegistry()

    def resolve(
        self,
        capability: str,
        node_name: Optional[str] = None,
        service_name: Optional[str] = None,
        args: Optional[dict] = None,
    ) -> dict:
        """Resolve a capability to the best available service.

        Returns a dict:
            {
                "ok": bool,
                "match": CapabilityMatch | None,
                "node_name": str | None,
                "capability": str,
                "error": str | None,
                "requires_confirmation": bool,
            }
        """
        # Validate node exists when given
        resolved_node: Optional[str] = None
        if node_name:
            from backend.app.tools.node_tool import _find_node
            node = _find_node(node_name)
            if not node:
                return self._err(
                    capability,
                    f"Node '{node_name}' not found. Use 'list nodes' to see registered nodes.",
                )
            resolved_node = node.name

        # Find services that expose this capability
        matches = self._registry.find_capability(capability, node_name=resolved_node)
        if not matches:
            target = f"on {resolved_node}" if resolved_node else "in the registry"
            return self._err(
                capability,
                f"No service {target} exposes capability '{capability}'. "
                "Register a service with this capability first.",
            )

        # Prefer running services
        running = [m for m in matches if m.service_status == "running"]
        best = running[0] if running else matches[0]

        # Prefer named service when given
        if service_name:
            named = [m for m in matches if m.service_name.lower() == service_name.lower()]
            if named:
                running_named = [m for m in named if m.service_status == "running"]
                best = running_named[0] if running_named else named[0]

        return {
            "ok": True,
            "match": best,
            "node_name": best.node_name,
            "capability": capability,
            "error": None,
            "requires_confirmation": (
                bool(best.capability_confirmation)
                or best.capability_risk in ("high", "critical")
            ),
        }

    @staticmethod
    def _err(capability: str, message: str) -> dict:
        return {
            "ok": False,
            "match": None,
            "node_name": None,
            "capability": capability,
            "error": message,
            "requires_confirmation": False,
        }
