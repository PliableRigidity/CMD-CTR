"""Service presets — named bundles of services + capabilities for common node roles."""
from __future__ import annotations

# Each preset entry:
#   name       → service name (goes into node_services.name)
#   type       → service type
#   description → human-readable description
#   transport  → default transport (http unless overridden)
#   status     → initial status
#   capabilities → list of {name, description, risk_level}

SERVICE_PRESETS: dict[str, list[dict]] = {
    "nas": [
        {
            "name": "nas",
            "type": "storage",
            "description": "NAS main coordination service",
            "transport": "ssh",
            "capabilities": [
                {"name": "system.status", "description": "Check NAS status", "risk_level": "low"},
                {"name": "system.restart", "description": "Restart NAS", "risk_level": "medium"},
            ],
        },
        {
            "name": "samba",
            "type": "file-sharing",
            "description": "SMB/CIFS file sharing (Samba)",
            "transport": "ssh",
            "capabilities": [
                {"name": "system.start",   "description": "Start Samba", "risk_level": "low"},
                {"name": "system.stop",    "description": "Stop Samba",  "risk_level": "medium"},
                {"name": "system.restart", "description": "Restart Samba", "risk_level": "medium"},
                {"name": "system.status",  "description": "Check Samba status", "risk_level": "low"},
            ],
        },
        {
            "name": "ssh",
            "type": "remote-access",
            "description": "SSH remote access",
            "transport": "ssh",
            "capabilities": [
                {"name": "system.status", "description": "Check SSH daemon", "risk_level": "low"},
            ],
        },
        {
            "name": "file-storage",
            "type": "storage",
            "description": "File storage and volume management",
            "transport": "ssh",
            "capabilities": [
                {"name": "sensor.read", "description": "Read disk usage", "risk_level": "low"},
            ],
        },
    ],

    "media-player": [
        {
            "name": "media-player",
            "type": "media",
            "description": "Core media playback service",
            "transport": "http",
            "capabilities": [
                {"name": "media.play",     "description": "Play media",     "risk_level": "low"},
                {"name": "media.pause",    "description": "Pause playback", "risk_level": "low"},
                {"name": "media.stop",     "description": "Stop playback",  "risk_level": "low"},
                {"name": "media.next",     "description": "Next track",     "risk_level": "low"},
                {"name": "media.previous", "description": "Previous track", "risk_level": "low"},
            ],
        },
        {
            "name": "audio-output",
            "type": "audio",
            "description": "Audio output control",
            "transport": "http",
            "capabilities": [
                {"name": "audio.volume", "description": "Set volume",    "risk_level": "low"},
                {"name": "audio.play",   "description": "Play audio",    "risk_level": "low"},
                {"name": "audio.stop",   "description": "Stop audio",    "risk_level": "low"},
            ],
        },
        {
            "name": "playlist-control",
            "type": "media",
            "description": "Playlist management",
            "transport": "http",
            "capabilities": [
                {"name": "media.volume", "description": "Set volume",       "risk_level": "low"},
                {"name": "media.next",   "description": "Next track",       "risk_level": "low"},
                {"name": "media.previous","description": "Previous track",  "risk_level": "low"},
            ],
        },
    ],

    "robot": [
        {
            "name": "motion-controller",
            "type": "motion",
            "description": "Motion and drive control",
            "transport": "http",
            "capabilities": [
                {"name": "motion.forward",    "description": "Move forward",    "risk_level": "low"},
                {"name": "motion.backward",   "description": "Move backward",   "risk_level": "low"},
                {"name": "motion.stop",       "description": "Stop motion",     "risk_level": "low"},
                {"name": "motion.turn_left",  "description": "Turn left",       "risk_level": "low"},
                {"name": "motion.turn_right", "description": "Turn right",      "risk_level": "low"},
                {"name": "motion.hover",      "description": "Hover in place",  "risk_level": "low"},
            ],
        },
        {
            "name": "telemetry",
            "type": "telemetry",
            "description": "Sensor and position telemetry",
            "transport": "http",
            "capabilities": [
                {"name": "sensor.read",    "description": "Read sensors",       "risk_level": "low"},
                {"name": "battery.status", "description": "Battery level",      "risk_level": "low"},
            ],
        },
        {
            "name": "battery-monitor",
            "type": "power",
            "description": "Battery monitoring and alerts",
            "transport": "http",
            "capabilities": [
                {"name": "battery.status", "description": "Battery status", "risk_level": "low"},
            ],
        },
    ],

    "esp32": [
        {
            "name": "sensor",
            "type": "sensor",
            "description": "Sensor data collection",
            "transport": "mqtt",
            "capabilities": [
                {"name": "sensor.read",      "description": "Read sensor values",  "risk_level": "low"},
                {"name": "sensor.calibrate", "description": "Calibrate sensor",    "risk_level": "medium"},
            ],
        },
        {
            "name": "telemetry",
            "type": "telemetry",
            "description": "Periodic telemetry reporting via MQTT",
            "transport": "mqtt",
            "capabilities": [
                {"name": "sensor.read",    "description": "Read telemetry", "risk_level": "low"},
                {"name": "battery.status", "description": "Battery level",  "risk_level": "low"},
            ],
        },
        {
            "name": "mqtt-control",
            "type": "mqtt",
            "description": "MQTT command and control channel",
            "transport": "mqtt",
            "capabilities": [
                {"name": "system.restart", "description": "Reboot device", "risk_level": "high"},
                {"name": "gpio.set",       "description": "Set GPIO pin",  "risk_level": "medium"},
                {"name": "gpio.get",       "description": "Read GPIO pin", "risk_level": "low"},
            ],
        },
    ],

    "web-server": [
        {
            "name": "nginx",
            "type": "web",
            "description": "Nginx web server",
            "transport": "ssh",
            "capabilities": [
                {"name": "system.start",   "description": "Start nginx",   "risk_level": "low"},
                {"name": "system.stop",    "description": "Stop nginx",    "risk_level": "medium"},
                {"name": "system.restart", "description": "Restart nginx", "risk_level": "medium"},
                {"name": "system.status",  "description": "Nginx status",  "risk_level": "low"},
            ],
        },
        {
            "name": "ssh",
            "type": "remote-access",
            "description": "SSH remote access",
            "transport": "ssh",
            "capabilities": [
                {"name": "system.status", "description": "Check SSH daemon", "risk_level": "low"},
            ],
        },
    ],

    "drone": [
        {
            "name": "flight-controller",
            "type": "motion",
            "description": "Flight controller interface",
            "transport": "http",
            "capabilities": [
                {"name": "motion.hover",      "description": "Hover",           "risk_level": "low"},
                {"name": "motion.forward",    "description": "Fly forward",     "risk_level": "medium"},
                {"name": "motion.backward",   "description": "Fly backward",    "risk_level": "medium"},
                {"name": "motion.stop",       "description": "Stop / loiter",   "risk_level": "low"},
                {"name": "navigation.home",   "description": "Return to home",  "risk_level": "medium"},
                {"name": "navigation.goto",   "description": "Go to waypoint",  "risk_level": "medium"},
            ],
        },
        {
            "name": "telemetry",
            "type": "telemetry",
            "description": "Flight telemetry (GPS, IMU, battery)",
            "transport": "http",
            "capabilities": [
                {"name": "sensor.read",    "description": "Read sensors",   "risk_level": "low"},
                {"name": "battery.status", "description": "Battery status", "risk_level": "low"},
            ],
        },
        {
            "name": "camera",
            "type": "camera",
            "description": "Onboard camera",
            "transport": "http",
            "capabilities": [
                {"name": "camera.capture",      "description": "Take photo",  "risk_level": "low"},
                {"name": "camera.stream",       "description": "Live stream", "risk_level": "low"},
                {"name": "camera.stream_stop",  "description": "Stop stream", "risk_level": "low"},
            ],
        },
    ],
}

# Canonical aliases — maps user-input variants → canonical preset key
PRESET_ALIASES: dict[str, str] = {
    # NAS
    "nas": "nas",
    "network attached storage": "nas",
    "network-attached-storage": "nas",
    "file server": "nas",
    "file-server": "nas",
    "storage": "nas",
    # Media player
    "media": "media-player",
    "media player": "media-player",
    "media-player": "media-player",
    "music": "media-player",
    "music player": "media-player",
    "audio": "media-player",
    # Robot
    "robot": "robot",
    "rover": "robot",
    "mobile robot": "robot",
    # ESP32
    "esp32": "esp32",
    "sensor node": "esp32",
    "iot": "esp32",
    # Web server
    "web server": "web-server",
    "web-server": "web-server",
    "webserver": "web-server",
    "http server": "web-server",
    # Drone
    "drone": "drone",
    "uav": "drone",
    "quadcopter": "drone",
}


def resolve_preset(name: str) -> tuple[str | None, list[dict]]:
    """Resolve a user-provided preset name to (canonical_key, services list).
    Returns (None, []) if not found."""
    key = PRESET_ALIASES.get(name.lower().strip())
    if not key:
        # Try removing hyphens/underscores
        normalized = name.lower().strip().replace("_", "-").replace(" ", "-")
        key = SERVICE_PRESETS.get(normalized) and normalized
    if not key:
        return None, []
    return key, SERVICE_PRESETS.get(key, [])
