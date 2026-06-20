"""Workspace Awareness — Phase 16A.

Metadata-based screen awareness for SILVIA. Detects the user's current
engineering context from window titles, process metadata, and workspace
files. No screenshots, OCR, or vision — purely metadata.

Data sources:
  - Win32 foreground window (ctypes)
  - Process list (psutil)
  - VS Code window title pattern: "{file} - {workspace} - Visual Studio Code"
  - KiCad/Fusion/FreeCAD/Bambu title parsing
  - Browser title for engineering sites
  - Git repo detection in project folders
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("silvia.workspace_awareness")

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

# ── Engineering tool classification ─────────────────────────────────────────

_TOOL_MAP: dict[str, dict[str, str]] = {
    "code.exe":            {"app": "VS Code",       "type": "development", "category": "ide"},
    "devenv.exe":          {"app": "Visual Studio",  "type": "development", "category": "ide"},
    "kicad.exe":           {"app": "KiCad",          "type": "pcb_design",  "category": "eda"},
    "pcbnew.exe":          {"app": "KiCad PCB",      "type": "pcb_design",  "category": "eda"},
    "eeschema.exe":        {"app": "KiCad Schematic", "type": "pcb_design", "category": "eda"},
    "fusiondesktop.exe":   {"app": "Fusion 360",     "type": "cad_design",  "category": "cad"},
    "freecad.exe":         {"app": "FreeCAD",        "type": "cad_design",  "category": "cad"},
    "freecadlink.exe":     {"app": "FreeCAD",        "type": "cad_design",  "category": "cad"},
    "openscad.exe":        {"app": "OpenSCAD",       "type": "cad_design",  "category": "cad"},
    "bambu studio.exe":    {"app": "Bambu Studio",   "type": "3d_printing", "category": "slicer"},
    "bambu-studio.exe":    {"app": "Bambu Studio",   "type": "3d_printing", "category": "slicer"},
    "prusa-slicer.exe":    {"app": "PrusaSlicer",    "type": "3d_printing", "category": "slicer"},
    "prusaslicer.exe":     {"app": "PrusaSlicer",    "type": "3d_printing", "category": "slicer"},
    "cura.exe":            {"app": "Cura",           "type": "3d_printing", "category": "slicer"},
    "arduino.exe":         {"app": "Arduino IDE",    "type": "development", "category": "embedded"},
    "arduino ide.exe":     {"app": "Arduino IDE",    "type": "development", "category": "embedded"},
    "platformio-ide.exe":  {"app": "PlatformIO",     "type": "development", "category": "embedded"},
    "obs64.exe":           {"app": "OBS Studio",     "type": "streaming",   "category": "media"},
    "obs32.exe":           {"app": "OBS Studio",     "type": "streaming",   "category": "media"},
    "discord.exe":         {"app": "Discord",        "type": "communication", "category": "chat"},
    "telegram.exe":        {"app": "Telegram",       "type": "communication", "category": "chat"},
    "slack.exe":           {"app": "Slack",          "type": "communication", "category": "chat"},
    "windowsterminal.exe": {"app": "Terminal",       "type": "development", "category": "terminal"},
    "powershell.exe":      {"app": "PowerShell",     "type": "development", "category": "terminal"},
    "cmd.exe":             {"app": "Command Prompt",  "type": "development", "category": "terminal"},
    "firefox.exe":         {"app": "Firefox",        "type": "browsing",    "category": "browser"},
    "chrome.exe":          {"app": "Chrome",         "type": "browsing",    "category": "browser"},
    "msedge.exe":          {"app": "Edge",           "type": "browsing",    "category": "browser"},
    "brave.exe":           {"app": "Brave",          "type": "browsing",    "category": "browser"},
    "notepad++.exe":       {"app": "Notepad++",      "type": "development", "category": "editor"},
    "notepad.exe":         {"app": "Notepad",        "type": "development", "category": "editor"},
    "gimp-2.10.exe":       {"app": "GIMP",           "type": "design",      "category": "graphics"},
    "inkscape.exe":        {"app": "Inkscape",       "type": "design",      "category": "graphics"},
    "blender.exe":         {"app": "Blender",        "type": "3d_modeling",  "category": "3d"},
}

# Engineering websites detected from browser titles
_ENGINEERING_SITES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"github\.com", re.I),         "GitHub",       "development"),
    (re.compile(r"gitlab\.com", re.I),         "GitLab",       "development"),
    (re.compile(r"stackoverflow\.com", re.I),  "StackOverflow", "research"),
    (re.compile(r"mouser\.", re.I),            "Mouser",       "procurement"),
    (re.compile(r"digikey\.", re.I),           "DigiKey",      "procurement"),
    (re.compile(r"aliexpress\.", re.I),        "AliExpress",   "procurement"),
    (re.compile(r"amazon\.", re.I),            "Amazon",       "procurement"),
    (re.compile(r"pcbway\.", re.I),            "PCBWay",       "procurement"),
    (re.compile(r"jlcpcb\.", re.I),            "JLCPCB",       "procurement"),
    (re.compile(r"lcsc\.", re.I),              "LCSC",         "procurement"),
    (re.compile(r"docs\.google\.com", re.I),   "Google Docs",  "documentation"),
    (re.compile(r"notion\.so", re.I),          "Notion",       "documentation"),
    (re.compile(r"obsidian", re.I),            "Obsidian",     "documentation"),
    (re.compile(r"youtube\.com", re.I),        "YouTube",      "media"),
    (re.compile(r"reddit\.com", re.I),         "Reddit",       "research"),
    (re.compile(r"hackaday", re.I),            "Hackaday",     "research"),
    (re.compile(r"instructables", re.I),       "Instructables", "research"),
    (re.compile(r"arduino\.cc", re.I),         "Arduino.cc",   "research"),
    (re.compile(r"platformio\.org", re.I),     "PlatformIO",   "research"),
    (re.compile(r"espressif", re.I),           "Espressif",    "research"),
    (re.compile(r"raspberrypi\.com|raspberrypi\.org", re.I), "Raspberry Pi", "research"),
    (re.compile(r"datasheets?|\.pdf", re.I),   "Datasheet",    "research"),
]

# Session type mapping from dominant tool categories
_SESSION_TYPES: dict[str, str] = {
    "ide":       "Development Session",
    "eda":       "PCB Design Session",
    "cad":       "CAD Session",
    "slicer":    "3D Printing Session",
    "embedded":  "Embedded Development Session",
    "terminal":  "Development Session",
    "browser":   "Research Session",
    "editor":    "Development Session",
    "3d":        "3D Modeling Session",
    "graphics":  "Design Session",
    "media":     "Media Session",
    "chat":      "Communication",
}

# VS Code title pattern: "{file} - {workspace} - Visual Studio Code"
_VSCODE_TITLE_RE = re.compile(
    r"^(?:(?P<file>.+?)\s+[-–—]\s+)?(?P<workspace>.+?)\s+[-–—]\s+Visual Studio Code$",
    re.I,
)

# KiCad title patterns
_KICAD_TITLE_RE = re.compile(
    r"^(?P<tool>Pcbnew|Eeschema|KiCad)\s*[-–—]?\s*(?P<detail>.*)$",
    re.I,
)

# Generic "File - App" pattern
_GENERIC_TITLE_RE = re.compile(
    r"^(?P<file>.+?)\s+[-–—]\s+(?P<app>.+)$",
)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class WorkspaceAwareness:
    """Metadata-based workspace context detection."""

    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspace_context_log (
                    id          TEXT PRIMARY KEY,
                    timestamp   TEXT NOT NULL,
                    app_name    TEXT NOT NULL,
                    window_title TEXT NOT NULL DEFAULT '',
                    project     TEXT NOT NULL DEFAULT '',
                    file_name   TEXT NOT NULL DEFAULT '',
                    tool_type   TEXT NOT NULL DEFAULT '',
                    session_type TEXT NOT NULL DEFAULT '',
                    category    TEXT NOT NULL DEFAULT '',
                    extra       TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_wcl_ts ON workspace_context_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_wcl_project ON workspace_context_log(project);
            """)

    # ── Core: get current context ───────────────────────────────────────────

    def get_context(self) -> dict[str, Any]:
        """Get full current workspace context."""
        fg = self._get_foreground_window()
        running = self._get_engineering_tools()
        session = self._classify_session(fg, running)

        ctx = {
            "active_app": fg.get("app_name", "Unknown"),
            "window_title": fg.get("title", ""),
            "project": fg.get("project", ""),
            "file": fg.get("file", ""),
            "workspace": fg.get("workspace", ""),
            "tool_type": fg.get("tool_type", ""),
            "category": fg.get("category", ""),
            "session_type": session,
            "engineering_context": fg.get("engineering_context", {}),
            "open_tools": running,
            "tool_summary": self._tool_summary(running),
        }

        self._log_context(ctx)
        return ctx

    def get_active_project(self) -> dict[str, Any]:
        """Just the active project info."""
        fg = self._get_foreground_window()
        project = fg.get("project", "")
        registry_match = self._match_project_registry(project) if project else None
        return {
            "project": project,
            "source": fg.get("project_source", "window_title"),
            "app": fg.get("app_name", ""),
            "file": fg.get("file", ""),
            "registry_match": registry_match,
        }

    def get_active_file(self) -> dict[str, Any]:
        """Just the active file info."""
        fg = self._get_foreground_window()
        return {
            "file": fg.get("file", ""),
            "app": fg.get("app_name", ""),
            "project": fg.get("project", ""),
            "language": self._detect_language(fg.get("file", "")),
        }

    def get_active_application(self) -> dict[str, Any]:
        """Just the active application info."""
        fg = self._get_foreground_window()
        return {
            "app": fg.get("app_name", ""),
            "exe": fg.get("exe_name", ""),
            "title": fg.get("title", ""),
            "category": fg.get("category", ""),
            "tool_type": fg.get("tool_type", ""),
            "pid": fg.get("pid", 0),
        }

    def get_recent_sessions(self, hours: int = 24, limit: int = 20) -> list[dict]:
        """Recent context history from the log."""
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - hours * 3600),
        )
        with _conn() as db:
            rows = db.execute(
                """SELECT app_name, project, file_name, tool_type, session_type,
                          category, timestamp, extra
                   FROM workspace_context_log
                   WHERE timestamp >= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_projects(self, hours: int = 24) -> list[dict]:
        """Distinct projects worked on recently, with duration estimates."""
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - hours * 3600),
        )
        with _conn() as db:
            rows = db.execute(
                """SELECT project, COUNT(*) as entries,
                          MIN(timestamp) as first_seen, MAX(timestamp) as last_seen,
                          GROUP_CONCAT(DISTINCT app_name) as apps
                   FROM workspace_context_log
                   WHERE timestamp >= ? AND project != ''
                   GROUP BY project
                   ORDER BY last_seen DESC""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_context_for_assistant(self) -> str:
        """Generate a context string for the assistant to use in responses."""
        ctx = self.get_context()
        parts = []
        if ctx["active_app"]:
            parts.append(f"Active app: {ctx['active_app']}")
        if ctx["project"]:
            parts.append(f"Project: {ctx['project']}")
        if ctx["file"]:
            parts.append(f"File: {ctx['file']}")
        if ctx["session_type"]:
            parts.append(f"Session: {ctx['session_type']}")
        eng = ctx.get("engineering_context", {})
        if eng.get("site"):
            parts.append(f"Site: {eng['site']}")
        if eng.get("activity"):
            parts.append(f"Activity: {eng['activity']}")

        tools = ctx.get("open_tools", [])
        tool_names = list({t["app_name"] for t in tools})
        if tool_names:
            parts.append(f"Open tools: {', '.join(tool_names[:6])}")

        return " | ".join(parts) if parts else "No active context detected."

    # ── Foreground window detection ─────────────────────────────────────────

    def _get_foreground_window(self) -> dict[str, Any]:
        """Get the foreground window's metadata."""
        if sys.platform != "win32":
            return {"app_name": "Unknown", "title": "", "tool_type": "", "category": ""}

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {"app_name": "Unknown", "title": "", "tool_type": "", "category": ""}

            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value.strip()

            pid_out = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
            pid = pid_out.value

            exe_name = ""
            try:
                import psutil
                proc = psutil.Process(pid)
                exe_name = proc.name().lower()
            except Exception:
                pass

            tool_info = _TOOL_MAP.get(exe_name, {})
            app_name = tool_info.get("app", self._app_from_title(title, exe_name))
            tool_type = tool_info.get("type", "other")
            category = tool_info.get("category", "other")

            result = {
                "app_name": app_name,
                "exe_name": exe_name,
                "title": title,
                "pid": pid,
                "tool_type": tool_type,
                "category": category,
                "project": "",
                "file": "",
                "workspace": "",
                "project_source": "",
                "engineering_context": {},
            }

            # App-specific parsing
            if "code.exe" == exe_name:
                self._parse_vscode(result, title)
            elif exe_name in ("kicad.exe", "pcbnew.exe", "eeschema.exe"):
                self._parse_kicad(result, title)
            elif exe_name in ("fusiondesktop.exe", "freecad.exe", "freecadlink.exe", "openscad.exe", "blender.exe"):
                self._parse_cad(result, title)
            elif exe_name in ("bambu studio.exe", "bambu-studio.exe", "prusaslicer.exe", "prusa-slicer.exe", "cura.exe"):
                self._parse_slicer(result, title)
            elif category == "browser":
                self._parse_browser(result, title)
            elif category == "terminal":
                self._parse_terminal(result, title)
            else:
                self._parse_generic(result, title)

            # Try to match project to registry
            if result["project"]:
                match = self._match_project_registry(result["project"])
                if match:
                    result["project"] = match

            return result
        except Exception as e:
            logger.debug("Foreground window detection error: %s", e)
            return {"app_name": "Unknown", "title": "", "tool_type": "", "category": ""}

    # ── App-specific parsers ────────────────────────────────────────────────

    def _parse_vscode(self, result: dict, title: str) -> None:
        """Parse VS Code window title for file, workspace, project."""
        m = _VSCODE_TITLE_RE.match(title)
        if not m:
            return
        file_part = (m.group("file") or "").strip()
        workspace = (m.group("workspace") or "").strip()

        result["file"] = file_part
        result["workspace"] = workspace
        result["project"] = workspace
        result["project_source"] = "vscode_workspace"

        # Detect language from file extension
        if file_part:
            result["engineering_context"]["language"] = self._detect_language(file_part)
            result["engineering_context"]["file_type"] = Path(file_part).suffix.lstrip(".")

        # Check if workspace maps to a git project
        self._try_git_project(result, workspace)

    def _parse_kicad(self, result: dict, title: str) -> None:
        """Parse KiCad window title."""
        m = _KICAD_TITLE_RE.match(title)
        tool_name = "KiCad"
        detail = title
        if m:
            tool_name = m.group("tool").strip()
            detail = m.group("detail").strip()

        result["app_name"] = f"KiCad ({tool_name})"
        result["engineering_context"]["kicad_tool"] = tool_name

        # Try to extract project from detail
        # KiCad titles often include the project file path
        if detail:
            path_match = re.search(r"([A-Za-z]:[/\\].+?\.\w+)", detail)
            if path_match:
                fp = Path(path_match.group(1))
                result["file"] = fp.name
                result["project"] = fp.parent.name
                result["project_source"] = "kicad_filepath"
                result["engineering_context"]["activity"] = "PCB/Schematic editing"
            else:
                result["engineering_context"]["detail"] = detail

    def _parse_cad(self, result: dict, title: str) -> None:
        """Parse CAD tool window title."""
        m = _GENERIC_TITLE_RE.match(title)
        if m:
            result["file"] = m.group("file").strip()
            result["engineering_context"]["activity"] = "CAD modeling"
        # Try to find project from the filename
        if result["file"]:
            name = Path(result["file"]).stem
            result["project"] = name
            result["project_source"] = "cad_filename"

    def _parse_slicer(self, result: dict, title: str) -> None:
        """Parse slicer tool window title."""
        m = _GENERIC_TITLE_RE.match(title)
        if m:
            result["file"] = m.group("file").strip()
            result["engineering_context"]["activity"] = "3D print preparation"
        if result["file"]:
            result["project_source"] = "slicer_filename"

    def _parse_browser(self, result: dict, title: str) -> None:
        """Parse browser title for engineering context."""
        result["engineering_context"]["page_title"] = title

        for pattern, site_name, activity_type in _ENGINEERING_SITES:
            if pattern.search(title):
                result["engineering_context"]["site"] = site_name
                result["engineering_context"]["activity"] = activity_type
                result["tool_type"] = activity_type

                # GitHub: try to extract repo/project
                if site_name == "GitHub":
                    gh_match = re.search(r"github\.com/([^/]+/[^/\s]+)", title, re.I)
                    if not gh_match:
                        gh_match = re.search(r"^([^/]+/[^/\s·–—-]+)", title)
                    if gh_match:
                        repo = gh_match.group(1).strip()
                        result["project"] = repo.split("/")[-1] if "/" in repo else repo
                        result["project_source"] = "github_title"

                # Procurement sites
                if activity_type == "procurement":
                    result["tool_type"] = "procurement"
                    result["session_type"] = "Procurement Session"
                break

    def _parse_terminal(self, result: dict, title: str) -> None:
        """Parse terminal title for project context."""
        # Terminal titles often contain the current directory
        path_match = re.search(r"([A-Za-z]:[/\\][^\s:]+)", title)
        if path_match:
            path = Path(path_match.group(1))
            result["workspace"] = path.name
            result["project"] = path.name
            result["project_source"] = "terminal_cwd"
        # Windows Terminal may show "PowerShell" or a custom title
        if "powershell" in title.lower() or "cmd" in title.lower():
            result["engineering_context"]["activity"] = "command line"

    def _parse_generic(self, result: dict, title: str) -> None:
        """Generic title parsing fallback."""
        m = _GENERIC_TITLE_RE.match(title)
        if m:
            result["file"] = m.group("file").strip()

    # ── Process scanning ────────────────────────────────────────────────────

    def _get_engineering_tools(self) -> list[dict]:
        """List running engineering tools (deduplicated by app name)."""
        seen: set[str] = set()
        tools: list[dict] = []
        try:
            import psutil
            for proc in psutil.process_iter(["pid", "name"]):
                name = (proc.info["name"] or "").lower()
                if name in _TOOL_MAP and name not in seen:
                    seen.add(name)
                    info = _TOOL_MAP[name]
                    tools.append({
                        "app_name": info["app"],
                        "exe": name,
                        "tool_type": info["type"],
                        "category": info["category"],
                        "pid": proc.info["pid"],
                    })
        except Exception as e:
            logger.debug("Process scan error: %s", e)
        return tools

    # ── Session classification ──────────────────────────────────────────────

    def _classify_session(self, fg: dict, running: list[dict]) -> str:
        """Determine the current engineering session type."""
        # Priority: foreground app's category defines the session
        fg_cat = fg.get("category", "")
        if fg_cat and fg_cat in _SESSION_TYPES:
            return _SESSION_TYPES[fg_cat]

        # Fallback: most common category among running tools
        if running:
            cats = [t["category"] for t in running if t["category"] in _SESSION_TYPES]
            if cats:
                from collections import Counter
                most_common = Counter(cats).most_common(1)[0][0]
                return _SESSION_TYPES.get(most_common, "Engineering Session")

        return "General"

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _app_from_title(self, title: str, exe: str) -> str:
        """Guess app name from title or exe."""
        if not title and not exe:
            return "Unknown"
        if exe:
            return exe.replace(".exe", "").title()
        m = _GENERIC_TITLE_RE.match(title)
        if m:
            return m.group("app").strip()
        return title[:40] if title else "Unknown"

    def _detect_language(self, filename: str) -> str:
        """Detect programming language from filename."""
        ext = Path(filename).suffix.lower()
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".jsx": "React/JSX",
            ".ts": "TypeScript", ".tsx": "React/TSX", ".c": "C",
            ".cpp": "C++", ".h": "C/C++ Header", ".rs": "Rust",
            ".go": "Go", ".java": "Java", ".kt": "Kotlin",
            ".swift": "Swift", ".rb": "Ruby", ".php": "PHP",
            ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
            ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
            ".md": "Markdown", ".sql": "SQL", ".sh": "Shell",
            ".ps1": "PowerShell", ".bat": "Batch",
            ".ino": "Arduino", ".pde": "Processing",
        }
        return lang_map.get(ext, ext.lstrip(".").upper() if ext else "")

    def _try_git_project(self, result: dict, workspace: str) -> None:
        """Try to detect project from common workspace paths."""
        common_roots = [
            Path(os.path.expanduser("~")) / "Documents" / "GitHub",
            Path(os.path.expanduser("~")) / "Projects",
            Path(os.path.expanduser("~")) / "dev",
            Path(os.path.expanduser("~")) / "repos",
        ]
        for root in common_roots:
            candidate = root / workspace
            if candidate.exists() and (candidate / ".git").exists():
                result["project_source"] = "git_repo"
                result["engineering_context"]["git_repo"] = str(candidate)
                return

    def _match_project_registry(self, name: str) -> Optional[str]:
        """Try to match a detected project name to the project registry."""
        if not name:
            return None
        try:
            from backend.app.services.project_service import ProjectService
            proj = ProjectService().find_by_name(name)
            if proj:
                return proj.name
        except Exception:
            pass
        return None

    def _tool_summary(self, tools: list[dict]) -> str:
        """Human-readable summary of open engineering tools."""
        if not tools:
            return "No engineering tools detected."
        names = [t["app_name"] for t in tools]
        return f"{len(names)} tool(s) open: {', '.join(names)}"

    # ── Context logging ─────────────────────────────────────────────────────

    def _log_context(self, ctx: dict) -> None:
        """Log current context to the history table."""
        try:
            import json
            with _conn() as db:
                db.execute(
                    """INSERT INTO workspace_context_log
                       (id, timestamp, app_name, window_title, project, file_name,
                        tool_type, session_type, category, extra)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"wc_{uuid.uuid4().hex[:8]}",
                        _now(),
                        ctx.get("active_app", ""),
                        ctx.get("window_title", "")[:200],
                        ctx.get("project", ""),
                        ctx.get("file", ""),
                        ctx.get("tool_type", ""),
                        ctx.get("session_type", ""),
                        ctx.get("category", ""),
                        json.dumps(ctx.get("engineering_context", {})),
                    ),
                )
                # Prune old entries (keep 7 days)
                cutoff = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(time.time() - 7 * 86400),
                )
                db.execute(
                    "DELETE FROM workspace_context_log WHERE timestamp < ?",
                    (cutoff,),
                )
        except Exception as e:
            logger.debug("Context log error: %s", e)


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[WorkspaceAwareness] = None


def get_awareness() -> WorkspaceAwareness:
    global _instance
    if _instance is None:
        _instance = WorkspaceAwareness()
    return _instance
