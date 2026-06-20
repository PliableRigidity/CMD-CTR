"""Desktop control tools — file search, folder open, app launch.

Safety contract:
  READ   — list locations, search files  ✓
  LAUNCH — open folder, launch app       ✓
  MODIFY — rename / delete / write       ✗  (never)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.app.services.desktop_service import DesktopService

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
    "target", ".cargo", ".idea", ".vscode",
}

_MAX_RESULTS = 50
_MAX_DEPTH   = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mtime_str(path: str) -> str:
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


def _size_str(path: str) -> str:
    try:
        b = os.path.getsize(path)
        if b < 1024:
            return f"{b} B"
        if b < 1024 ** 2:
            return f"{b / 1024:.1f} KB"
        return f"{b / 1024 ** 2:.1f} MB"
    except OSError:
        return ""


def _walk(root: str, max_depth: int):
    """os.walk wrapper with depth limit and skip list."""
    root = root.rstrip(os.sep)
    root_depth = root.count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.count(os.sep) - root_depth
        if depth >= max_depth:
            dirnames.clear()
            continue
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        yield dirpath, filenames


def _oxford(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


# ---------------------------------------------------------------------------
# Tool: open_location
# ---------------------------------------------------------------------------

def open_location(name: str) -> dict:
    """Open a trusted location in File Explorer."""
    svc = DesktopService()
    loc = svc.find_location(name)
    if not loc:
        locations = svc.list_locations()
        known = [l["name"] for l in locations]
        return {
            "ok": False,
            "error": "location_not_found",
            "name": name,
            "summary": (
                f"I don't have a location called '{name}' in my registry. "
                f"Known locations: {_oxford(known)}. "
                f"To add it, say: 'add {name} folder at <path>'."
            ),
        }
    path = loc["path"]
    if not os.path.isdir(path):
        return {
            "ok": False,
            "error": "path_not_found",
            "name": loc["name"],
            "path": path,
            "summary": f"Path does not exist on disk: {path}",
        }
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        return {
            "ok": True,
            "name": loc["name"],
            "path": path,
            "summary": f"Done. Opened {loc['name']} — {path}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "launch_failed",
            "name": loc["name"],
            "path": path,
            "summary": f"Failed to open {loc['name']}: {exc}",
        }


# ---------------------------------------------------------------------------
# Tool: find_files
# ---------------------------------------------------------------------------

def find_files(
    query: str = "",
    extension: str = "",
    location: str = "",
    max_results: int = _MAX_RESULTS,
) -> dict:
    """Search for files across trusted locations (or a specific one)."""
    svc = DesktopService()

    # Resolve search roots
    if location:
        loc = svc.find_location(location)
        if not loc:
            return {
                "ok": False,
                "error": "location_not_found",
                "summary": f"Location '{location}' not in the registry.",
                "results": [],
            }
        if not os.path.isdir(loc["path"]):
            return {
                "ok": False,
                "error": "path_not_found",
                "summary": f"{loc['name']} path does not exist: {loc['path']}",
                "results": [],
            }
    elif not any(os.path.isdir(l["path"]) for l in svc.list_locations()):
        return {
            "ok": True,
            "count": 0,
            "results": [],
            "summary": "No registered locations currently exist on disk.",
        }

    # Normalise extension (stl → .stl)
    ext_lower = ""
    if extension:
        ext_lower = extension.lower().lstrip(".")
        # Special alias: pcb → kicad_pcb
        _EXT_ALIAS = {
            "pcb": "kicad_pcb",
            "schematic": "kicad_sch",
            "sch": "kicad_sch",
        }
        ext_lower = _EXT_ALIAS.get(ext_lower, ext_lower)

    query_lower = query.strip().lower()

    results = svc.search_files(
        query=query_lower,
        extension=ext_lower,
        location=location,
        max_results=max_results,
    )
    indexed_files = svc.count_indexed_files(location=location)

    total = len(results)
    label_parts = []
    if ext_lower:
        label_parts.append(f".{ext_lower}")
    if query_lower:
        label_parts.append(f"'{query}'")
    label = " ".join(label_parts) if label_parts else "all"

    if total == 0:
        where = f"in {location}" if location else "in registered locations"
        return {
            "ok": True,
            "count": 0,
            "indexed_files": indexed_files,
            "results": [],
            "summary": f"No {label} files found {where}. Searched {indexed_files} indexed files.",
        }

    top = results[:10]
    listing = "\n".join(
        f"  {r['name']}  ({r['location']}, {r['modified']})" for r in top
    )
    more = f"\n  … and {total - 10} more." if total > 10 else ""
    where = f"in {location}" if location else "across trusted locations"
    summary = (
        f"Found {total} {label} file{'s' if total != 1 else ''} {where}:\n{listing}{more}"
    )

    return {
        "ok": True,
        "count": total,
        "indexed_files": indexed_files,
        "results": results,
        "summary": f"{summary}\nSearched {indexed_files} indexed files.",
    }


# ---------------------------------------------------------------------------
# Tool: recent_files
# ---------------------------------------------------------------------------

def recent_files(location: str = "", max_results: int = 25) -> dict:
    """Return newest indexed files from trusted locations."""
    svc = DesktopService()
    if location:
        loc = svc.find_location(location)
        if not loc:
            return {
                "ok": False,
                "error": "location_not_found",
                "summary": f"Location '{location}' not in the registry.",
                "results": [],
            }
        if not os.path.isdir(loc["path"]):
            return {
                "ok": False,
                "error": "path_not_found",
                "summary": f"{loc['name']} path does not exist: {loc['path']}",
                "results": [],
            }

    results = svc.recent_files(location=location, max_results=max_results)
    indexed_files = svc.count_indexed_files(location=location)
    if not results:
        where = f"in {location}" if location else "in registered locations"
        return {
            "ok": True,
            "count": 0,
            "indexed_files": indexed_files,
            "results": [],
            "summary": f"No recent files found {where}. Searched {indexed_files} indexed files.",
        }

    listing = "\n".join(
        f"  {r['name']}  ({r['location']}, {r['modified']})" for r in results[:10]
    )
    more = f"\n  ... and {len(results) - 10} more." if len(results) > 10 else ""
    where = f"in {location}" if location else "across trusted locations"
    return {
        "ok": True,
        "count": len(results),
        "indexed_files": indexed_files,
        "results": results,
        "summary": f"Recent files {where}:\n{listing}{more}\nSearched {indexed_files} indexed files.",
    }


# ---------------------------------------------------------------------------
# Tool: open_kicad_project
# ---------------------------------------------------------------------------

def _normalise_project_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _strip_project_words(value: str) -> str:
    cleaned = re.sub(r"\bkicad\b", " ", value, flags=re.I)
    cleaned = re.sub(r"\b(project|projects|file|open|launch|latest|newest|the)\b", " ", cleaned, flags=re.I)
    return re.sub(r"\s+", " ", cleaned).strip()


def _resolve_kicad_project(query: str = "", latest: bool = False) -> dict:
    files = find_files(extension="kicad_pro", max_results=200)
    if not files.get("ok"):
        return {
            "ok": False,
            "error": files.get("error", "search_failed"),
            "summary": files.get("summary", "KiCad project search failed."),
            "matches": [],
        }

    projects = files.get("results", [])
    if not projects:
        return {
            "ok": False,
            "error": "project_not_found",
            "summary": f"No KiCad project files were found. Searched {files.get('indexed_files', 0)} indexed files.",
            "matches": [],
        }

    if latest or not query.strip():
        return {"ok": True, "project": projects[0], "matches": projects[:1]}

    wanted = _normalise_project_key(_strip_project_words(query))
    matches = []
    for project in projects:
        stem = Path(project["name"]).stem
        haystack = _normalise_project_key(stem)
        if wanted and wanted in haystack:
            matches.append(project)

    if not matches:
        top_names = ", ".join(p["name"] for p in projects[:8])
        return {
            "ok": False,
            "error": "project_not_found",
            "summary": (
                f"No KiCad project matched '{query}'. Searched {len(projects)} KiCad project files. "
                f"Closest available projects: {top_names}"
            ),
            "matches": [],
        }

    if len(matches) > 1:
        names = ", ".join(p["name"] for p in matches[:8])
        return {
            "ok": False,
            "error": "multiple_matches",
            "summary": f"Multiple KiCad projects matched '{query}': {names}. Please specify which one.",
            "matches": matches,
        }

    return {"ok": True, "project": matches[0], "matches": matches}


def open_kicad_project(query: str = "", latest: bool = False) -> dict:
    """Open a resolved .kicad_pro file in KiCad."""
    svc = DesktopService()
    app = svc.find_app("KiCad")
    if not app:
        return {
            "ok": False,
            "error": "app_not_found",
            "summary": "KiCad project matched, but KiCad is not registered in the application registry.",
        }

    exe = svc.resolve_app_executable(app)
    if not exe:
        return {
            "ok": False,
            "error": "executable_not_found",
            "summary": (
                "KiCad is registered, but its executable could not be resolved. "
                f"Registered executable: {app.get('executable')}"
            ),
        }

    resolved = _resolve_kicad_project(query=query, latest=latest)
    if not resolved.get("ok"):
        logger.info(
            "INTENT: open_project MATCH: none ROUTE: file_open APPLICATION: KiCad Query=%r Result=%s",
            query,
            resolved.get("error"),
        )
        return resolved

    project = resolved["project"]
    try:
        from backend.app.services.app_lifecycle_service import snapshot_pids as _snapshot, track_launch as _track
        import threading
        before_pids = _snapshot()
        proc = subprocess.Popen([exe, project["path"]])
        pid = getattr(proc, "pid", None)
        logger.info(
            "INTENT: open_project MATCH: %s ROUTE: file_open APPLICATION: KiCad",
            project["name"],
        )
        logger.info(
            "APP_LAUNCH Application=%r Executable=%r Argument=%r PID=%r Result=success",
            "KiCad", exe, project["path"], pid,
        )
        # Seed runtime registry immediately with the known PID, then let the
        # background tracker expand to children after 2 s.
        from backend.app.services import app_runtime_registry as _rt
        _rt.register("KiCad", exe, [pid] if pid is not None else [], [], "kicad_project")
        kicad_app = {"name": "KiCad", "executable_path": exe, "executable": exe}
        threading.Thread(
            target=_track,
            args=(kicad_app, exe, "kicad_project", before_pids),
            daemon=True,
        ).start()
        return {
            "ok": True,
            "name": "KiCad",
            "project": project,
            "executable": exe,
            "summary": f"KiCad launched with {project['name']}.",
        }
    except Exception as exc:
        logger.exception(
            "APP_LAUNCH Application=%r Executable=%r Argument=%r Result=launch_failed",
            "KiCad",
            exe,
            project["path"],
        )
        return {
            "ok": False,
            "error": "launch_failed",
            "project": project,
            "executable": exe,
            "summary": f"KiCad project was resolved, but launch failed for {project['path']}: {exc}",
        }


# ---------------------------------------------------------------------------
# Tool: open_app
# ---------------------------------------------------------------------------

def open_app(name: str) -> dict:
    """Launch a registered application."""
    svc = DesktopService()
    matches = svc.find_app_matches(name, limit=5)
    if not matches:
        apps = svc.list_apps()
        known = [a["name"] for a in apps]
        logger.warning(
            "APP_LAUNCH Application=%r Result=app_not_found RegisteredAppCount=%d Sample=%r",
            name,
            len(known),
            known[:25],
        )
        return {
            "ok": False,
            "error": "app_not_found",
            "name": name,
            "summary": (
                f"I searched the application registry but did not find '{name}'. "
                f"Registry entries checked: {len(known)}. Try 'rescan apps' if it was installed recently."
            ),
        }

    query_norm = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    exact_matches = [
        app for app in matches
        if query_norm == app.get("normalized_name")
        or query_norm in {str(alias).lower() for alias in app.get("aliases", [])}
    ]
    exact_name_matches = [app for app in exact_matches if query_norm == app.get("normalized_name")]
    if len(exact_name_matches) == 1:
        exact_matches = exact_name_matches
    if len(exact_matches) > 1:
        names = [app["name"] for app in exact_matches]
        logger.warning(
            "APP_LAUNCH Application=%r Result=multiple_matches Matches=%r",
            name,
            names,
        )
        return {
            "ok": False,
            "error": "multiple_matches",
            "name": name,
            "matches": exact_matches,
            "summary": f"I found multiple application matches for '{name}': {_oxford(names)}. Which one do you mean?",
        }

    app = exact_matches[0] if exact_matches else matches[0]
    candidates = svc.get_launch_candidates(app)
    if not candidates:
        logger.warning(
            "APP_LAUNCH Application=%r Result=no_launch_candidate Registry=%r",
            app["name"],
            app,
        )
        return {
            "ok": False,
            "error": "no_launch_candidate",
            "name": app["name"],
            "summary": (
                f"{app['name']} was found in the application registry, but no valid launch target exists. "
                f"Shortcut: {app.get('shortcut_path') or 'none'}; executable: {app.get('executable_path') or app.get('executable') or 'none'}."
            ),
        }

    failures = []
    chosen = None
    try:
        # Snapshot PIDs before launch so we can identify what spawned
        from backend.app.services.app_lifecycle_service import snapshot_pids as _snapshot
        before_pids = _snapshot()

        for candidate in candidates:
            command = candidate["command"]
            launch_type = candidate["type"]
            try:
                if sys.platform == "win32":
                    if launch_type in {"shortcut", "uri", "web"}:
                        os.startfile(command)
                    elif command in ("explorer", "notepad") or shutil.which(command):
                        subprocess.Popen([command], shell=True)
                    elif command.endswith(".cmd") or command.endswith(".bat"):
                        subprocess.Popen(command, shell=True)
                    else:
                        os.startfile(command)
                else:
                    subprocess.Popen([command])
                chosen = candidate
                break
            except Exception as exc:
                failures.append(f"{launch_type}:{command} -> {exc}")
        if not chosen:
            raise RuntimeError("; ".join(failures) or "no launch candidate succeeded")
        logger.info(
            "APP_LAUNCH Application=%r Executable=%r LaunchType=%r Source=%r Result=success",
            app["name"],
            chosen["command"],
            chosen["type"],
            app.get("source"),
        )

        # Track the spawned process in the runtime registry (background thread —
        # non-blocking so the launch response returns immediately).
        import threading
        from backend.app.services.app_lifecycle_service import track_launch as _track
        app_snapshot = dict(app)
        cmd_snapshot = chosen["command"]
        lt_snapshot = chosen["type"]
        bpids_snapshot = set(before_pids)
        threading.Thread(
            target=_track,
            args=(app_snapshot, cmd_snapshot, lt_snapshot, bpids_snapshot),
            daemon=True,
        ).start()

        return {
            "ok": True,
            "name": app["name"],
            "category": app["category"],
            "executable": chosen["command"],
            "launch_type": chosen["type"],
            "source": app.get("source"),
            "summary": f"{app['name']} launched successfully.",
        }
    except Exception as exc:
        logger.exception(
            "APP_LAUNCH Application=%r Candidates=%r Result=launch_failed",
            app["name"],
            candidates,
        )
        return {
            "ok": False,
            "error": "launch_failed",
            "name": app["name"],
            "candidates": candidates,
            "summary": f"{app['name']} was found, but every launch method failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Tool: scan_apps
# ---------------------------------------------------------------------------

def scan_apps() -> dict:
    svc = DesktopService()
    result = svc.scan_installed_apps()
    return result


# ---------------------------------------------------------------------------
# Tool: show_app
# ---------------------------------------------------------------------------

def show_app(name: str) -> dict:
    svc = DesktopService()
    matches = svc.find_app_matches(name, limit=5)
    if not matches:
        return {
            "ok": False,
            "error": "app_not_found",
            "name": name,
            "summary": f"I searched the application registry but did not find '{name}'. Try 'rescan apps'.",
        }
    query_norm = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    exact_matches = [
        app for app in matches
        if query_norm == app.get("normalized_name")
        or query_norm in {str(alias).lower() for alias in app.get("aliases", [])}
    ]
    exact_name_matches = [app for app in exact_matches if query_norm == app.get("normalized_name")]
    if len(exact_name_matches) == 1:
        exact_matches = exact_name_matches
    if len(exact_matches) == 1:
        matches = exact_matches
    if len(matches) > 1:
        names = [app["name"] for app in matches]
        summary = "Possible matches:\n" + "\n".join(
            f"  - {app['name']} [{app['source']}] aliases: {', '.join(app['aliases'][:6])}"
            for app in matches
        )
        return {
            "ok": True,
            "count": len(matches),
            "matches": matches,
            "summary": summary if len(matches) > 1 else f"Found {names[0]}.",
        }

    app = matches[0]
    candidates = svc.get_launch_candidates(app)
    lines = [
        f"Application: {app['name']}",
        f"Source: {app['source']}",
        f"Launch type: {app['launch_type']}",
        f"Aliases: {', '.join(app['aliases']) or 'none'}",
        f"Executable: {app.get('executable_path') or app.get('executable') or 'none'}",
        f"Shortcut: {app.get('shortcut_path') or 'none'}",
        f"Launch candidates: {len(candidates)}",
    ]
    return {"ok": True, "count": 1, "app": app, "summary": "\n".join(lines)}


# Avoid circular import for shutil
import shutil


# ---------------------------------------------------------------------------
# Tool: open_url
# ---------------------------------------------------------------------------

def open_url(url: str) -> dict:
    """Open a URL in the default system browser."""
    import webbrowser
    raw = url.strip()
    # Normalise bare domains to https://
    if raw and not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    try:
        webbrowser.open(raw)
        logger.info("OPEN_URL URL=%r", raw)
        return {"ok": True, "url": raw, "summary": f"Opening {raw} in your browser."}
    except Exception as exc:
        logger.exception("OPEN_URL failed url=%r: %s", raw, exc)
        return {"ok": False, "url": raw, "error": str(exc), "summary": f"Couldn't open {raw}: {exc}"}


# ---------------------------------------------------------------------------
# Tool: open_target — preference-aware unified resolver
# ---------------------------------------------------------------------------

def open_target(target: str, modifier: str = "") -> dict:
    """Open a named target (website / app / folder) using preference-aware resolution."""
    svc = DesktopService()
    res = svc.resolve_target(target, modifier)
    action = res["action"]

    if action == "open_url":
        result = open_url(res["value"])
        reason = res.get("reason", "")
        label = res.get("label", target)
        result["summary"] = f"Opening {label} in your browser ({res['value']})."
        return result

    if action == "open_app":
        result = open_app(res["value"])
        return result

    if action == "open_location":
        result = open_location(res["value"])
        return result

    # error
    return {
        "ok": False,
        "error": res.get("error", "target_not_found"),
        "target": target,
        "modifier": modifier,
        "summary": res.get("reason", f"Couldn't resolve '{target}'."),
    }


# ---------------------------------------------------------------------------
# Tool: set_launch_preference
# ---------------------------------------------------------------------------

def set_launch_preference(target: str, preferred: str) -> dict:
    """Set the launch preference (web/app/folder/auto) for a named target."""
    svc = DesktopService()
    result = svc.set_launch_preference(target.strip(), preferred.strip())
    if not result["ok"]:
        return {"ok": False, "summary": result.get("error", "Failed to set preference.")}
    return {
        "ok": True,
        "target": result["target"],
        "preferred": result["preferred"],
        "summary": f"Preference for '{result['target']}' set to '{result['preferred']}'.",
    }


# ---------------------------------------------------------------------------
# Tool: show_launch_target
# ---------------------------------------------------------------------------

def show_launch_target(target: str) -> dict:
    """Show all configured targets (web/app/folder) and current preference for a name."""
    svc = DesktopService()
    pref = svc.get_launch_preference(target)
    web_url = svc.resolve_web_url(target)
    app = svc.find_app(target)
    loc = svc.find_location(target)

    lines = [f"Target: {target}"]
    if pref:
        lines.append(f"Preferred: {pref['preferred']}")
    else:
        lines.append("Preferred: auto (no preference set)")

    if web_url:
        lines.append(f"Web: {web_url}")
    else:
        lines.append("Web: none")

    if app:
        lines.append(f"App: {app['name']} ({app.get('executable_path') or app.get('executable') or 'unknown'})")
    else:
        lines.append("App: none registered")

    if loc:
        lines.append(f"Folder: {loc['name']} → {loc['path']}")
    else:
        lines.append("Folder: none registered")

    lines.append("")
    lines.append("Commands:")
    lines.append(f"  prefer {target} web  |  prefer {target} app  |  prefer {target} folder")

    return {
        "ok": True,
        "target": target,
        "preference": pref,
        "web_url": web_url,
        "app": app,
        "location": loc,
        "summary": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Tool: list_launch_preferences
# ---------------------------------------------------------------------------

def list_launch_preferences() -> dict:
    """List all configured launch preferences."""
    svc = DesktopService()
    prefs = svc.list_launch_preferences()
    if not prefs:
        return {
            "ok": True, "count": 0, "prefs": [],
            "summary": "No launch preferences configured.",
        }
    lines = [f"  {p['target']:20s} → {p['preferred']:8s}  {p.get('web_url') or p.get('app_name') or ''}"
             for p in prefs]
    return {
        "ok": True,
        "count": len(prefs),
        "prefs": prefs,
        "summary": f"Launch preferences ({len(prefs)}):\n" + "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Tool: close_app
# ---------------------------------------------------------------------------

def close_app(name: str) -> dict:
    """Gracefully close a running application and verify it actually exited."""
    from backend.app.services.app_lifecycle_service import close_app as _close
    return _close(name)


# ---------------------------------------------------------------------------
# Tool: app_status
# ---------------------------------------------------------------------------

def app_status(name: str) -> dict:
    """Check whether a registered application is currently running."""
    from backend.app.services.app_lifecycle_service import app_status as _status
    return _status(name)


# ---------------------------------------------------------------------------
# Tool: list_running_apps
# ---------------------------------------------------------------------------

def list_running_apps() -> dict:
    """List all registered apps that are currently running."""
    from backend.app.services.app_lifecycle_service import list_running_apps as _list
    return _list()


# ---------------------------------------------------------------------------
# Tool: show_app_runtime
# ---------------------------------------------------------------------------

def show_app_runtime(name: str) -> dict:
    """Show detailed runtime state (PID, window, launch time) for a specific app."""
    from backend.app.services import app_runtime_registry as _rt
    from backend.app.services.app_lifecycle_service import find_processes_for_app, get_windows_for_pids
    from backend.app.services.desktop_service import DesktopService

    svc = DesktopService()
    app = svc.find_app(name)
    if not app:
        return {
            "ok": False,
            "error": "app_not_found",
            "summary": f"'{name}' is not in the application registry.",
        }

    entry = _rt.get(app["name"])
    procs = find_processes_for_app(app)
    pids = [p.pid for p in procs]
    windows = get_windows_for_pids(pids) if pids else []

    if not procs and not entry:
        return {
            "ok": True,
            "name": app["name"],
            "running": False,
            "summary": f"{app['name']} is not running.",
        }

    lines = [
        f"Application: {app['name']}",
        f"State: {'Running' if procs else 'Unknown'}",
        f"PID(s): {pids or 'unknown'}",
    ]
    if windows:
        for w in windows:
            lines.append(f"Window: {w['title']} (hwnd={w['hwnd']}, pid={w['pid']})")
    if entry:
        lines.append(f"Launch Time: {entry.get('launched_at_str', 'unknown')}")
        lines.append(f"Launch Source: {entry.get('launch_source', 'unknown')}")
        lines.append(f"Command: {entry.get('command', 'unknown')}")

    return {
        "ok": True,
        "name": app["name"],
        "running": bool(procs),
        "pids": pids,
        "windows": windows,
        "runtime_entry": entry,
        "summary": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Tool: list_locations
# ---------------------------------------------------------------------------

def list_locations() -> dict:
    svc = DesktopService()
    locs = svc.list_locations()
    if not locs:
        return {"ok": True, "count": 0, "locations": [], "summary": "No trusted locations registered."}
    lines = []
    for l in locs:
        status = "✓" if l["exists"] else "✗"
        aliases = f"  [{', '.join(l['aliases'])}]" if l["aliases"] else ""
        lines.append(f"  {status} {l['name']} — {l['path']}{aliases}")
    summary = f"Trusted locations ({len(locs)}):\n" + "\n".join(lines)
    return {"ok": True, "count": len(locs), "locations": locs, "summary": summary}


# ---------------------------------------------------------------------------
# Tool: list_apps
# ---------------------------------------------------------------------------

def list_apps() -> dict:
    svc = DesktopService()
    apps = svc.list_apps()
    if not apps:
        return {"ok": True, "count": 0, "apps": [], "summary": "No apps registered."}
    by_cat: dict[str, list] = {}
    for a in apps:
        by_cat.setdefault(a["category"], []).append(a)
    lines = []
    for cat, cat_apps in sorted(by_cat.items()):
        lines.append(f"  [{cat}]")
        for a in cat_apps:
            avail = "✓" if a["available"] else "✗"
            lines.append(f"    {avail} {a['name']}")
    summary = f"Registered apps ({len(apps)}):\n" + "\n".join(lines)
    return {"ok": True, "count": len(apps), "apps": apps, "summary": summary}


# ---------------------------------------------------------------------------
# Tool: add_location
# ---------------------------------------------------------------------------

def add_location(
    name: str,
    path: str,
    aliases: str = "",
    tags: str = "",
    description: str = "",
) -> dict:
    """Register a new trusted location."""
    path = path.strip()
    name = name.strip()
    if not name or not path:
        return {"ok": False, "error": "missing_args", "summary": "Name and path are required."}
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    exists = os.path.isdir(path)
    svc = DesktopService()
    loc = svc.add_location(name, path, alias_list, tag_list, description)
    status = "registered" if loc else "failed"
    warning = "" if exists else f" (Warning: path does not currently exist on disk.)"
    return {
        "ok": bool(loc),
        "location": loc,
        "summary": f"Done. {name} {status} at {path}.{warning}",
    }


# ---------------------------------------------------------------------------
# Tool: add_app
# ---------------------------------------------------------------------------

def add_app(
    name: str,
    executable: str,
    aliases: str = "",
    category: str = "general",
    description: str = "",
) -> dict:
    """Register a new application."""
    name = name.strip()
    executable = executable.strip()
    if not name or not executable:
        return {"ok": False, "error": "missing_args", "summary": "Name and executable are required."}
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []
    svc = DesktopService()
    app = svc.add_app(name, executable, alias_list, category, description)
    return {
        "ok": bool(app),
        "app": app,
        "summary": f"Done. {name} registered at {executable}.",
    }
