"""
Project Registry — ground truth for known projects.

Status and milestones are never invented. 'Status not recorded' is the
honest answer when nothing is known. No completion percentages, no invented
milestones, no project logs that don't come from actual tool output.
"""
from __future__ import annotations

PROJECT_REGISTRY: dict[str, dict] = {
    "cmd-ctr": {
        "display_name": "CMD-CTR / SILVIA",
        "aliases": ["silvia", "cmd-ctr", "cmdctr", "command center", "cmd ctr"],
        "description": "Personal AI operating system and command center.",
        "status": "active",
        "status_detail": "Active development.",
        "notes": [],
    },
    "dronehive": {
        "display_name": "DroneHive",
        "aliases": ["dronehive", "droneHive", "drone hive", "drone-hive"],
        "description": "Drone swarm project.",
        "status": "unknown",
        "status_detail": None,
        "notes": [],
    },
    "koi": {
        "display_name": "KOI",
        "aliases": ["koi"],
        "description": "No details recorded.",
        "status": "unknown",
        "status_detail": None,
        "notes": [],
    },
    "brain63": {
        "display_name": "Brain63",
        "aliases": ["brain63", "brain 63"],
        "description": "No details recorded.",
        "status": "unknown",
        "status_detail": None,
        "notes": [],
    },
    "cyberdeck": {
        "display_name": "Cyberdeck",
        "aliases": ["cyberdeck"],
        "description": "Portable command platform project.",
        "status": "unknown",
        "status_detail": None,
        "notes": [],
    },
    "university": {
        "display_name": "University",
        "aliases": ["university", "uni", "school", "studies"],
        "description": "University coursework and studies.",
        "status": "active",
        "status_detail": None,
        "notes": [],
    },
    "storage-node": {
        "display_name": "Storage Node",
        "aliases": ["storage-node"],
        "description": "Raspberry Pi 4 NAS server.",
        "status": "active",
        "status_detail": None,
        "notes": ["Infrastructure node — registered in CMD-CTR node registry."],
    },
}


def find_project(name: str) -> dict | None:
    """Find project by name or alias (case-insensitive). Returns None if not found."""
    name_lower = name.lower().strip()
    for key, proj in PROJECT_REGISTRY.items():
        if name_lower == key or name_lower in [a.lower() for a in proj["aliases"]]:
            return proj
    return None


def list_projects() -> str:
    """Comma-separated list of known project names (excluding infrastructure nodes)."""
    return ", ".join(
        p["display_name"] for k, p in PROJECT_REGISTRY.items() if k != "storage-node"
    )


def describe_project(name: str, correction: str | None = None) -> str:
    """Grounded project description. Returns honest 'not recorded' for unknown status."""
    proj = find_project(name)
    if proj is None:
        known = list_projects()
        return f"'{name}' is not in the project registry. Known projects: {known}."

    if correction:
        return f"{proj['display_name']}: {correction}"

    display = proj["display_name"]
    desc = proj["description"]
    status = proj["status"]
    detail = proj["status_detail"]
    notes = proj.get("notes") or []

    if status == "active" and detail:
        status_str = detail
    elif status == "active":
        status_str = "Active."
    else:
        status_str = "Status not recorded."

    result = f"{display}: {desc} {status_str}"
    if notes:
        result += " " + " ".join(notes)
    return result.strip()
