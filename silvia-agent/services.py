"""Detect running services by scanning active process names."""
import platform

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

# Process name patterns → service label.
# Checked against the running process list — cross-platform.
_PROCESS_MAP: dict[str, str] = {
    "ollama": "ollama",
    "tailscaled": "tailscale",
    "tailscale": "tailscale",
    "nginx": "nginx",
    "apache2": "apache",
    "httpd": "apache",
    "sshd": "ssh",
    "smbd": "samba",
    "nmbd": "samba",
    "dockerd": "docker",
    "containerd": "docker",
    "mosquitto": "mqtt",
    "redis-server": "redis",
    "postgres": "postgresql",
    "mysqld": "mysql",
    "mongod": "mongodb",
    "node": "node",
    "python3": "python",
    "python": "python",
    "uvicorn": "uvicorn",
    "gunicorn": "gunicorn",
    "caddy": "caddy",
    "haproxy": "haproxy",
    "grafana-server": "grafana",
    "prometheus": "prometheus",
    "influxd": "influxdb",
    "code": "vscode",
    "code-server": "code-server",
    "jupyter": "jupyter",
}

# On Windows, match against .exe names
_WINDOWS_MAP: dict[str, str] = {
    "ollama.exe": "ollama",
    "tailscale.exe": "tailscale",
    "nginx.exe": "nginx",
    "dockerd.exe": "docker",
    "redis-server.exe": "redis",
    "node.exe": "node",
    "python.exe": "python",
    "python3.exe": "python",
    "uvicorn.exe": "uvicorn",
    "Code.exe": "vscode",
    "jupyter.exe": "jupyter",
}


def detect() -> list[str]:
    """Return sorted list of detected service labels."""
    if not _HAS_PSUTIL:
        return []

    is_windows = platform.system() == "Windows"
    lookup = _WINDOWS_MAP if is_windows else _PROCESS_MAP
    found: set[str] = set()

    try:
        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name") or ""
            label = lookup.get(name)
            if label:
                found.add(label)
    except Exception:
        pass

    return sorted(found)
