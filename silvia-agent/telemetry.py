"""System telemetry collection — cross-platform via psutil."""
import platform
import time

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def collect() -> dict:
    """Return raw telemetry dict. All fields are None if psutil unavailable."""
    if not _HAS_PSUTIL:
        return {
            "cpu": None, "ram": None, "disk": None,
            "temperature": None, "uptime": None,
        }

    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    ram = mem.percent

    # Disk — use root partition
    try:
        root = "/" if platform.system() != "Windows" else "C:\\"
        disk = psutil.disk_usage(root).percent
    except Exception:
        disk = None

    # Temperature — Linux/RPi only; None on Windows/Mac
    temperature = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            # Prefer cpu_thermal (RPi), then coretemp (x86 Linux)
            for key in ("cpu_thermal", "coretemp", "k10temp", "acpitz"):
                if key in temps and temps[key]:
                    temperature = round(temps[key][0].current, 1)
                    break
    except (AttributeError, Exception):
        pass

    # Uptime in seconds
    uptime = int(time.time() - psutil.boot_time())

    return {
        "cpu": round(cpu, 1),
        "ram": round(ram, 1),
        "disk": round(disk, 1) if disk is not None else None,
        "temperature": temperature,
        "uptime": uptime,
    }
