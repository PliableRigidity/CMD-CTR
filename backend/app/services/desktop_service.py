"""Desktop awareness service — Trusted Locations + App Registry.

Read-only in spirit: discover, navigate, launch. Never delete or modify files.
"""
from __future__ import annotations

import glob as _glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import logging
from pathlib import Path
from typing import Iterable, Optional

from backend.app.services.node_service import DB_PATH, _conn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def _init_desktop_tables() -> None:
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trusted_locations (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                path        TEXT NOT NULL,
                aliases     TEXT NOT NULL DEFAULT '[]',
                tags        TEXT NOT NULL DEFAULT '[]',
                description TEXT
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trusted_locations_name
                ON trusted_locations (LOWER(name));

            CREATE TABLE IF NOT EXISTS app_registry (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                executable  TEXT NOT NULL,
                aliases     TEXT NOT NULL DEFAULT '[]',
                category    TEXT NOT NULL DEFAULT 'general',
                description TEXT,
                normalized_name TEXT,
                executable_path TEXT,
                shortcut_path TEXT,
                launch_command TEXT,
                source TEXT,
                launch_type TEXT NOT NULL DEFAULT 'desktop',
                confidence REAL NOT NULL DEFAULT 0.5,
                last_seen REAL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_app_registry_name
                ON app_registry (LOWER(name));
            CREATE TABLE IF NOT EXISTS file_index (
                path          TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                extension     TEXT NOT NULL DEFAULT '',
                location_id   TEXT NOT NULL,
                location_name TEXT NOT NULL,
                size_bytes    INTEGER,
                modified_ts   REAL,
                indexed_at    REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_file_index_ext
                ON file_index (extension);
            CREATE INDEX IF NOT EXISTS idx_file_index_location
                ON file_index (location_id);
            CREATE INDEX IF NOT EXISTS idx_file_index_modified
                ON file_index (modified_ts);
        """)
        _migrate_app_registry(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_app_registry_normalized ON app_registry (normalized_name)"
        )
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS launch_preferences (
                target      TEXT PRIMARY KEY,
                preferred   TEXT NOT NULL DEFAULT 'auto',
                web_url     TEXT,
                app_name    TEXT,
                folder_name TEXT,
                updated_at  REAL
            );
        """)
        conn.commit()
        _seed_locations(conn)
        _seed_apps(conn)
        _seed_launch_preferences(conn)
        conn.commit()
    finally:
        conn.close()


_USER = str(Path.home())
_GH = str(Path.home() / "Documents" / "GitHub")
_INDEX_TTL_SECONDS = 300
_MAX_INDEX_DEPTH = 6
_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
    "target", ".cargo", ".idea", ".vscode",
}
_EXE_SKIP_WORDS = {
    "unins", "uninstall", "setup", "install", "installer", "update", "updater",
    "crash", "helper", "service", "broker", "reporter", "diagnostic", "repair",
}
_VENDOR_PREFIXES = {
    "autodesk", "microsoft", "google", "apple", "adobe", "jetbrains", "valve",
    "the", "windows",
}
_APP_ALIAS_OVERRIDES = {
    "visual studio code": ["vs code", "vscode", "code"],
    "code": ["vs code", "vscode"],
    "google chrome": ["chrome", "browser"],
    "chrome": ["google chrome", "browser"],
    "autodesk fusion 360": ["fusion 360", "fusion360", "fusion", "f360"],
    "fusion 360": ["fusion360", "fusion", "f360"],
    "obs studio": ["obs"],
    "unity hub": ["unity"],
    "github desktop": ["github"],
}
_WEB_ALIASES: dict[str, str] = {
    # Dev & code hosting
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "bitbucket": "https://bitbucket.org",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "npm": "https://npmjs.com",
    "pypi": "https://pypi.org",
    # AI & tools
    "chatgpt": "https://chatgpt.com",
    "chat gpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "openai": "https://openai.com",
    "anthropic": "https://anthropic.com",
    "huggingface": "https://huggingface.co",
    "hugging face": "https://huggingface.co",
    "perplexity": "https://perplexity.ai",
    # Productivity
    "notion": "https://notion.so",
    "linear": "https://linear.app",
    "figma": "https://figma.com",
    "miro": "https://miro.com",
    "trello": "https://trello.com",
    "jira": "https://jira.atlassian.com",
    "confluence": "https://confluence.atlassian.com",
    # Google suite
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "calendar": "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "google": "https://google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "sheets": "https://sheets.google.com",
    "google slides": "https://slides.google.com",
    "slides": "https://slides.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "meet": "https://meet.google.com",
    "google meet": "https://meet.google.com",
    # Media
    "youtube": "https://youtube.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://netflix.com",
    "twitch": "https://twitch.tv",
    "soundcloud": "https://soundcloud.com",
    # Social & communication
    "discord": "https://discord.com",
    "reddit": "https://reddit.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "linkedin": "https://linkedin.com",
    "instagram": "https://instagram.com",
    # Shopping
    "amazon": "https://amazon.com",
    "ebay": "https://ebay.com",
    # Cloud & infra
    "vercel": "https://vercel.com",
    "netlify": "https://netlify.com",
    "heroku": "https://heroku.com",
    "aws": "https://aws.amazon.com",
    "gcp": "https://console.cloud.google.com",
    "azure": "https://portal.azure.com",
    "cloudflare": "https://cloudflare.com",
    "digitalocean": "https://digitalocean.com",
}
# Keep old name for backwards compat
_WEB_PREFERRED = _WEB_ALIASES
_URI_COMMANDS: dict[str, str] = {}


def _migrate_app_registry(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(app_registry)").fetchall()
    }
    columns = {
        "normalized_name": "TEXT",
        "executable_path": "TEXT",
        "shortcut_path": "TEXT",
        "launch_command": "TEXT",
        "source": "TEXT",
        "launch_type": "TEXT NOT NULL DEFAULT 'desktop'",
        "confidence": "REAL NOT NULL DEFAULT 0.5",
        "last_seen": "REAL",
    }
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE app_registry ADD COLUMN {name} {ddl}")
    conn.execute(
        "UPDATE app_registry SET normalized_name=LOWER(name) WHERE normalized_name IS NULL OR normalized_name=''"
    )
    conn.execute(
        "UPDATE app_registry SET executable_path=executable WHERE (executable_path IS NULL OR executable_path='') AND executable != ''"
    )
    conn.execute(
        "UPDATE app_registry SET source='seeded' WHERE source IS NULL OR source=''"
    )
    conn.execute(
        "UPDATE app_registry SET last_seen=? WHERE last_seen IS NULL",
        (time.time(),),
    )


def _seed_locations(conn: sqlite3.Connection) -> None:
    seeds = [
        {
            "id": "loc-cmd-ctr",
            "name": "CMD-CTR",
            "path": rf"{_GH}\CMD-CTR",
            "aliases": json.dumps(["command center", "silvia", "cmdctr", "cmd ctr"]),
            "tags": json.dumps(["project", "code", "ai"]),
            "description": "SILVIA Command Center repository",
        },
        {
            "id": "loc-brain63",
            "name": "Brain63",
            "path": rf"{_GH}\Brain63",
            "aliases": json.dumps(["brain", "notes", "vault", "obsidian", "brain 63"]),
            "tags": json.dumps(["notes", "knowledge", "obsidian"]),
            "description": "Obsidian knowledge vault",
        },
        {
            "id": "loc-dronehive",
            "name": "DroneHive",
            "path": rf"{_GH}\DroneHive",
            "aliases": json.dumps(["drone hive", "drone", "hive", "drones"]),
            "tags": json.dumps(["project", "robotics", "code"]),
            "description": "DroneHive robotics project",
        },
        {
            "id": "loc-cyberdeck",
            "name": "Cyberdeck",
            "path": rf"{_GH}\Cyberdeck",
            "aliases": json.dumps(["cyber deck", "deck"]),
            "tags": json.dumps(["project", "hardware", "portable"]),
            "description": "Cyberdeck project folder",
        },
        {
            "id": "loc-university",
            "name": "University",
            "path": rf"{_USER}\Documents\University",
            "aliases": json.dumps(["uni", "coursework", "school"]),
            "tags": json.dumps(["study", "documents"]),
            "description": "University documents and coursework",
        },
        {
            "id": "loc-internship",
            "name": "Internship",
            "path": rf"{_USER}\Documents\Internship",
            "aliases": json.dumps(["work placement", "placement", "work"]),
            "tags": json.dumps(["work", "documents"]),
            "description": "Internship documents and notes",
        },
        {
            "id": "loc-koi",
            "name": "KOI",
            "path": rf"{_GH}\KOI",
            "aliases": json.dumps(["koi project"]),
            "tags": json.dumps(["project", "code"]),
            "description": "KOI project",
        },
        {
            "id": "loc-magi",
            "name": "MAGI",
            "path": rf"{_GH}\MAGI",
            "aliases": json.dumps(["magi project"]),
            "tags": json.dumps(["project", "code", "ai"]),
            "description": "MAGI project",
        },
        {
            "id": "loc-downloads",
            "name": "Downloads",
            "path": rf"{_USER}\Downloads",
            "aliases": json.dumps(["download"]),
            "tags": json.dumps(["files", "system"]),
            "description": "Downloads folder",
        },
        {
            "id": "loc-documents",
            "name": "Documents",
            "path": rf"{_USER}\Documents",
            "aliases": json.dumps(["docs", "my documents"]),
            "tags": json.dumps(["files", "system"]),
            "description": "Documents folder",
        },
        {
            "id": "loc-desktop",
            "name": "Desktop",
            "path": rf"{_USER}\Desktop",
            "aliases": json.dumps([]),
            "tags": json.dumps(["files", "system"]),
            "description": "Desktop",
        },
        {
            "id": "loc-github",
            "name": "GitHub",
            "path": _GH,
            "aliases": json.dumps(["projects", "repos", "repositories", "code"]),
            "tags": json.dumps(["code", "projects"]),
            "description": "GitHub projects folder",
        },
    ]
    for s in seeds:
        conn.execute(
            """INSERT OR IGNORE INTO trusted_locations
               (id, name, path, aliases, tags, description)
               VALUES (:id, :name, :path, :aliases, :tags, :description)""",
            s,
        )


def _normalize_app_name(value: str) -> str:
    text = value.lower()
    text = re.sub(r"\.(lnk|exe|appref-ms)$", "", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def generate_app_aliases(name: str, extra: Iterable[str] | None = None) -> list[str]:
    """Generate useful launch aliases without requiring per-app hardcoding."""
    normalized = _normalize_app_name(name)
    aliases: set[str] = {normalized} if normalized else set()
    words = normalized.split()

    compact = _compact_alias(normalized)
    if compact and compact != normalized:
        aliases.add(compact)

    if len(words) > 1:
        acronym = "".join(word[0] for word in words if word)
        if len(acronym) >= 2:
            aliases.add(acronym)

    if words and words[0] in _VENDOR_PREFIXES and len(words) > 1:
        vendorless = " ".join(words[1:])
        aliases.add(vendorless)
        aliases.add(_compact_alias(vendorless))

    for suffix in (" app", " application", " launcher"):
        if normalized.endswith(suffix):
            aliases.add(normalized[: -len(suffix)].strip())

    for key, values in _APP_ALIAS_OVERRIDES.items():
        if normalized == key or normalized.endswith(f" {key}"):
            aliases.update(values)

    for item in extra or []:
        item_norm = _normalize_app_name(item)
        if item_norm:
            aliases.add(item_norm)
            aliases.add(_compact_alias(item_norm))

    aliases.discard("")
    return sorted(aliases, key=lambda item: (len(item), item))


def _seed_apps(conn: sqlite3.Connection) -> None:
    seeds = [
        {
            "id": "app-vscode",
            "name": "VS Code",
            "executable": rf"{_USER}\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd",
            "aliases": json.dumps(["vscode", "code", "visual studio code", "editor"]),
            "category": "development",
            "description": "Visual Studio Code editor",
        },
        {
            "id": "app-fusion360",
            "name": "Fusion 360",
            "executable": "fusion360",
            "aliases": json.dumps(["fusion", "f360", "cad", "autodesk"]),
            "category": "cad",
            "description": "Autodesk Fusion 360 CAD/CAM",
        },
        {
            "id": "app-chrome",
            "name": "Chrome",
            "executable": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "aliases": json.dumps(["browser", "google chrome", "google"]),
            "category": "browser",
            "description": "Google Chrome browser",
        },
        {
            "id": "app-kicad",
            "name": "KiCad",
            "executable": r"C:\Program Files\KiCad\9.0\bin\kicad.exe",
            "aliases": json.dumps(["kicad", "pcb", "schematic", "electronics"]),
            "category": "electronics",
            "description": "KiCad PCB design suite",
        },
        {
            "id": "app-explorer",
            "name": "Explorer",
            "executable": "explorer",
            "aliases": json.dumps(["file explorer", "files", "file manager", "windows explorer"]),
            "category": "system",
            "description": "Windows File Explorer",
        },
        {
            "id": "app-notepad",
            "name": "Notepad",
            "executable": "notepad",
            "aliases": json.dumps(["text editor", "notepad", "txt"]),
            "category": "system",
            "description": "Windows Notepad",
        },
    ]
    for s in seeds:
        normalized = _normalize_app_name(s["name"])
        conn.execute(
            """INSERT OR IGNORE INTO app_registry
               (id, name, executable, aliases, category, description, normalized_name,
                executable_path, source, launch_type, confidence, last_seen)
               VALUES (:id, :name, :executable, :aliases, :category, :description, :normalized_name,
                :executable_path, 'seeded', 'desktop', 0.8, :last_seen)""",
            {
                **s,
                "normalized_name": normalized,
                "executable_path": s["executable"],
                "last_seen": time.time(),
            },
        )


def _seed_launch_preferences(conn: sqlite3.Connection) -> None:
    """Seed per-target launch preferences (preferred=web for web-first services)."""
    seeds = [
        # web-first targets — "open github" opens the website by default
        ("github",    "web",  "https://github.com",         "GitHub Desktop", "GitHub"),
        ("gmail",     "web",  "https://mail.google.com",    None, None),
        ("youtube",   "web",  "https://youtube.com",        None, None),
        ("chatgpt",   "web",  "https://chatgpt.com",        None, None),
        ("claude",    "web",  "https://claude.ai",          None, None),
        ("notion",    "web",  "https://notion.so",          None, None),
        ("linear",    "web",  "https://linear.app",         None, None),
        ("figma",     "web",  "https://figma.com",          None, None),
        ("reddit",    "web",  "https://reddit.com",         None, None),
        ("twitter",   "web",  "https://twitter.com",        None, None),
        ("x",         "web",  "https://x.com",              None, None),
        # app-first targets with web fallback
        ("spotify",   "auto", "https://open.spotify.com",   "Spotify", None),
        ("discord",   "auto", "https://discord.com",        "Discord", None),
        ("steam",     "auto", None,                          "Steam",   None),
        ("obs",       "auto", None,                          "OBS Studio", None),
    ]
    for target, preferred, web_url, app_name, folder_name in seeds:
        conn.execute(
            """INSERT OR IGNORE INTO launch_preferences
               (target, preferred, web_url, app_name, folder_name, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (target, preferred, web_url, app_name, folder_name, time.time()),
        )


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------

def _row_to_location(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "path": row["path"],
        "aliases": json.loads(row["aliases"] or "[]"),
        "tags": json.loads(row["tags"] or "[]"),
        "description": row["description"] or "",
        "exists": os.path.isdir(row["path"]),
    }


def _row_to_app(row: sqlite3.Row) -> dict:
    keys = set(row.keys())
    exe = row["executable"]
    executable_path = row["executable_path"] if "executable_path" in keys else exe
    shortcut_path = row["shortcut_path"] if "shortcut_path" in keys else ""
    launch_command = row["launch_command"] if "launch_command" in keys else ""
    return {
        "id": row["id"],
        "name": row["name"],
        "normalized_name": row["normalized_name"] if "normalized_name" in keys else _normalize_app_name(row["name"]),
        "executable": exe,
        "executable_path": executable_path or "",
        "shortcut_path": shortcut_path or "",
        "launch_command": launch_command or "",
        "aliases": json.loads(row["aliases"] or "[]"),
        "category": row["category"],
        "description": row["description"] or "",
        "source": row["source"] if "source" in keys and row["source"] else "manual",
        "launch_type": row["launch_type"] if "launch_type" in keys and row["launch_type"] else "desktop",
        "confidence": float(row["confidence"] if "confidence" in keys and row["confidence"] is not None else 0.5),
        "last_seen": row["last_seen"] if "last_seen" in keys else None,
        "available": _check_app_available(executable_path or exe, row["name"], shortcut_path, launch_command),
    }


def _check_app_available(
    executable: str,
    name: str = "",
    shortcut_path: str = "",
    launch_command: str = "",
) -> bool:
    name_lower = name.lower()
    if shortcut_path and os.path.isfile(shortcut_path):
        return True
    if launch_command and _looks_like_uri(launch_command):
        return True
    if executable == "fusion360":
        return bool(_resolve_fusion360())
    if executable == "kicad" or name_lower == "kicad":
        return bool(_resolve_kicad())
    if executable == "code" or name_lower == "vs code":
        return bool(_resolve_vscode())
    if executable == "chrome" or name_lower == "chrome":
        return bool(_resolve_chrome())
    if executable in ("explorer", "notepad"):
        return True
    if os.path.isfile(executable):
        return True
    return shutil.which(executable) is not None


def _resolve_fusion360() -> Optional[str]:
    """Find the latest Fusion 360 launcher via glob."""
    pattern = str(Path.home() / "AppData" / "Local" / "Autodesk" / "webdeploy" / "production" / "*" / "FusionLauncher.exe")
    candidates = _glob.glob(pattern)
    if not candidates:
        return None
    return sorted(candidates, key=os.path.getmtime)[-1]


def _resolve_kicad() -> Optional[str]:
    candidates = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.extend(_glob.glob(str(Path(base) / "KiCad" / "*" / "bin" / "kicad.exe")))
            candidates.extend(_glob.glob(str(Path(base) / "KiCad" / "bin" / "kicad.exe")))
    candidates = [c for c in candidates if os.path.isfile(c)]
    if candidates:
        return sorted(candidates, key=os.path.getmtime)[-1]
    return shutil.which("kicad")


def _resolve_vscode() -> Optional[str]:
    candidates = [
        Path.home() / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd",
        Path.home() / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "Code.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("code") or shutil.which("code.cmd")


def _resolve_chrome() -> Optional[str]:
    candidates = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.append(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("chrome")


def _looks_like_uri(value: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9+.-]*:", value.strip(), re.I))


def _clean_icon_path(value: str) -> str:
    text = (value or "").strip().strip('"')
    if not text:
        return ""
    if "," in text:
        possible_path = text.rsplit(",", 1)[0].strip().strip('"')
        if possible_path.lower().endswith(".exe"):
            return possible_path
    return text


def _shortcut_roots() -> list[Path]:
    roots = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData"))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("Public", r"C:\Users\Public")) / "Desktop",
    ]
    return [root for root in roots if root.exists()]


def _common_install_roots() -> list[Path]:
    candidates = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        str(Path.home() / "AppData" / "Local"),
        str(Path.home() / "AppData" / "Roaming"),
    ]
    return [Path(root) for root in candidates if root and Path(root).exists()]


def _iter_shortcut_apps() -> Iterable[dict]:
    for root in _shortcut_roots():
        for shortcut in root.rglob("*"):
            if shortcut.suffix.lower() not in {".lnk", ".appref-ms", ".url"}:
                continue
            name = shortcut.stem.strip()
            if not name:
                continue
            launch_type = "url" if shortcut.suffix.lower() == ".url" else "shortcut"
            yield {
                "name": name,
                "executable_path": "",
                "shortcut_path": str(shortcut),
                "launch_command": str(shortcut),
                "source": "Start Menu Shortcut" if "Start Menu" in str(shortcut) else "Desktop Shortcut",
                "launch_type": launch_type,
                "confidence": 0.9,
                "description": f"Discovered from {shortcut}",
            }


def _iter_registry_apps() -> Iterable[dict]:
    if os.name != "nt":
        return
    try:
        import winreg
    except ImportError:
        return

    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, key_path in hives:
        try:
            root_key = winreg.OpenKey(hive, key_path)
        except OSError:
            continue
        with root_key:
            try:
                count = winreg.QueryInfoKey(root_key)[0]
            except OSError:
                continue
            for index in range(count):
                try:
                    subkey_name = winreg.EnumKey(root_key, index)
                    subkey = winreg.OpenKey(root_key, subkey_name)
                except OSError:
                    continue
                with subkey:
                    values: dict[str, str] = {}
                    for value_name in ("DisplayName", "DisplayIcon", "InstallLocation", "Publisher"):
                        try:
                            values[value_name] = str(winreg.QueryValueEx(subkey, value_name)[0])
                        except OSError:
                            pass
                    name = values.get("DisplayName", "").strip()
                    if not name:
                        continue
                    display_icon = _clean_icon_path(values.get("DisplayIcon", ""))
                    executable = display_icon if display_icon.lower().endswith(".exe") and os.path.isfile(display_icon) else ""
                    yield {
                        "name": name,
                        "executable_path": executable,
                        "shortcut_path": "",
                        "launch_command": executable,
                        "source": "Windows Registry",
                        "launch_type": "desktop",
                        "confidence": 0.75 if executable else 0.55,
                        "description": f"Installed application{f' by {values.get("Publisher")}' if values.get('Publisher') else ''}",
                    }


def _exe_name_is_launchable(path: Path) -> bool:
    stem = path.stem.lower()
    if any(word in stem for word in _EXE_SKIP_WORDS):
        return False
    return path.is_file() and path.suffix.lower() == ".exe"


def _iter_common_path_apps(max_depth: int = 3, max_dirs: int = 1200) -> Iterable[dict]:
    scanned_dirs = 0
    for root in _common_install_roots():
        root_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            scanned_dirs += 1
            if scanned_dirs > max_dirs:
                return
            path = Path(dirpath)
            depth = len(path.parts) - root_depth
            if depth >= max_depth:
                dirnames.clear()
            dirnames[:] = [
                item for item in dirnames
                if item not in _SKIP_DIRS and not item.startswith(".")
            ]
            launchable = [path / filename for filename in filenames if _exe_name_is_launchable(path / filename)]
            if not launchable:
                continue
            preferred = sorted(
                launchable,
                key=lambda exe: (
                    exe.stem.lower() not in path.name.lower(),
                    len(exe.name),
                ),
            )[0]
            display_name = path.name if path.name.lower() not in {"bin", "app", "program"} else preferred.stem
            yield {
                "name": display_name,
                "executable_path": str(preferred),
                "shortcut_path": "",
                "launch_command": str(preferred),
                "source": "Common Install Path",
                "launch_type": "desktop",
                "confidence": 0.5,
                "description": f"Discovered executable at {preferred}",
            }


def _walk_files(root: str, max_depth: int = _MAX_INDEX_DEPTH):
    root_path = os.path.abspath(root).rstrip(os.sep)
    root_depth = root_path.count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root_path):
        depth = dirpath.count(os.sep) - root_depth
        if depth >= max_depth:
            dirnames.clear()
            continue
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        yield dirpath, filenames


def _format_mtime(timestamp: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
    except (OSError, ValueError):
        return ""


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 ** 2:.1f} MB"


def _row_to_indexed_file(row: sqlite3.Row) -> dict:
    return {
        "name": row["name"],
        "path": row["path"],
        "extension": row["extension"],
        "location": row["location_name"],
        "size": _format_size(int(row["size_bytes"] or 0)),
        "modified": _format_mtime(float(row["modified_ts"] or 0)),
    }


# ---------------------------------------------------------------------------
# DesktopService
# ---------------------------------------------------------------------------

class DesktopService:
    def __init__(self) -> None:
        _init_desktop_tables()

    # ── Locations ─────────────────────────────────────────────────────────────

    def list_locations(self) -> list[dict]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM trusted_locations ORDER BY name"
            ).fetchall()
            return [_row_to_location(r) for r in rows]
        finally:
            conn.close()

    def find_location(self, name: str) -> Optional[dict]:
        """Find a location by name or alias (case-insensitive)."""
        name_lower = name.strip().lower()
        conn = _conn()
        try:
            # Exact name match first
            row = conn.execute(
                "SELECT * FROM trusted_locations WHERE LOWER(name)=?", (name_lower,)
            ).fetchone()
            if row:
                return _row_to_location(row)
            # Alias match — scan all (small table, no perf issue)
            rows = conn.execute("SELECT * FROM trusted_locations").fetchall()
            for r in rows:
                aliases = json.loads(r["aliases"] or "[]")
                if any(a.lower() == name_lower for a in aliases):
                    return _row_to_location(r)
            # Partial name match (prefix)
            row = conn.execute(
                "SELECT * FROM trusted_locations WHERE LOWER(name) LIKE ? ORDER BY LENGTH(name) LIMIT 1",
                (f"{name_lower}%",),
            ).fetchone()
            if row:
                return _row_to_location(row)
            return None
        finally:
            conn.close()

    def add_location(
        self,
        name: str,
        path: str,
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        description: str = "",
    ) -> dict:
        loc_id = str(uuid.uuid4())
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO trusted_locations (id, name, path, aliases, tags, description)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(LOWER(name)) DO UPDATE SET
                     path=excluded.path,
                     aliases=excluded.aliases,
                     tags=excluded.tags,
                     description=excluded.description""",
                (
                    loc_id, name, path,
                    json.dumps(aliases or []),
                    json.dumps(tags or []),
                    description,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM trusted_locations WHERE LOWER(name)=LOWER(?)", (name,)
            ).fetchone()
            return _row_to_location(row) if row else {}
        finally:
            conn.close()

    def delete_location(self, name: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute(
                "DELETE FROM trusted_locations WHERE LOWER(name)=LOWER(?)", (name,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ── Apps ──────────────────────────────────────────────────────────────────

    def list_apps(self) -> list[dict]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM app_registry ORDER BY category, confidence DESC, name"
            ).fetchall()
            return [_row_to_app(r) for r in rows]
        finally:
            conn.close()

    def scan_installed_apps(self) -> dict:
        """Discover installed Windows apps and persist them into app_registry."""
        discovered: dict[str, dict] = {}
        sources = (
            _iter_shortcut_apps(),
            _iter_registry_apps() or [],
            _iter_common_path_apps(),
        )
        for source in sources:
            for item in source:
                normalized = _normalize_app_name(item["name"])
                if not normalized:
                    continue
                current = discovered.get(normalized)
                if not current or item.get("confidence", 0) > current.get("confidence", 0):
                    discovered[normalized] = item

        saved = 0
        conn = _conn()
        try:
            for item in discovered.values():
                self._upsert_discovered_app(conn, item)
                saved += 1
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "APP_SCAN Sources=%r Discovered=%d Saved=%d",
            ["Start Menu", "Desktop", "Registry", "Common Install Paths"],
            len(discovered),
            saved,
        )
        return {
            "ok": True,
            "count": saved,
            "summary": f"Scanned installed applications and updated {saved} registry entries.",
        }

    def _upsert_discovered_app(self, conn: sqlite3.Connection, item: dict) -> None:
        name = item["name"].strip()
        normalized = _normalize_app_name(name)
        aliases = generate_app_aliases(name, item.get("aliases", []))
        executable_path = item.get("executable_path") or ""
        shortcut_path = item.get("shortcut_path") or ""
        launch_command = item.get("launch_command") or shortcut_path or executable_path
        source = item.get("source") or "discovered"
        launch_type = item.get("launch_type") or "desktop"
        confidence = float(item.get("confidence", 0.5))
        now = time.time()

        existing = conn.execute(
            "SELECT * FROM app_registry WHERE normalized_name=? OR LOWER(name)=LOWER(?)",
            (normalized, name),
        ).fetchone()
        if existing:
            existing_app = _row_to_app(existing)
            if existing_app.get("source") in {"manual", "seeded"}:
                merged_aliases = sorted(set(existing_app["aliases"]) | set(aliases))
            else:
                merged_aliases = aliases
            conn.execute(
                """UPDATE app_registry SET
                     aliases=?,
                     executable=?,
                     executable_path=?,
                     shortcut_path=?,
                     launch_command=?,
                     source=?,
                     launch_type=?,
                     confidence=MAX(confidence, ?),
                     last_seen=?
                   WHERE id=?""",
                (
                    json.dumps(merged_aliases),
                    executable_path or existing_app.get("executable") or launch_command,
                    executable_path or existing_app.get("executable_path", ""),
                    shortcut_path or existing_app.get("shortcut_path", ""),
                    launch_command or existing_app.get("launch_command", ""),
                    source,
                    launch_type,
                    confidence,
                    now,
                    existing["id"],
                ),
            )
            return

        conn.execute(
            """INSERT INTO app_registry
               (id, name, executable, aliases, category, description, normalized_name,
                executable_path, shortcut_path, launch_command, source, launch_type, confidence, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                name,
                executable_path or launch_command,
                json.dumps(aliases),
                item.get("category", "discovered"),
                item.get("description", ""),
                normalized,
                executable_path,
                shortcut_path,
                launch_command,
                source,
                launch_type,
                confidence,
                now,
            ),
        )

    def find_app_matches(self, name: str, limit: int = 8) -> list[dict]:
        query = _normalize_app_name(name)
        if not query:
            return []
        compact_query = _compact_alias(query)
        rows: list[sqlite3.Row]
        conn = _conn()
        try:
            rows = conn.execute("SELECT * FROM app_registry").fetchall()
        finally:
            conn.close()

        scored: list[tuple[int, dict]] = []
        for row in rows:
            app = _row_to_app(row)
            candidates = {
                app["normalized_name"],
                _compact_alias(app["normalized_name"]),
                *[_normalize_app_name(alias) for alias in app["aliases"]],
                *[_compact_alias(alias) for alias in app["aliases"]],
            }
            score = 0
            if query == app["normalized_name"] or compact_query == _compact_alias(app["normalized_name"]):
                score = 100
            elif query in candidates or compact_query in candidates:
                score = 95
            elif any(candidate.startswith(query) for candidate in candidates if candidate):
                score = 80
            elif any(query in candidate or compact_query in candidate for candidate in candidates if candidate):
                score = 65
            if score:
                scored.append((score + int(app["confidence"] * 10), app))

        scored.sort(key=lambda item: (-item[0], item[1]["name"].lower()))
        if len(scored) > 1 and scored[0][0] - scored[1][0] < 5:
            return [app for _, app in scored[:limit]]
        return [app for _, app in scored[:limit]]

    def find_app(self, name: str) -> Optional[dict]:
        matches = self.find_app_matches(name, limit=1)
        return matches[0] if matches else None

    def add_app(
        self,
        name: str,
        executable: str,
        aliases: list[str] | None = None,
        category: str = "general",
        description: str = "",
    ) -> dict:
        app_id = str(uuid.uuid4())
        normalized = _normalize_app_name(name)
        alias_list = sorted(set(aliases or []) | set(generate_app_aliases(name)))
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO app_registry
                   (id, name, executable, aliases, category, description, normalized_name,
                    executable_path, launch_command, source, launch_type, confidence, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(LOWER(name)) DO UPDATE SET
                     executable=excluded.executable,
                     executable_path=excluded.executable_path,
                     launch_command=excluded.launch_command,
                     aliases=excluded.aliases,
                     category=excluded.category,
                     description=excluded.description,
                     normalized_name=excluded.normalized_name,
                     source=excluded.source,
                     launch_type=excluded.launch_type,
                     confidence=excluded.confidence,
                     last_seen=excluded.last_seen""",
                (
                    app_id, name, executable,
                    json.dumps(alias_list),
                    category, description,
                    normalized,
                    executable if executable.lower().endswith(".exe") or os.path.isfile(executable) else "",
                    executable,
                    "manual",
                    "desktop",
                    0.95,
                    time.time(),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM app_registry WHERE LOWER(name)=LOWER(?)", (name,)
            ).fetchone()
            return _row_to_app(row) if row else {}
        finally:
            conn.close()

    def delete_app(self, name: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute(
                "DELETE FROM app_registry WHERE LOWER(name)=LOWER(?)", (name,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def resolve_app_executable(self, app: dict) -> Optional[str]:
        exe = app.get("executable_path") or app.get("executable", "")
        name = app.get("name", "").lower()
        if exe == "fusion360":
            return _resolve_fusion360()
        if exe == "kicad" or name == "kicad":
            return _resolve_kicad()
        if exe == "code" or name == "vs code":
            return _resolve_vscode()
        if exe == "chrome" or name == "chrome":
            return _resolve_chrome()
        if exe in ("explorer", "notepad"):
            return exe
        if os.path.isfile(exe):
            return exe
        found = shutil.which(exe)
        return found

    def get_launch_candidates(self, app: dict, prefer_web: bool = False) -> list[dict]:
        normalized = app.get("normalized_name") or _normalize_app_name(app.get("name", ""))
        candidates: list[dict] = []
        web_url = _WEB_PREFERRED.get(normalized)
        uri = _URI_COMMANDS.get(normalized)

        if prefer_web and web_url:
            candidates.append({"type": "web", "command": web_url})
        if app.get("shortcut_path") and os.path.isfile(app["shortcut_path"]):
            candidates.append({"type": "shortcut", "command": app["shortcut_path"]})

        exe = self.resolve_app_executable(app)
        if exe:
            candidates.append({"type": "executable", "command": exe})

        launch_command = app.get("launch_command") or app.get("executable") or ""
        if launch_command and launch_command not in {c["command"] for c in candidates}:
            if _looks_like_uri(launch_command):
                candidates.append({"type": "uri", "command": launch_command})
            elif os.path.isfile(launch_command) or shutil.which(launch_command):
                candidates.append({"type": "command", "command": launch_command})

        if uri and uri not in {c["command"] for c in candidates}:
            candidates.append({"type": "uri", "command": uri})
        if not prefer_web and web_url:
            candidates.append({"type": "web", "command": web_url})

        return candidates

    # Launch Preferences ----------------------------------------------------

    def _norm_target(self, target: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", target.lower()).strip()

    def get_launch_preference(self, target: str) -> Optional[dict]:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM launch_preferences WHERE target=?",
                (self._norm_target(target),),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_launch_preference(
        self,
        target: str,
        preferred: str,
        web_url: str = "",
        app_name: str = "",
        folder_name: str = "",
    ) -> dict:
        norm = self._norm_target(target)
        valid = {"web", "app", "desktop", "folder", "auto"}
        if preferred not in valid:
            return {"ok": False, "error": f"preferred must be one of {valid}"}
        # Normalise desktop → app
        if preferred == "desktop":
            preferred = "app"
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO launch_preferences (target, preferred, web_url, app_name, folder_name, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(target) DO UPDATE SET
                     preferred=excluded.preferred,
                     web_url=COALESCE(NULLIF(excluded.web_url,''), web_url),
                     app_name=COALESCE(NULLIF(excluded.app_name,''), app_name),
                     folder_name=COALESCE(NULLIF(excluded.folder_name,''), folder_name),
                     updated_at=excluded.updated_at""",
                (norm, preferred, web_url, app_name, folder_name, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "target": norm, "preferred": preferred}

    def list_launch_preferences(self) -> list[dict]:
        conn = _conn()
        try:
            rows = conn.execute("SELECT * FROM launch_preferences ORDER BY target").fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def resolve_web_url(self, target: str) -> str:
        """Return the web URL for a target name (alias dict first, then DB preference)."""
        norm = self._norm_target(target)
        # 1. In-memory web alias dict
        url = _WEB_ALIASES.get(norm, "")
        if url:
            return url
        # 2. DB preference record
        pref = self.get_launch_preference(target)
        if pref and pref.get("web_url"):
            return pref["web_url"]
        # 3. Try treating the target as a bare domain
        if re.match(r"^[a-z0-9][-a-z0-9]*\.[a-z]{2,}", norm):
            return "https://" + norm
        return ""

    def resolve_target(self, target: str, modifier: str = "") -> dict:
        """Unified launcher resolution with preference-aware priority.

        Returns {"action": "open_url"|"open_app"|"open_location"|"error", ...}
        """
        mod = modifier.lower().strip()
        want_web = mod in {"web", "site", "browser", "online", "website"}
        want_app = mod in {"app", "application", "desktop", "program"}
        want_folder = mod in {"folder", "directory", "dir", "repo", "repository", "project"}

        # --- Explicit web ---
        if want_web:
            url = self.resolve_web_url(target)
            if not url:
                url = f"https://{target.lower().strip()}"
            return {"action": "open_url", "value": url, "label": target, "reason": "web_modifier"}

        # --- Explicit app ---
        if want_app:
            app = self.find_app(target)
            if app:
                return {"action": "open_app", "value": app["name"], "label": app["name"], "reason": "app_modifier"}
            return {"action": "error", "error": "app_not_found", "label": target,
                    "reason": f"No app named '{target}' in the registry. Try 'rescan apps'."}

        # --- Explicit folder ---
        if want_folder:
            loc = self.find_location(target)
            if loc:
                return {"action": "open_location", "value": loc["name"], "label": loc["name"], "reason": "folder_modifier"}
            return {"action": "error", "error": "location_not_found", "label": target,
                    "reason": f"No location named '{target}' in trusted locations."}

        # --- No modifier: check preference registry ---
        pref = self.get_launch_preference(target)
        if pref:
            preferred = pref.get("preferred", "auto")
            if preferred == "web":
                url = pref.get("web_url") or self.resolve_web_url(target)
                if url:
                    return {"action": "open_url", "value": url, "label": target, "reason": "preference_web"}
            elif preferred == "app":
                app_name = pref.get("app_name") or target
                app = self.find_app(app_name)
                if app:
                    return {"action": "open_app", "value": app["name"], "label": app["name"], "reason": "preference_app"}
                # App not installed — fall through to auto
            elif preferred == "folder":
                folder = pref.get("folder_name") or target
                loc = self.find_location(folder)
                if loc:
                    return {"action": "open_location", "value": loc["name"], "label": loc["name"], "reason": "preference_folder"}

        # --- Auto: app registry first (installed apps beat web aliases) ---
        app = self.find_app(target)
        if app:
            return {"action": "open_app", "value": app["name"], "label": app["name"], "reason": "app_registry"}

        # --- Auto: web alias (fallback when app not installed) ---
        url = self.resolve_web_url(target)
        if url:
            return {"action": "open_url", "value": url, "label": target, "reason": "web_alias"}

        # --- Auto: location registry ---
        loc = self.find_location(target)
        if loc:
            return {"action": "open_location", "value": loc["name"], "label": loc["name"], "reason": "location_registry"}

        return {
            "action": "error",
            "error": "target_not_found",
            "label": target,
            "reason": (
                f"No web alias, application, or trusted location found for '{target}'. "
                "Try 'rescan apps' or register it with 'add app / add location'."
            ),
        }

    # Files -----------------------------------------------------------------

    def refresh_file_index(self, location: str = "", force: bool = False) -> dict:
        locations = [self.find_location(location)] if location else self.list_locations()
        locations = [loc for loc in locations if loc and os.path.isdir(loc["path"])]

        indexed_at = time.time()
        scanned = 0
        conn = _conn()
        try:
            for loc in locations:
                if not force:
                    row = conn.execute(
                        "SELECT MAX(indexed_at) AS last_indexed FROM file_index WHERE location_id=?",
                        (loc["id"],),
                    ).fetchone()
                    last_indexed = row["last_indexed"] if row else None
                    if last_indexed and indexed_at - float(last_indexed) < _INDEX_TTL_SECONDS:
                        continue

                conn.execute("DELETE FROM file_index WHERE location_id=?", (loc["id"],))
                for dirpath, filenames in _walk_files(loc["path"]):
                    for filename in filenames:
                        full_path = os.path.join(dirpath, filename)
                        try:
                            stat = os.stat(full_path)
                        except OSError:
                            continue
                        conn.execute(
                            """INSERT OR REPLACE INTO file_index
                               (path, name, extension, location_id, location_name, size_bytes, modified_ts, indexed_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                full_path,
                                filename,
                                Path(filename).suffix.lower().lstrip("."),
                                loc["id"],
                                loc["name"],
                                stat.st_size,
                                stat.st_mtime,
                                indexed_at,
                            ),
                        )
                        scanned += 1
            conn.commit()
            return {"ok": True, "indexed": scanned, "locations": len(locations)}
        finally:
            conn.close()

    def search_files(
        self,
        query: str = "",
        extension: str = "",
        location: str = "",
        max_results: int = 50,
    ) -> list[dict]:
        self.refresh_file_index(location=location)

        query_lower = query.strip().lower()
        ext_lower = extension.lower().lstrip(".")
        ext_lower = {
            "pcb": "kicad_pcb",
            "schematic": "kicad_sch",
            "sch": "kicad_sch",
        }.get(ext_lower, ext_lower)

        loc = self.find_location(location) if location else None
        clauses = []
        params: list[object] = []
        if loc:
            clauses.append("location_id=?")
            params.append(loc["id"])
        if ext_lower:
            clauses.append("extension=?")
            params.append(ext_lower)
        if query_lower:
            clauses.append("(LOWER(name) LIKE ? OR LOWER(path) LIKE ?)")
            params.extend([f"%{query_lower}%", f"%{query_lower}%"])

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"""
            SELECT * FROM file_index
            {where}
            ORDER BY modified_ts DESC
            LIMIT ?
        """
        params.append(max_results)

        conn = _conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            results = [_row_to_indexed_file(row) for row in rows if os.path.isfile(row["path"])]
            logger.info(
                "FILE_SEARCH Query=%r Extension=%r Location=%r IndexedFiles=%d Matches=%d",
                query,
                ext_lower,
                location,
                self.count_indexed_files(location=location),
                len(results),
            )
            return results
        finally:
            conn.close()

    def recent_files(self, location: str = "", max_results: int = 25) -> list[dict]:
        return self.search_files(location=location, max_results=max_results)

    def count_indexed_files(self, location: str = "") -> int:
        loc = self.find_location(location) if location else None
        conn = _conn()
        try:
            if loc:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM file_index WHERE location_id=?",
                    (loc["id"],),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS count FROM file_index").fetchone()
            return int(row["count"] if row else 0)
        finally:
            conn.close()
