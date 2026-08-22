"""
Device Registry — ground truth for physical hardware in this build.

SILVIA answers hardware questions from this registry.
If a property is not recorded, SILVIA says so — never invents it.
"""
from __future__ import annotations

NOT_RECORDED = "not_recorded"

DEVICE_REGISTRY: dict[str, dict] = {
    "storage-node": {
        "display_name": "Storage Node",
        "type": "nas",
        "hardware": "Raspberry Pi 4",
        "description": "Personal NAS server.",
        "sensors": [],             # confirmed: none
        "camera": False,           # confirmed: no camera
        "thermal_imaging": False,  # confirmed: no thermal imaging
        "display": NOT_RECORDED,
        "location": NOT_RECORDED,
        "notes": [],
    },
    "cyberdeck": {
        "display_name": "Cyberdeck",
        "type": "project",
        "hardware": NOT_RECORDED,
        "description": "Portable command platform — hardware project in progress.",
        "sensors": NOT_RECORDED,
        "camera": NOT_RECORDED,
        "thermal_imaging": NOT_RECORDED,
        "display": NOT_RECORDED,
        "location": NOT_RECORDED,
        "notes": ["Separate project from SILVIA/CMD-CTR infrastructure."],
    },
}


def get_device(name: str) -> dict | None:
    return DEVICE_REGISTRY.get(name.lower().strip())


def describe_device(name: str, correction: str | None = None) -> str:
    """Grounded device description. Returns 'not in registry' if unknown."""
    device = get_device(name)
    if device is None:
        return f"'{name}' is not in the device registry."

    if correction:
        return f"{device['display_name']}: {correction}"

    display = device["display_name"]
    hw = device.get("hardware")
    desc = device.get("description", "")
    notes = device.get("notes") or []

    hw_str = hw if (hw and hw != NOT_RECORDED) else "hardware details not recorded"
    result = f"{display}: {hw_str}. {desc}"
    if notes:
        result += " " + " ".join(notes)
    return result.strip()


def describe_sensors(name: str, correction: str | None = None) -> str:
    """Hardware/sensor property info. Returns 'not recorded' instead of inventing."""
    device = get_device(name)
    if device is None:
        return f"'{name}' is not in the device registry."

    if correction:
        return f"{device['display_name']}: {correction}"

    display = device["display_name"]
    sensors = device.get("sensors")
    camera = device.get("camera")
    thermal = device.get("thermal_imaging")

    if sensors == NOT_RECORDED:
        return f"Hardware properties for {display} are not recorded."

    parts = []

    if isinstance(sensors, list):
        if not sensors:
            parts.append(f"No sensors recorded for {display}.")
        else:
            parts.append(f"{display} sensors: {', '.join(sensors)}.")

    if camera is False:
        parts.append("No camera.")
    elif camera is True:
        parts.append("Has a camera.")
    elif camera == NOT_RECORDED:
        parts.append("Camera: not recorded.")

    if thermal is False:
        parts.append("No thermal imaging.")
    elif thermal is True:
        parts.append("Has thermal imaging.")
    elif thermal == NOT_RECORDED:
        parts.append("Thermal imaging: not recorded.")

    return " ".join(parts) if parts else f"Hardware details for {display} are not recorded."
