"""Task service — personal task tracking."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models.personal import Task, TaskCreate

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"


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
            CREATE TABLE IF NOT EXISTS tasks (
                id           TEXT PRIMARY KEY,
                title        TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'pending',
                priority     TEXT NOT NULL DEFAULT 'normal',
                project      TEXT,
                created_at   TEXT NOT NULL,
                completed_at TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _row_to_task(row) -> Task:
    return Task(**dict(row))


class TaskService:
    def __init__(self) -> None:
        _init_db()

    def create_task(self, title: str, priority: str = "normal", project: str | None = None) -> Task:
        tid = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO tasks (id, title, status, priority, project, created_at)
                   VALUES (?, ?, 'pending', ?, ?, ?)""",
                (tid, title, priority, project or None, now),
            )
            conn.commit()
        finally:
            conn.close()
        return Task(id=tid, title=title, priority=priority, project=project or None, created_at=now)

    def list_tasks(self, status: str = "pending") -> list[Task]:
        conn = _conn()
        try:
            if status == "all":
                rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            return [_row_to_task(r) for r in rows]
        finally:
            conn.close()

    def complete_task(self, task_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                (now, task_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_task(self, task_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def find_by_query(self, query: str) -> Task | None:
        """Find first pending task matching partial title or exact ID."""
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (query,)
            ).fetchone()
            if row:
                return _row_to_task(row)
            rows = conn.execute(
                "SELECT * FROM tasks WHERE LOWER(title) LIKE ? ORDER BY created_at DESC",
                (f"%{query.lower()}%",),
            ).fetchall()
            if rows:
                return _row_to_task(rows[0])
            return None
        finally:
            conn.close()
