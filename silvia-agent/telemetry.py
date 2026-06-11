"""System telemetry collection — cross-platform via psutil.
Supports standard (CPU/RAM/disk/temp) and robotics (battery/position/IMU) fields.
Robotics fields come from environment variables or future hardware drivers.
"""
import os
import platform
import time

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


def _read_env_float(key: str) -> float | None:
    val = os.getenv(key)
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _read_imu() -> dict | None:
    """Read IMU data from env vars (set by hardware driver or simulator)."""
    keys = ["AGENT_IMU_ACCEL_X", "AGENT_IMU_ACCEL_Y", "AGENT_IMU_ACCEL_Z",
            "AGENT_IMU_GYRO_X", "AGENT_IMU_GYRO_Y", "AGENT_IMU_GYRO_Z"]
    data = {}
    for key in keys:
        val = _read_env_float(key)
        if val is not None:
            data[key.replace("AGENT_IMU_", "").lower()] = val
    return data if data else None


def collect() -> dict:
    """Return full telemetry dict including robotics fields if configured."""
    base = {
        "cpu": None,
        "ram": None,
        "disk": None,
        "temperature": None,
        "uptime": None,
        # Robotics fields (None if not a robotics node)
        "battery_pct": None,
        "position_lat": None,
        "position_lon": None,
        "altitude": None,
        "heading": None,
        "mission_state": None,
        "imu_data": None,
    }

    if _HAS_PSUTIL:
        base["cpu"] = round(psutil.cpu_percent(interval=0.2), 1)
        mem = psutil.virtual_memory()
        base["ram"] = round(mem.percent, 1)

        try:
            root = "/" if platform.system() != "Windows" else "C:\\"
            base["disk"] = round(psutil.disk_usage(root).percent, 1)
        except Exception:
            pass

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ("cpu_thermal", "coretemp", "k10temp", "acpitz"):
                    if key in temps and temps[key]:
                        base["temperature"] = round(temps[key][0].current, 1)
                        break
        except (AttributeError, Exception):
            pass

        base["uptime"] = int(time.time() - psutil.boot_time())

    # Robotics fields — from environment variables
    base["battery_pct"] = _read_env_float("AGENT_BATTERY_PCT")
    base["position_lat"] = _read_env_float("AGENT_POSITION_LAT")
    base["position_lon"] = _read_env_float("AGENT_POSITION_LON")
    base["altitude"] = _read_env_float("AGENT_ALTITUDE")
    base["heading"] = _read_env_float("AGENT_HEADING")
    mission = os.getenv("AGENT_MISSION_STATE")
    if mission:
        base["mission_state"] = mission
    base["imu_data"] = _read_imu()

    return base
