"""Tool functions for chat-based service assignment (Phase 10B)."""
from __future__ import annotations

from backend.app.models.services import NodeServiceCreate, ServiceCapabilityCreate
from backend.app.services.node_service import NodeService
from backend.app.services.service_presets import resolve_preset
from backend.app.services.service_registry import ServiceRegistry


def _find_node_id(node_name: str) -> tuple[str | None, str | None]:
    """Return (node_id, display_name) or (None, None) if not found."""
    svc = NodeService()
    nodes = svc.list_nodes()
    lower = node_name.lower().strip()
    for n in nodes:
        if n.name.lower() == lower or n.id.lower() == lower:
            return n.id, n.name
        # Also check aliases stored in metadata
    return None, None


def register_node_preset(node_name: str, preset_name: str) -> dict:
    """Apply a named service preset to a node (upserts all services + capabilities)."""
    node_id, display_name = _find_node_id(node_name)
    if not node_id:
        return {"ok": False, "error": "node_not_found", "node_name": node_name}

    canonical, services = resolve_preset(preset_name)
    if not canonical or not services:
        return {"ok": False, "error": "preset_not_found", "preset_name": preset_name}

    registry = ServiceRegistry()
    added: list[str] = []
    updated: list[str] = []

    for svc_def in services:
        existing = registry.get_service_by_name(node_id, svc_def["name"])
        svc_data = NodeServiceCreate(
            name=svc_def["name"],
            type=svc_def.get("type", "custom"),
            description=svc_def.get("description", ""),
            transport=svc_def.get("transport", "http"),
            status="unknown",
        )
        if existing:
            registry.update_service(existing.id, svc_data)
            svc_id = existing.id
            updated.append(svc_def["name"])
        else:
            new_svc = registry.create_service(node_id, svc_data)
            svc_id = new_svc.id
            added.append(svc_def["name"])

        # Replace capabilities for this service entry
        for cap in svc_def.get("capabilities", []):
            registry.add_capability(
                svc_id,
                ServiceCapabilityCreate(
                    name=cap["name"],
                    description=cap.get("description", ""),
                    risk_level=cap.get("risk_level", "low"),
                ),
            )

    all_names = [s["name"] for s in services]
    # Oxford-comma list for SILVIA's response
    if len(all_names) > 2:
        svc_list = ", ".join(all_names[:-1]) + ", and " + all_names[-1]
    elif len(all_names) == 2:
        svc_list = all_names[0] + " and " + all_names[1]
    else:
        svc_list = all_names[0] if all_names else "(none)"

    return {
        "ok": True,
        "node_name": display_name,
        "preset": canonical,
        "services": all_names,
        "added": added,
        "updated": updated,
        "summary": (
            f"Done. {display_name} is now registered with {canonical} services: {svc_list}."
        ),
    }


def add_node_service(
    node_name: str,
    service_name: str,
    service_type: str = "",
    description: str = "",
) -> dict:
    """Add or update a single service on a node (upsert — safe for existing services)."""
    node_id, display_name = _find_node_id(node_name)
    if not node_id:
        return {"ok": False, "error": "node_not_found", "node_name": node_name}

    registry = ServiceRegistry()
    existing = registry.get_service_by_name(node_id, service_name)
    svc_data = NodeServiceCreate(
        name=service_name,
        type=service_type or _infer_type(service_name),
        description=description or _infer_description(service_name),
        transport="http",
        status="unknown",
    )

    if existing:
        registry.update_service(existing.id, svc_data)
        action = "updated"
    else:
        registry.create_service(node_id, svc_data)
        action = "added"

    return {
        "ok": True,
        "node_name": display_name,
        "service_name": service_name,
        "action": action,
        "summary": f"Done. Service '{service_name}' {action} on {display_name}.",
    }


def remove_node_service(node_name: str, service_name: str) -> dict:
    """Remove a service from a node by name."""
    node_id, display_name = _find_node_id(node_name)
    if not node_id:
        return {"ok": False, "error": "node_not_found", "node_name": node_name}

    registry = ServiceRegistry()
    ok = registry.remove_service_by_name(node_id, service_name)
    if not ok:
        return {
            "ok": False,
            "error": "service_not_found",
            "node_name": display_name,
            "service_name": service_name,
            "summary": f"Service '{service_name}' not found on {display_name}.",
        }
    return {
        "ok": True,
        "node_name": display_name,
        "service_name": service_name,
        "summary": f"Done. Removed service '{service_name}' from {display_name}.",
    }


def rename_node_service(node_name: str, old_name: str, new_name: str) -> dict:
    """Rename a service on a node."""
    node_id, display_name = _find_node_id(node_name)
    if not node_id:
        return {"ok": False, "error": "node_not_found", "node_name": node_name}

    registry = ServiceRegistry()
    updated = registry.rename_service(node_id, old_name, new_name)
    if not updated:
        return {
            "ok": False,
            "error": "service_not_found",
            "node_name": display_name,
            "old_name": old_name,
            "summary": f"Service '{old_name}' not found on {display_name}.",
        }
    return {
        "ok": True,
        "node_name": display_name,
        "old_name": old_name,
        "new_name": new_name,
        "summary": f"Done. Renamed '{old_name}' to '{new_name}' on {display_name}.",
    }


# ── Type / description inference ──────────────────────────────────────────────

_TYPE_MAP: dict[str, str] = {
    "samba": "file-sharing",
    "nfs": "file-sharing",
    "file-storage": "storage",
    "nas": "storage",
    "smb": "file-sharing",
    "ssh": "remote-access",
    "remote-access": "remote-access",
    "vpn": "network",
    "media-player": "media",
    "mpd": "media",
    "kodi": "media",
    "plex": "media",
    "audio-output": "audio",
    "playlist-control": "media",
    "nginx": "web",
    "apache": "web",
    "caddy": "web",
    "mqtt": "mqtt",
    "mqtt-control": "mqtt",
    "motion-controller": "motion",
    "flight-controller": "motion",
    "telemetry": "telemetry",
    "battery-monitor": "power",
    "sensor": "sensor",
}


def _infer_type(service_name: str) -> str:
    name = service_name.lower().strip()
    if name in _TYPE_MAP:
        return _TYPE_MAP[name]
    if "sensor" in name:
        return "sensor"
    if "telemetry" in name:
        return "telemetry"
    if "battery" in name:
        return "power"
    if "motion" in name or "controller" in name:
        return "motion"
    if "media" in name or "player" in name:
        return "media"
    return "custom"


_DESC_MAP: dict[str, str] = {
    "samba": "SMB/CIFS file sharing (Samba)",
    "nas": "NAS coordination service",
    "ssh": "SSH remote access",
    "file-storage": "File storage and volume management",
    "media-player": "Core media playback service",
    "audio-output": "Audio output control",
    "playlist-control": "Playlist management",
    "motion-controller": "Motion and drive control",
    "telemetry": "Sensor and position telemetry",
    "battery-monitor": "Battery monitoring and alerts",
    "sensor": "Sensor data collection",
    "mqtt-control": "MQTT command and control channel",
    "nginx": "Nginx web server",
    "apache": "Apache HTTP server",
    "caddy": "Caddy web server",
}


def _infer_description(service_name: str) -> str:
    return _DESC_MAP.get(service_name.lower().strip(), f"{service_name} service")
