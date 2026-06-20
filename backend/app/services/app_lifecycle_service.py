"""Generic application lifecycle manager.

Design:
  - Runtime registry is checked FIRST for close/status. Process scan is a fallback.
  - No per-application logic. Works entirely from app_registry + runtime_registry.
  - Uses psutil for process discovery.
  - Uses WM_CLOSE via ctypes for graceful close (Windows native).
  - Never reports success without verified process exit.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_CLOSE_TIMEOUT = 5.0
_CLOSE_POLL = 0.25
WM_CLOSE = 0x0010


# ---------------------------------------------------------------------------
# psutil helpers
# ---------------------------------------------------------------------------

def _ps():
    import psutil
    return psutil


def _exe_basename(path: str) -> str:
    return os.path.basename(path).lower()


# ---------------------------------------------------------------------------
# Win32 helpers — pure ctypes, no pywin32
# ---------------------------------------------------------------------------

def _send_wm_close(pid: int) -> int:
    """Send WM_CLOSE to every visible top-level window owned by *pid*."""
    if sys.platform != "win32":
        return 0
    try:
        user32 = ctypes.windll.user32
        sent = [0]
        pid_out = ctypes.c_ulong(0)
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)

        def _cb(hwnd: int, _: int) -> bool:
            if user32.IsWindowVisible(hwnd):
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
                if pid_out.value == pid:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    sent[0] += 1
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        return sent[0]
    except Exception as exc:
        logger.debug("WM_CLOSE pid=%d: %s", pid, exc)
        return 0


def get_windows_for_pids(pids: list[int]) -> list[dict]:
    """Return visible windows (hwnd, title, pid) belonging to any of the given PIDs."""
    if sys.platform != "win32" or not pids:
        return []
    try:
        user32 = ctypes.windll.user32
        results = []
        pid_set = set(pids)
        pid_out = ctypes.c_ulong(0)
        buf = ctypes.create_unicode_buffer(512)
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)

        def _cb(hwnd: int, _: int) -> bool:
            if user32.IsWindowVisible(hwnd):
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
                if pid_out.value in pid_set:
                    user32.GetWindowTextW(hwnd, buf, 512)
                    title = buf.value.strip()
                    if title:
                        results.append({"hwnd": hwnd, "title": title, "pid": pid_out.value})
            return True

        user32.EnumWindows(EnumWindowsProc(_cb), 0)
        return results
    except Exception as exc:
        logger.debug("get_windows_for_pids: %s", exc)
        return []


def _get_process_tree(pid: int) -> list[int]:
    """Return *pid* plus all descendant PIDs (handles Chrome/Electron/Discord)."""
    psutil = _ps()
    pids = [pid]
    try:
        for child in psutil.Process(pid).children(recursive=True):
            try:
                pids.append(child.pid)
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    return pids


# ---------------------------------------------------------------------------
# Launch tracking — called from desktop_tool.open_app in a background thread
# ---------------------------------------------------------------------------

def snapshot_pids() -> set[int]:
    """Capture the set of running PIDs before a launch."""
    psutil = _ps()
    try:
        return {p.pid for p in psutil.process_iter(["pid"])}
    except Exception:
        return set()


def scan_new_processes(before_pids: set[int], app: dict) -> list[int]:
    """Find PIDs that appeared after launch and likely belong to this app.

    Strategy:
      1. Exact executable path match against new PIDs
      2. Basename match (also tries stem+.exe for .lnk and non-.exe paths)
      3. Fallback: all new non-system PIDs
    """
    psutil = _ps()

    exe_path = (app.get("executable_path") or app.get("executable") or "").strip()
    launch_cmd = (app.get("launch_command") or "").strip()

    # Build candidates: basename + stem variations to handle .lnk and non-.exe paths
    candidates: set[str] = set()
    for path in (exe_path, launch_cmd):
        if not path:
            continue
        base = _exe_basename(path)
        if base in ("", ".exe", ".lnk", ".cmd", ".bat"):
            continue
        candidates.add(base)
        stem = os.path.splitext(base)[0]
        if stem:
            candidates.add(stem + ".exe")
            candidates.add(stem)

    new_pids: list[int] = []
    matched_pids: list[int] = []

    for proc in psutil.process_iter(["pid", "name", "exe", "status"]):
        try:
            info = proc.info
            pid = info["pid"]
            if pid in before_pids:
                continue
            if info.get("status") == psutil.STATUS_ZOMBIE:
                continue

            new_pids.append(pid)

            proc_exe = (info.get("exe") or "").strip()
            proc_name = (info.get("name") or "").lower().strip()

            if exe_path and proc_exe and proc_exe.lower() == exe_path.lower():
                matched_pids.append(pid)
                continue
            if proc_exe:
                proc_base = _exe_basename(proc_exe)
                if proc_base in candidates:
                    matched_pids.append(pid)
                    continue
            if proc_name in candidates:
                matched_pids.append(pid)
        except Exception:
            pass

    if matched_pids:
        logger.info(
            "LAUNCH_TRACK SpecificMatch App=%r PIDs=%r",
            app.get("name"), matched_pids,
        )
        return matched_pids

    # Fallback: all new non-system-noise PIDs
    _SYSTEM_NOISE = {
        "dwm.exe", "conhost.exe", "svchost.exe", "csrss.exe", "winlogon.exe",
        "lsass.exe", "taskhostw.exe", "sihost.exe", "fontdrvhost.exe", "wininit.exe",
    }
    filtered = []
    for pid in new_pids:
        try:
            pname = psutil.Process(pid).name().lower()
            if pname not in _SYSTEM_NOISE:
                filtered.append(pid)
        except Exception:
            pass

    logger.info(
        "LAUNCH_TRACK FallbackNewPIDs App=%r PIDs=%r",
        app.get("name"), filtered,
    )
    return filtered


def track_launch(app: dict, command: str, launch_source: str, before_pids: set[int]) -> None:
    """Background thread: wait for process to appear, then register in runtime registry."""
    from backend.app.services import app_runtime_registry as _rt

    time.sleep(2.0)
    new_pids = scan_new_processes(before_pids, app)
    windows = get_windows_for_pids(new_pids)
    _rt.register(app["name"], command, new_pids, windows, launch_source)


# ---------------------------------------------------------------------------
# Generic process matcher — used when runtime registry has no entry
# ---------------------------------------------------------------------------

def find_processes_for_app(app: dict) -> list:
    """Return running psutil.Process objects matching this app.

    Check order:
      1. Runtime registry (tracked PIDs from launch)
      2. Process scan by executable path / basename / stem heuristics
    """
    psutil = _ps()
    from backend.app.services import app_runtime_registry as _rt

    # --- 1. Runtime registry ---
    entry = _rt.get(app.get("name", ""))
    if entry:
        tracked_pids = entry["pids"]
        alive_pids = [p for p in tracked_pids if psutil.pid_exists(p)]
        if alive_pids:
            # Expand to current process tree (handles launcher→actual-app spawning)
            all_pids: set[int] = set(alive_pids)
            for pid in alive_pids:
                try:
                    for child in psutil.Process(pid).children(recursive=True):
                        all_pids.add(child.pid)
                except psutil.Error:
                    pass

            procs = []
            for pid in all_pids:
                try:
                    procs.append(psutil.Process(pid))
                except psutil.Error:
                    pass

            logger.info(
                "LIFECYCLE_MATCH Application=%r Source=runtime_registry TrackedPIDs=%r AllPIDs=%r",
                app.get("name"), alive_pids, sorted(all_pids),
            )
            return procs

        # All tracked PIDs are dead — clean up registry
        _rt.unregister(app.get("name", ""))

    # --- 2. Process scan fallback ---
    exe_path = (app.get("executable_path") or app.get("executable") or "").strip()
    launch_cmd = (app.get("launch_command") or "").strip()

    candidates: set[str] = set()
    for path in (exe_path, launch_cmd):
        if not path:
            continue
        base = _exe_basename(path)
        candidates.add(base)
        stem = os.path.splitext(base)[0]
        if stem:
            candidates.add(stem + ".exe")
            candidates.add(stem)

    candidates = {c for c in candidates if c and c not in ("", ".exe", ".lnk", ".cmd", ".bat")}

    matches: list = []
    seen_pids: set[int] = set()

    for proc in psutil.process_iter(["pid", "name", "exe", "status"]):
        try:
            info = proc.info
            if info.get("status") == psutil.STATUS_ZOMBIE:
                continue
            pid = info["pid"]
            if pid in seen_pids:
                continue

            proc_exe = (info.get("exe") or "").strip()
            proc_name = (info.get("name") or "").lower().strip()

            if exe_path and proc_exe and proc_exe.lower() == exe_path.lower():
                matches.append(proc)
                seen_pids.add(pid)
                continue
            if proc_exe:
                proc_base = _exe_basename(proc_exe)
                if proc_base in candidates:
                    matches.append(proc)
                    seen_pids.add(pid)
                    continue
            if proc_name in candidates:
                matches.append(proc)
                seen_pids.add(pid)
        except Exception:
            pass

    logger.debug(
        "LIFECYCLE_MATCH Application=%r Source=process_scan Candidates=%r Matches=%d",
        app.get("name"), sorted(candidates), len(matches),
    )
    return matches


# ---------------------------------------------------------------------------
# Lifecycle operations
# ---------------------------------------------------------------------------

def close_app(name: str) -> dict:
    """Gracefully close a registered application and verify it actually closed."""
    from backend.app.services.desktop_service import DesktopService
    from backend.app.services import app_runtime_registry as _rt

    psutil = _ps()
    svc = DesktopService()
    app = svc.find_app(name)
    if not app:
        all_apps = svc.list_apps()
        return {
            "ok": False,
            "error": "app_not_found",
            "name": name,
            "summary": (
                f"I don't have '{name}' in the application registry. "
                f"Checked {len(all_apps)} registered apps."
            ),
        }

    procs = find_processes_for_app(app)
    if not procs:
        return {
            "ok": False,
            "error": "not_running",
            "name": app["name"],
            "summary": f"{app['name']} is not currently running.",
        }

    # Collect full process tree (handles launcher→child spawning)
    all_pids: set[int] = set()
    for proc in procs:
        try:
            all_pids.update(_get_process_tree(proc.pid))
        except Exception:
            all_pids.add(proc.pid)

    main_pids = [proc.pid for proc in procs]
    logger.info(
        "APP_CLOSE Application=%r MainPIDs=%r AllPIDs=%r",
        app["name"], main_pids, sorted(all_pids),
    )

    # Send WM_CLOSE to windows of main processes
    windows_closed = 0
    for pid in main_pids:
        windows_closed += _send_wm_close(pid)

    logger.info("APP_CLOSE WM_CLOSE sent to %d window(s)", windows_closed)

    # Poll until all PIDs exit or timeout
    deadline = time.monotonic() + _CLOSE_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(_CLOSE_POLL)
        still = [pid for pid in all_pids if psutil.pid_exists(pid)]
        if not still:
            _rt.unregister(app["name"])
            logger.info("APP_CLOSE Application=%r State=Closed", app["name"])
            return {
                "ok": True,
                "name": app["name"],
                "pids_closed": sorted(all_pids),
                "windows_closed": windows_closed,
                "summary": (
                    f"{app['name']} closed successfully. "
                    f"Sent WM_CLOSE to {windows_closed} window(s); "
                    f"{len(all_pids)} process(es) exited."
                ),
            }

    still_running = [pid for pid in all_pids if psutil.pid_exists(pid)]
    logger.warning(
        "APP_CLOSE_FAILED Application=%r Reason=process_still_running StillRunning=%r",
        app["name"], still_running,
    )
    return {
        "ok": False,
        "error": "process_still_running",
        "name": app["name"],
        "pids_sent": sorted(all_pids),
        "pids_still_running": still_running,
        "summary": (
            f"Attempted graceful close of {app['name']}. "
            f"Sent WM_CLOSE to {windows_closed} window(s), "
            f"but {len(still_running)} process(es) still running after {_CLOSE_TIMEOUT:.0f}s. "
            "The application may be waiting for user input (unsaved changes?). "
            f"Running PIDs: {still_running}"
        ),
    }


def app_status(name: str) -> dict:
    """Return running state of a registered application."""
    from backend.app.services.desktop_service import DesktopService
    from backend.app.services import app_runtime_registry as _rt

    psutil = _ps()
    svc = DesktopService()
    app = svc.find_app(name)
    if not app:
        return {
            "ok": False,
            "error": "app_not_found",
            "name": name,
            "summary": f"'{name}' is not in the application registry.",
        }

    procs = find_processes_for_app(app)
    if not procs:
        return {
            "ok": True,
            "name": app["name"],
            "running": False,
            "processes": [],
            "summary": f"{app['name']} is not currently running.",
        }

    proc_info = []
    for proc in procs:
        try:
            info = proc.as_dict(attrs=["pid", "name", "exe", "memory_percent", "cpu_percent"])
            proc_info.append({
                "pid": info["pid"],
                "name": info.get("name") or "",
                "exe": info.get("exe") or "",
                "memory_pct": round(float(info.get("memory_percent") or 0), 1),
                "cpu_pct": round(float(info.get("cpu_percent") or 0), 1),
            })
        except Exception:
            pass

    pids = [p["pid"] for p in proc_info]

    # Include window titles if we have them
    rt_entry = _rt.get(app["name"])
    windows = rt_entry.get("windows", []) if rt_entry else get_windows_for_pids(pids)
    launched_at = rt_entry.get("launched_at_str", "") if rt_entry else ""

    return {
        "ok": True,
        "name": app["name"],
        "running": True,
        "process_count": len(proc_info),
        "processes": proc_info,
        "windows": windows,
        "launched_at": launched_at,
        "summary": (
            f"{app['name']} is running — "
            f"{len(proc_info)} process(es), PID(s): {pids}"
            + (f", Window: {windows[0]['title']}" if windows else "")
            + (f", Launched: {launched_at}" if launched_at else "")
            + "."
        ),
    }


def list_running_apps() -> dict:
    """List all currently running registered apps.

    Combines runtime registry entries with live process scan for completeness.
    """
    from backend.app.services.desktop_service import DesktopService
    from backend.app.services import app_runtime_registry as _rt

    # Purge stale runtime entries first
    _rt.purge_dead()

    svc = DesktopService()
    all_apps = svc.list_apps()

    running: list[dict] = []
    seen_names: set[str] = set()

    # 1. Runtime registry entries first (most reliable — SILVIA launched these)
    for entry in _rt.get_all():
        app_name = entry["app_name"]
        pids = entry["pids"]
        windows = entry.get("windows", [])
        launched_at = entry.get("launched_at_str", "")
        running.append({
            "name": app_name,
            "running_pids": pids,
            "process_count": len(pids),
            "windows": windows,
            "launched_at": launched_at,
            "source": "runtime_registry",
        })
        seen_names.add(app_name.lower())

    # 2. Scan-based entries for apps not in runtime registry
    psutil = _ps()
    for app in all_apps:
        if app["name"].lower() in seen_names:
            continue
        procs = find_processes_for_app(app)
        if procs:
            pids = []
            for proc in procs:
                try:
                    pids.append(proc.pid)
                except Exception:
                    pass
            if pids:
                running.append({
                    "name": app["name"],
                    "running_pids": pids,
                    "process_count": len(pids),
                    "windows": [],
                    "launched_at": "",
                    "source": "process_scan",
                })
                seen_names.add(app["name"].lower())

    if not running:
        return {
            "ok": True,
            "count": 0,
            "apps": [],
            "summary": f"No registered apps are currently running. Checked {len(all_apps)} registry entries.",
        }

    lines = []
    for a in running:
        line = f"  {a['name']} — PID(s): {a['running_pids']}"
        if a.get("windows"):
            line += f" | Window: {a['windows'][0]['title']}"
        if a.get("launched_at"):
            line += f" | Launched: {a['launched_at']}"
        lines.append(line)

    return {
        "ok": True,
        "count": len(running),
        "apps": running,
        "summary": f"Running applications ({len(running)}):\n" + "\n".join(lines),
    }
