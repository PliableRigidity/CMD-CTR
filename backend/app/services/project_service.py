"""Project Registry — first-class project entity with SQLite persistence."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models.project import Project, ProjectCreate, ProjectUpdate

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

_SEEDS = [
    {
        "id": "cmd-ctr",
        "name": "CMD-CTR",
        "status": "active",
        "priority": "critical",
        "tags": ["ai", "os", "silvia"],
        "brain63_key": "CMD-CTR",
        "notes": "Personal AI operating system — SILVIA. Local-first, Ollama-powered.",
    },
    {
        "id": "dronehive",
        "name": "DroneHive",
        "status": "active",
        "priority": "high",
        "tags": ["drones", "robotics", "swarm"],
        "brain63_key": "DroneHive",
        "notes": "Autonomous drone swarm coordination and fleet intelligence platform.",
    },
    {
        "id": "cyberdeck",
        "name": "Cyberdeck",
        "status": "active",
        "priority": "normal",
        "tags": ["hardware", "cyberdeck"],
        "brain63_key": "Cyberdeck",
        "notes": "Custom cyberdeck build — power architecture under design.",
    },
    {
        "id": "koi",
        "name": "KOI",
        "status": "paused",
        "priority": "normal",
        "tags": ["ai", "workflow", "agents"],
        "brain63_key": "KOI",
        "notes": "AI-native project workflow automation via agent delegation.",
    },
    {
        "id": "brain63",
        "name": "Brain63",
        "status": "active",
        "priority": "normal",
        "tags": ["knowledge", "pkm", "notes"],
        "brain63_key": "Brain63",
        "notes": "Personal knowledge base and long-term memory system.",
    },
    {
        "id": "university",
        "name": "University",
        "status": "active",
        "priority": "high",
        "tags": ["academic", "coursework"],
        "brain63_key": None,
        "notes": "Academic coursework, research, and engineering education.",
    },
]


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'active',
                priority      TEXT NOT NULL DEFAULT 'normal',
                tags          TEXT NOT NULL DEFAULT '[]',
                brain63_key   TEXT,
                notes         TEXT,
                last_activity TEXT,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );
        """)
        conn.commit()
        # Seed projects if table is empty
        count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            for s in _SEEDS:
                conn.execute(
                    """INSERT INTO projects (id, name, status, priority, tags, brain63_key, notes, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        s["id"], s["name"], s["status"], s["priority"],
                        json.dumps(s["tags"]), s["brain63_key"], s["notes"],
                        now, now,
                    ),
                )
            conn.commit()
    finally:
        conn.close()


def _row_to_project(row) -> Project:
    d = dict(row)
    return Project(**d)


class ProjectService:
    def __init__(self) -> None:
        _init_db()

    def list_projects(self, status: str | None = None) -> list[Project]:
        conn = _conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM projects WHERE status = ? ORDER BY priority DESC, name ASC", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM projects ORDER BY priority DESC, name ASC"
                ).fetchall()
            return [_row_to_project(r) for r in rows]
        finally:
            conn.close()

    def get_project(self, project_id: str) -> Project | None:
        conn = _conn()
        try:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return _row_to_project(row) if row else None
        finally:
            conn.close()

    def find_by_name(self, name: str) -> Project | None:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE LOWER(name) = ?", (name.lower(),)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM projects WHERE LOWER(name) LIKE ?", (f"%{name.lower()}%",)
                ).fetchone()
            return _row_to_project(row) if row else None
        finally:
            conn.close()

    def create_project(self, data: ProjectCreate) -> Project:
        pid = data.name.lower().replace(" ", "-")[:24]
        # Ensure unique
        base = pid
        conn = _conn()
        try:
            idx = 1
            while conn.execute("SELECT id FROM projects WHERE id = ?", (pid,)).fetchone():
                pid = f"{base}-{idx}"
                idx += 1
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO projects (id, name, status, priority, tags, brain63_key, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pid, data.name, data.status, data.priority,
                    json.dumps(data.tags), data.brain63_key, data.notes,
                    now, now,
                ),
            )
            conn.commit()
            return Project(
                id=pid, name=data.name, status=data.status, priority=data.priority,
                tags=data.tags, brain63_key=data.brain63_key, notes=data.notes,
                created_at=now, updated_at=now,
            )
        finally:
            conn.close()

    def update_project(self, project_id: str, data: ProjectUpdate) -> Project | None:
        conn = _conn()
        try:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not row:
                return None
            now = datetime.now(timezone.utc).isoformat()
            fields: dict = {}
            if data.name is not None:
                fields["name"] = data.name
            if data.status is not None:
                fields["status"] = data.status
            if data.priority is not None:
                fields["priority"] = data.priority
            if data.tags is not None:
                fields["tags"] = json.dumps(data.tags)
            if data.brain63_key is not None:
                fields["brain63_key"] = data.brain63_key
            if data.notes is not None:
                fields["notes"] = data.notes
            fields["updated_at"] = now
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            values = list(fields.values()) + [project_id]
            conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)
            conn.commit()
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            return _row_to_project(row)
        finally:
            conn.close()

    def touch_activity(self, project_id: str) -> None:
        """Update last_activity to now — call when a task/reminder linked to this project changes."""
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            conn.execute(
                "UPDATE projects SET last_activity = ?, updated_at = ? WHERE id = ?",
                (now, now, project_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_project(self, project_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
