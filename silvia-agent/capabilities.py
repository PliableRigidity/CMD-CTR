"""Determine what this node is capable of reporting."""
import platform
import shutil


def detect() -> list[str]:
    """Return sorted list of capability strings."""
    caps: list[str] = ["telemetry", "services"]

    # Temperature sensors (Linux/RPi only)
    try:
        import psutil
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                caps.append("temperature")
    except Exception:
        pass

    # GPU detection
    if shutil.which("nvidia-smi"):
        caps.append("gpu-nvidia")
    if platform.system() == "Linux" and shutil.which("vcgencmd"):
        caps.append("gpu-rpi")

    # Docker
    if shutil.which("docker"):
        caps.append("docker")

    # Ollama inference
    if shutil.which("ollama"):
        caps.append("inference-ollama")

    # SSH server
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            if proc.info.get("name") in ("sshd", "ssh"):
                caps.append("ssh-server")
                break
    except Exception:
        pass

    return sorted(caps)
