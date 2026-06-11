"""System/terminal capability tools for SILVIA — specs, network, processes, shell commands."""
from __future__ import annotations

import os
import platform
import re
import subprocess
import time
from typing import Optional

_BLOCKED_CMD = re.compile(
    r"(?:^|\b)(?:"
    r"format\s+[a-zA-Z]:|"
    r"del\s+/[sfqSFQ]|"
    r"rmdir\s+/[sqSQ]|"
    r"rd\s+/[sqSQ]|"
    r"shutdown\b|"
    r"restart-computer\b|"
    r"stop-computer\b|"
    r"reg\s+(?:delete|add)\b|"
    r"netsh\s+(?:winsock|int(?:erface)?)\s+reset|"
    r"cipher\s+/[wW]|"
    r"wmic\s+process\s+call\s+(?:delete|terminate)"
    r")",
    re.I,
)


def _make_result(ok: bool, tool: str, summary: str, data, error: Optional[str]) -> dict:
    return {"ok": ok, "tool": tool, "summary": summary, "data": data, "error": error}


def _get_gpu_name() -> Optional[str]:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[0].strip()
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name", "/value"],
            capture_output=True, text=True, timeout=4
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("name="):
                    val = stripped[5:].strip()
                    if val:
                        return val
    except Exception:
        pass
    return None


def get_system_specs() -> dict:
    try:
        import psutil
        freq = psutil.cpu_freq()
        cpu = {
            "processor": platform.processor() or "Unknown",
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "freq_mhz": round(freq.current) if freq else None,
            "usage_pct": psutil.cpu_percent(interval=0.3),
        }
        mem = psutil.virtual_memory()
        ram = {
            "total_gb": round(mem.total / 1024**3, 1),
            "used_gb": round(mem.used / 1024**3, 1),
            "available_gb": round(mem.available / 1024**3, 1),
            "used_pct": mem.percent,
        }
        disks = []
        for p in psutil.disk_partitions():
            try:
                u = psutil.disk_usage(p.mountpoint)
                disks.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(u.total / 1024**3, 1),
                    "used_gb": round(u.used / 1024**3, 1),
                    "free_gb": round(u.free / 1024**3, 1),
                    "used_pct": u.percent,
                })
            except Exception:
                pass
        os_info = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "node": platform.node(),
        }
        gpu = _get_gpu_name()
        data = {
            "cpu": cpu,
            "ram": ram,
            "disk": disks,
            "os": os_info,
            "gpu": gpu,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        freq_str = f" @ {cpu['freq_mhz']}MHz" if cpu["freq_mhz"] else ""
        summary = (
            f"OS: {os_info['system']} {os_info['release']} | "
            f"CPU: {cpu['cores_logical']} cores{freq_str} {cpu['usage_pct']}% load | "
            f"RAM: {ram['total_gb']}GB {ram['used_pct']}% used | "
            f"GPU: {gpu or 'unknown'} | "
            f"Disk: {disks[0]['device']} {disks[0]['total_gb']}GB {disks[0]['used_pct']}% used" if disks else ""
        )
        return _make_result(True, "get_system_specs", summary, data, None)
    except Exception as exc:
        return _make_result(False, "get_system_specs", f"Failed to get system specs: {exc}", None, str(exc))


def get_network_info() -> dict:
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        interfaces = []
        for iface, addr_list in addrs.items():
            ipv4 = [a.address for a in addr_list if a.family.name == "AF_INET"]
            ipv6 = [a.address for a in addr_list if a.family.name == "AF_INET6"]
            stat = stats.get(iface)
            interfaces.append({
                "name": iface,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "is_up": stat.isup if stat else False,
                "speed_mbps": stat.speed if stat else 0,
            })
        interfaces.sort(key=lambda x: (not x["is_up"], x["name"]))
        active = [i for i in interfaces if i["is_up"] and i["ipv4"]]
        parts = [f"{i['name']}: {', '.join(i['ipv4'])}" for i in active[:6]]
        summary = "Active: " + " | ".join(parts) if parts else "No active interfaces found"
        return _make_result(True, "get_network_info", summary, {"interfaces": interfaces}, None)
    except Exception as exc:
        return _make_result(False, "get_network_info", f"Failed to get network info: {exc}", None, str(exc))


def get_process_info(top_n: int = 15) -> dict:
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                procs.append({
                    "pid": info["pid"],
                    "name": info["name"] or "unknown",
                    "cpu_pct": round(info["cpu_percent"] or 0, 1),
                    "mem_pct": round(info["memory_percent"] or 0, 2),
                    "status": info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: (x["cpu_pct"], x["mem_pct"]), reverse=True)
        top = procs[:top_n]
        total = len(procs)
        busy = [p for p in top[:5] if p["cpu_pct"] > 0]
        busy_str = ", ".join(f"{p['name']} ({p['cpu_pct']}%)" for p in busy) if busy else "all idle"
        summary = f"{total} processes total. Top CPU: {busy_str}"
        return _make_result(True, "get_process_info", summary, {"processes": top, "total_count": total}, None)
    except Exception as exc:
        return _make_result(False, "get_process_info", f"Failed to get process list: {exc}", None, str(exc))


def run_shell_command(cmd: str, timeout: int = 15) -> dict:
    if not cmd or not cmd.strip():
        return _make_result(False, "run_command", "No command provided", None, "Command is empty.")

    if _BLOCKED_CMD.search(cmd):
        return _make_result(
            False, "run_command",
            f"Blocked: '{cmd[:60]}' contains a restricted operation.",
            None,
            "Command blocked — destructive operations are not permitted.",
        )

    try:
        result = subprocess.run(
            ["powershell.exe", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.expanduser("~"),
        )
        stdout = result.stdout.strip()[:3000] if result.stdout else ""
        stderr = result.stderr.strip()[:500] if result.stderr else ""
        ok = result.returncode == 0
        preview = (stdout[:80] if stdout else stderr[:80]) or "(no output)"
        summary = f"$ {cmd[:60]} | exit:{result.returncode} | {preview}"
        return _make_result(
            ok, "run_command", summary,
            {"cmd": cmd, "stdout": stdout, "stderr": stderr, "returncode": result.returncode},
            stderr if not ok and stderr else None,
        )
    except subprocess.TimeoutExpired:
        return _make_result(
            False, "run_command",
            f"$ {cmd[:60]} | TIMEOUT ({timeout}s)",
            {"cmd": cmd, "stdout": "", "stderr": "", "returncode": -1},
            f"Command timed out after {timeout} seconds.",
        )
    except Exception as exc:
        return _make_result(
            False, "run_command",
            f"$ {cmd[:60]} | ERROR: {exc}",
            None,
            str(exc),
        )
