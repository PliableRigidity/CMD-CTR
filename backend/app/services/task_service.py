"""Canonical persistent task service with additive legacy-schema migration."""
from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models.personal import Task

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"
VALID_STATUSES = {"open", "in_progress", "blocked", "completed", "cancelled"}
STATUS_ALIASES = {"pending": "open", "done": "completed", "complete": "completed"}
PRIORITIES = {"low", "normal", "high", "critical"}


class AmbiguousTaskError(ValueError):
    def __init__(self, query: str, matches: list[Task]):
        self.query, self.matches = query, matches
        super().__init__(f"Multiple tasks match '{query}'.")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _conn()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            priority TEXT NOT NULL DEFAULT 'normal', project TEXT, created_at TEXT NOT NULL,
            completed_at TEXT)""")
        existing = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        additions = {"description": "TEXT", "updated_at": "TEXT", "due_at": "TEXT",
                     "estimated_minutes": "INTEGER", "reminder_id": "TEXT", "cancelled_at": "TEXT"}
        for name, ddl in additions.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE tasks SET status='open' WHERE status='pending'")
        conn.execute("UPDATE tasks SET status='completed' WHERE status='done'")
        conn.execute("UPDATE tasks SET updated_at=COALESCE(updated_at, created_at, ?)", (now,))
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_at)")
        conn.commit()
    finally:
        conn.close()


def _task(row: sqlite3.Row) -> Task: return Task(**dict(row))
def _norm(text: str) -> str: return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


class TaskService:
    def __init__(self) -> None: _init_db()

    def get_task(self, task_id: str) -> Task | None:
        with _conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return _task(row) if row else None

    def create_task(self, title: str, priority: str = "normal", project: str | None = None,
                    description: str | None = None, due_at: str | None = None,
                    estimated_minutes: int | None = None, reminder_id: str | None = None) -> Task:
        title = title.strip()
        if not title: raise ValueError("Task title is required.")
        priority = priority if priority in PRIORITIES else "normal"
        duplicate = self.find_exact_active(title, project)
        if duplicate: return duplicate
        tid, now = str(uuid.uuid4())[:8], datetime.now(timezone.utc).isoformat()
        with _conn() as conn:
            conn.execute("""INSERT INTO tasks
                (id,title,description,status,priority,project,created_at,updated_at,due_at,estimated_minutes,reminder_id)
                VALUES (?,?,?,'open',?,?,?,?,?,?,?)""",
                (tid, title, description, priority, project or None, now, now, due_at, estimated_minutes, reminder_id))
        stored = self.get_task(tid)
        if not stored: raise RuntimeError("Task could not be verified after saving.")
        return stored

    def list_tasks(self, status: str = "open", project: str | None = None,
                   due_from: str | None = None, due_to: str | None = None) -> list[Task]:
        status = STATUS_ALIASES.get(status, status)
        clauses, args = [], []
        if status != "all":
            if status == "active": clauses.append("status IN ('open','in_progress','blocked')")
            else: clauses.append("status=?"); args.append(status)
        if project: clauses.append("LOWER(project)=LOWER(?)"); args.append(project)
        if due_from: clauses.append("due_at>=?"); args.append(due_from)
        if due_to: clauses.append("due_at<?"); args.append(due_to)
        sql = "SELECT * FROM tasks" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        sql += " ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, COALESCE(due_at,'9999'), created_at"
        with _conn() as conn: return [_task(r) for r in conn.execute(sql, args).fetchall()]

    def find_matches(self, query: str, active_only: bool = True) -> list[Task]:
        q = _norm(query)
        if not q: return []
        with _conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (query,)).fetchone()
            if row: return [_task(row)]
            candidates = [_task(r) for r in conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC").fetchall()]
        if active_only: candidates = [t for t in candidates if t.status not in {"completed", "cancelled"}]
        exact = [t for t in candidates if _norm(t.title) == q]
        if exact: return exact
        words = set(q.split())
        return [t for t in candidates if q in _norm(t.title) or words.issubset(set(_norm(t.title).split()))]

    def resolve(self, query: str, active_only: bool = True) -> Task | None:
        matches = self.find_matches(query, active_only)
        if len(matches) > 1: raise AmbiguousTaskError(query, matches)
        return matches[0] if matches else None

    def find_by_query(self, query: str) -> Task | None: return self.resolve(query)

    def find_exact_active(self, title: str, project: str | None = None) -> Task | None:
        with _conn() as conn:
            row = conn.execute("""SELECT * FROM tasks WHERE LOWER(TRIM(title))=LOWER(TRIM(?))
                AND COALESCE(LOWER(project),'')=COALESCE(LOWER(?),'')
                AND status NOT IN ('completed','cancelled') ORDER BY updated_at DESC LIMIT 1""", (title, project)).fetchone()
            return _task(row) if row else None

    def update_task(self, task_id: str, **changes) -> Task | None:
        allowed = {"title", "description", "status", "priority", "project", "due_at", "estimated_minutes", "reminder_id"}
        changes = {k: v for k, v in changes.items() if k in allowed}
        if "status" in changes:
            changes["status"] = STATUS_ALIASES.get(changes["status"], changes["status"])
            if changes["status"] not in VALID_STATUSES: raise ValueError("Invalid task status.")
        if not changes: return self.get_task(task_id)
        now = datetime.now(timezone.utc).isoformat(); changes["updated_at"] = now
        if changes.get("status") == "completed": changes["completed_at"] = now
        elif "status" in changes: changes["completed_at"] = None
        if changes.get("status") == "cancelled": changes["cancelled_at"] = now
        sets = ", ".join(f"{k}=?" for k in changes)
        with _conn() as conn:
            cur = conn.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*changes.values(), task_id))
            if not cur.rowcount: return None
        return self.get_task(task_id)

    def complete_task(self, task_id: str) -> bool: return self.update_task(task_id, status="completed") is not None
    def reopen_task(self, task_id: str) -> bool: return self.update_task(task_id, status="open") is not None
    def reschedule_task(self, task_id: str, due_at: str) -> Task | None: return self.update_task(task_id, due_at=due_at)
    def cancel_task(self, task_id: str) -> bool: return self.update_task(task_id, status="cancelled") is not None
    def delete_task(self, task_id: str) -> bool: return self.cancel_task(task_id)
