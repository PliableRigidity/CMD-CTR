"""Session Manager — Phase 16B.

Captures, stores, and retrieves engineering sessions. A session is a
contiguous period of work on a project detected via Screen Awareness.
Sessions are created from workspace_context_log entries, grouped by
project and time proximity.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("silvia.session_manager")

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

_SESSION_GAP_MINUTES = 30


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ts() -> float:
    return time.time()


class SessionManager:
    """Manages engineering session capture, storage, and retrieval."""

    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspace_sessions (
                    id          TEXT PRIMARY KEY,
                    project     TEXT NOT NULL DEFAULT '',
                    started_at  TEXT NOT NULL,
                    ended_at    TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL DEFAULT 0,
                    apps        TEXT NOT NULL DEFAULT '[]',
                    files       TEXT NOT NULL DEFAULT '[]',
                    session_type TEXT NOT NULL DEFAULT '',
                    summary     TEXT NOT NULL DEFAULT '',
                    context     TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ws_sess_project ON workspace_sessions(project);
                CREATE INDEX IF NOT EXISTS idx_ws_sess_started ON workspace_sessions(started_at);

                CREATE TABLE IF NOT EXISTS workspace_profiles (
                    id          TEXT PRIMARY KEY,
                    project     TEXT NOT NULL UNIQUE,
                    apps        TEXT NOT NULL DEFAULT '[]',
                    boards      TEXT NOT NULL DEFAULT '[]',
                    folders     TEXT NOT NULL DEFAULT '[]',
                    urls        TEXT NOT NULL DEFAULT '[]',
                    notes       TEXT NOT NULL DEFAULT '',
                    updated_at  TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_prof_project
                    ON workspace_profiles(project);
            """)

    # ── Session capture ─────────────────────────────────────────────────────

    def capture_current(self) -> dict[str, Any]:
        """Capture the current workspace state as a session snapshot."""
        from backend.app.services.workspace_awareness import get_awareness
        ctx = get_awareness().get_context()

        project = ctx.get("project", "")
        if not project:
            return {"ok": False, "reason": "No active project detected."}

        apps = list({t["app_name"] for t in ctx.get("open_tools", [])})
        files = [ctx["file"]] if ctx.get("file") else []

        now = _now()
        sid = f"ses_{uuid.uuid4().hex[:8]}"

        with _conn() as db:
            db.execute(
                """INSERT INTO workspace_sessions
                   (id, project, started_at, ended_at, duration_minutes,
                    apps, files, session_type, summary, context, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sid, project, now, now, 0,
                    json.dumps(apps), json.dumps(files),
                    ctx.get("session_type", ""),
                    f"Working on {project}" + (f" — {ctx.get('file', '')}" if ctx.get("file") else ""),
                    json.dumps({
                        "active_app": ctx.get("active_app", ""),
                        "workspace": ctx.get("workspace", ""),
                        "tool_type": ctx.get("tool_type", ""),
                        "engineering_context": ctx.get("engineering_context", {}),
                    }),
                    now,
                ),
            )

        return {
            "ok": True,
            "session_id": sid,
            "project": project,
            "apps": apps,
            "files": files,
            "session_type": ctx.get("session_type", ""),
        }

    def build_sessions_from_log(self) -> int:
        """Build session records from the workspace_context_log.

        Groups context log entries by project and time proximity
        (entries within _SESSION_GAP_MINUTES of each other = same session).
        Only creates sessions not already represented.
        """
        with _conn() as db:
            # Get latest session end time per project
            existing = {}
            for row in db.execute(
                "SELECT project, MAX(ended_at) as last_end FROM workspace_sessions GROUP BY project"
            ).fetchall():
                existing[row["project"]] = row["last_end"]

            # Get context log entries grouped by project
            rows = db.execute(
                """SELECT project, app_name, file_name, session_type, timestamp
                   FROM workspace_context_log
                   WHERE project != ''
                   ORDER BY project, timestamp"""
            ).fetchall()

        if not rows:
            return 0

        # Group into sessions
        sessions: list[dict] = []
        current: Optional[dict] = None

        for row in rows:
            row = dict(row)
            proj = row["project"]
            ts = row["timestamp"]

            # Skip if already covered by existing session
            if proj in existing and ts <= existing[proj]:
                continue

            if current and current["project"] == proj and self._within_gap(current["ended_at"], ts):
                current["ended_at"] = ts
                current["apps"].add(row["app_name"])
                if row["file_name"]:
                    current["files"].add(row["file_name"])
                current["session_type"] = row["session_type"] or current["session_type"]
                current["count"] += 1
            else:
                if current:
                    sessions.append(current)
                current = {
                    "project": proj,
                    "started_at": ts,
                    "ended_at": ts,
                    "apps": {row["app_name"]},
                    "files": {row["file_name"]} if row["file_name"] else set(),
                    "session_type": row["session_type"] or "",
                    "count": 1,
                }

        if current:
            sessions.append(current)

        # Store new sessions
        created = 0
        with _conn() as db:
            for s in sessions:
                if s["count"] < 2:
                    continue
                dur = self._duration_minutes(s["started_at"], s["ended_at"])
                if dur < 1:
                    continue
                sid = f"ses_{uuid.uuid4().hex[:8]}"
                apps = sorted(s["apps"] - {""})
                files = sorted(s["files"] - {""})
                db.execute(
                    """INSERT OR IGNORE INTO workspace_sessions
                       (id, project, started_at, ended_at, duration_minutes,
                        apps, files, session_type, summary, context, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        sid, s["project"], s["started_at"], s["ended_at"], dur,
                        json.dumps(apps), json.dumps(files),
                        s["session_type"],
                        f"Worked on {s['project']} for ~{dur}m",
                        "{}",
                        _now(),
                    ),
                )
                created += 1

        return created

    # ── Session queries ─────────────────────────────────────────────────────

    def get_recent_sessions(self, hours: int = 48, limit: int = 20) -> list[dict]:
        """Recent sessions across all projects."""
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - hours * 3600),
        )
        with _conn() as db:
            rows = db.execute(
                """SELECT * FROM workspace_sessions
                   WHERE started_at >= ?
                   ORDER BY started_at DESC LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [self._hydrate(r) for r in rows]

    def get_project_sessions(self, project: str, limit: int = 10) -> list[dict]:
        """Sessions for a specific project."""
        with _conn() as db:
            rows = db.execute(
                """SELECT * FROM workspace_sessions
                   WHERE LOWER(project) LIKE LOWER(?)
                   ORDER BY started_at DESC LIMIT ?""",
                (f"%{project}%", limit),
            ).fetchall()
        return [self._hydrate(r) for r in rows]

    def get_last_session(self, project: str | None = None) -> Optional[dict]:
        """Most recent session, optionally for a specific project."""
        with _conn() as db:
            if project:
                row = db.execute(
                    """SELECT * FROM workspace_sessions
                       WHERE LOWER(project) LIKE LOWER(?)
                       ORDER BY started_at DESC LIMIT 1""",
                    (f"%{project}%",),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM workspace_sessions ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
        return self._hydrate(row) if row else None

    def get_session_timeline(self, hours: int = 24) -> list[dict]:
        """Timeline of sessions within the last N hours."""
        cutoff = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - hours * 3600),
        )
        with _conn() as db:
            rows = db.execute(
                """SELECT project, started_at, ended_at, duration_minutes,
                          session_type, apps
                   FROM workspace_sessions
                   WHERE started_at >= ?
                   ORDER BY started_at""",
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_accomplishments(self, hours: int = 24) -> dict[str, Any]:
        """What was accomplished in the last N hours."""
        sessions = self.get_recent_sessions(hours=hours, limit=50)
        if not sessions:
            # Fall back to context log
            from backend.app.services.workspace_awareness import get_awareness
            recent = get_awareness().get_recent_projects(hours=hours)
            if recent:
                return {
                    "ok": True,
                    "source": "context_log",
                    "period_hours": hours,
                    "projects": [
                        {"project": r["project"], "entries": r["entries"], "apps": r.get("apps", "")}
                        for r in recent
                    ],
                    "session_count": 0,
                    "total_minutes": 0,
                    "summary": f"Worked on {len(recent)} project(s) in the last {hours}h.",
                }
            return {"ok": True, "source": "none", "projects": [], "session_count": 0,
                    "total_minutes": 0, "summary": "No recorded activity."}

        projects: dict[str, dict] = {}
        total_minutes = 0
        for s in sessions:
            proj = s["project"]
            if proj not in projects:
                projects[proj] = {"project": proj, "sessions": 0, "minutes": 0, "files": set(), "apps": set()}
            projects[proj]["sessions"] += 1
            projects[proj]["minutes"] += s.get("duration_minutes", 0)
            total_minutes += s.get("duration_minutes", 0)
            for f in s.get("files", []):
                projects[proj]["files"].add(f)
            for a in s.get("apps", []):
                projects[proj]["apps"].add(a)

        # Add recent milestones from project memory
        milestones = []
        try:
            from backend.app.services.project_memory import get_memory
            milestones = get_memory().get_recent(days=1, limit=5)
        except Exception:
            pass

        proj_list = []
        for p in sorted(projects.values(), key=lambda x: -x["minutes"]):
            proj_list.append({
                "project": p["project"],
                "sessions": p["sessions"],
                "minutes": p["minutes"],
                "files": sorted(p["files"]),
                "apps": sorted(p["apps"]),
            })

        return {
            "ok": True,
            "source": "sessions",
            "period_hours": hours,
            "projects": proj_list,
            "session_count": len(sessions),
            "total_minutes": total_minutes,
            "milestones": milestones[:5],
            "summary": f"{len(sessions)} session(s) across {len(projects)} project(s), ~{total_minutes}m total.",
        }

    # ── Continuity: "continue project X" ────────────────────────────────────

    def continue_project(self, project_name: str) -> dict[str, Any]:
        """Generate a continuity report for resuming work on a project.

        Aggregates: last session, project memory, digital twin, open tasks,
        recommended actions.
        """
        last = self.get_last_session(project_name)
        recent_sessions = self.get_project_sessions(project_name, limit=5)

        # Digital Twin data
        twin_data = {}
        try:
            from backend.app.services.digital_twin import get_twin
            for p in get_twin().project_states():
                if p["name"].lower() == project_name.lower() or project_name.lower() in p["name"].lower():
                    twin_data = p
                    break
        except Exception:
            pass

        # Project memory
        recent_memory = []
        try:
            from backend.app.services.project_memory import get_memory
            recent_memory = get_memory().get_project_memories(project_name, limit=5)
        except Exception:
            pass

        # Open tasks
        open_tasks = []
        try:
            from backend.app.services.task_service import TaskService
            tasks = TaskService().list_tasks(status="pending")
            open_tasks = [t.title for t in tasks if t.project and project_name.lower() in t.project.lower()][:5]
        except Exception:
            pass

        # Project briefing recommended action
        recommended = twin_data.get("recommended_action", "")

        # Resolve project name
        resolved_name = twin_data.get("name", project_name)

        return {
            "ok": True,
            "project": resolved_name,
            "last_session": {
                "when": last["started_at"] if last else None,
                "duration": last.get("duration_minutes", 0) if last else 0,
                "files": last.get("files", []) if last else [],
                "apps": last.get("apps", []) if last else [],
                "session_type": last.get("session_type", "") if last else "",
            } if last else None,
            "recent_sessions": len(recent_sessions),
            "status": twin_data.get("status", "unknown"),
            "priority": twin_data.get("priority", "normal"),
            "readiness_pct": twin_data.get("readiness_pct", 0),
            "open_tasks": open_tasks,
            "recent_memory": [
                {"type": m.get("type", ""), "title": m.get("title", "")}
                for m in recent_memory
            ],
            "recommended_action": recommended,
            "summary": self._build_continue_summary(resolved_name, last, twin_data, open_tasks, recommended),
        }

    def _build_continue_summary(self, name, last, twin, tasks, recommended) -> str:
        parts = [f"Continue {name}:"]
        if last:
            parts.append(f"Last session: {last.get('session_type', '')} ({last.get('duration_minutes', 0)}m)")
            if last.get("files"):
                parts.append(f"Last files: {', '.join(last['files'][:3])}")
        if twin.get("status"):
            parts.append(f"Status: {twin['status']}, {twin.get('readiness_pct', 0)}% ready")
        if tasks:
            parts.append(f"{len(tasks)} open task(s)")
        if recommended:
            parts.append(f"Next: {recommended}")
        return " | ".join(parts)

    # ── Workspace profiles ──────────────────────────────────────────────────

    def get_profile(self, project: str) -> Optional[dict]:
        """Get workspace profile for a project."""
        with _conn() as db:
            row = db.execute(
                "SELECT * FROM workspace_profiles WHERE LOWER(project) = LOWER(?)",
                (project,),
            ).fetchone()
        if row:
            r = dict(row)
            for k in ("apps", "boards", "folders", "urls"):
                try:
                    r[k] = json.loads(r[k])
                except Exception:
                    r[k] = []
            return r

        # Auto-generate from project data
        return self._auto_profile(project)

    def save_profile(self, project: str, apps: list[str] | None = None,
                     boards: list[str] | None = None, folders: list[str] | None = None,
                     urls: list[str] | None = None, notes: str = "") -> dict:
        """Save or update a workspace profile."""
        now = _now()
        with _conn() as db:
            existing = db.execute(
                "SELECT id FROM workspace_profiles WHERE LOWER(project) = LOWER(?)",
                (project,),
            ).fetchone()
            if existing:
                fields = {}
                if apps is not None:
                    fields["apps"] = json.dumps(apps)
                if boards is not None:
                    fields["boards"] = json.dumps(boards)
                if folders is not None:
                    fields["folders"] = json.dumps(folders)
                if urls is not None:
                    fields["urls"] = json.dumps(urls)
                if notes:
                    fields["notes"] = notes
                fields["updated_at"] = now
                sets = ", ".join(f"{k}=?" for k in fields)
                vals = list(fields.values()) + [existing["id"]]
                db.execute(f"UPDATE workspace_profiles SET {sets} WHERE id=?", vals)
                return {"ok": True, "action": "updated", "project": project}
            else:
                pid = f"wp_{uuid.uuid4().hex[:8]}"
                db.execute(
                    """INSERT INTO workspace_profiles
                       (id, project, apps, boards, folders, urls, notes, updated_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        pid, project,
                        json.dumps(apps or []), json.dumps(boards or []),
                        json.dumps(folders or []), json.dumps(urls or []),
                        notes, now,
                    ),
                )
                return {"ok": True, "action": "created", "project": project}

    def _auto_profile(self, project: str) -> Optional[dict]:
        """Auto-generate a workspace profile from project data."""
        try:
            from backend.app.services.project_intelligence import ProjectIntelligence
            meta = ProjectIntelligence().find_project_meta(project)
            if not meta:
                return None

            name = meta["name"]
            apps = ["VS Code"]
            boards = ["/workspace"]
            folders = []
            urls = []

            # Check for project folder
            gh_root = Path.home() / "Documents" / "GitHub"
            for candidate in [gh_root / name, gh_root / name.lower(), gh_root / name.replace(" ", "-")]:
                if candidate.exists():
                    folders.append(str(candidate))
                    break

            # Brain63 key → probably has notes
            if meta.get("brain63_key"):
                boards.append("/knowledge")

            # Hardware project → hardware board
            if meta.get("hw_project"):
                boards.append("/hardware")

            # Memory entries → memory board
            try:
                from backend.app.services.project_memory import get_memory
                if get_memory().get_project_memories(name, limit=1):
                    boards.append("/memory")
            except Exception:
                pass

            # Recent session apps
            sessions = self.get_project_sessions(project, limit=3)
            for s in sessions:
                for app in s.get("apps", []):
                    if app not in apps:
                        apps.append(app)

            return {
                "id": None,
                "project": name,
                "apps": apps[:6],
                "boards": list(dict.fromkeys(boards))[:5],
                "folders": folders[:3],
                "urls": urls[:5],
                "notes": meta.get("notes", ""),
                "auto_generated": True,
            }
        except Exception:
            return None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _hydrate(self, row) -> dict:
        r = dict(row)
        for k in ("apps", "files"):
            try:
                r[k] = json.loads(r[k])
            except Exception:
                r[k] = []
        try:
            r["context"] = json.loads(r.get("context", "{}"))
        except Exception:
            r["context"] = {}
        return r

    def _within_gap(self, ts1: str, ts2: str) -> bool:
        """Check if two timestamps are within the session gap."""
        try:
            t1 = datetime.fromisoformat(ts1.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(ts2.replace("Z", "+00:00"))
            return abs((t2 - t1).total_seconds()) < _SESSION_GAP_MINUTES * 60
        except Exception:
            return False

    def _duration_minutes(self, start: str, end: str) -> int:
        try:
            t1 = datetime.fromisoformat(start.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return max(1, int((t2 - t1).total_seconds() / 60))
        except Exception:
            return 0


_instance: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _instance
    if _instance is None:
        _instance = SessionManager()
    return _instance
