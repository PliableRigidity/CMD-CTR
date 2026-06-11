"""Reminder service — persistent reminders with recurrence support."""
from __future__ import annotations

import sqlite3
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.models.personal import Reminder, ReminderCreate

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
            CREATE TABLE IF NOT EXISTS reminders (
                id            TEXT PRIMARY KEY,
                message       TEXT NOT NULL,
                trigger_at    TEXT NOT NULL,
                recurrence    TEXT NOT NULL DEFAULT 'once',
                completed     INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL,
                last_fired_at TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _row_to_reminder(row) -> Reminder:
    d = dict(row)
    d["completed"] = bool(d["completed"])
    return Reminder(**d)


class ReminderService:
    def __init__(self) -> None:
        _init_db()

    def create_reminder(self, message: str, trigger_at: str, recurrence: str = "once") -> Reminder:
        rid = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO reminders (id, message, trigger_at, recurrence, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (rid, message, trigger_at, recurrence, now),
            )
            conn.commit()
        finally:
            conn.close()
        return Reminder(id=rid, message=message, trigger_at=trigger_at,
                        recurrence=recurrence, created_at=now)

    def list_reminders(self, include_completed: bool = False) -> list[Reminder]:
        conn = _conn()
        try:
            sql = "SELECT * FROM reminders"
            if not include_completed:
                sql += " WHERE completed = 0"
            sql += " ORDER BY trigger_at ASC"
            return [_row_to_reminder(r) for r in conn.execute(sql).fetchall()]
        finally:
            conn.close()

    def get_due_reminders(self) -> list[Reminder]:
        """Return non-completed reminders whose trigger_at <= now (UTC)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE completed = 0 AND trigger_at <= ? ORDER BY trigger_at ASC",
                (now_iso,),
            ).fetchall()
            return [_row_to_reminder(r) for r in rows]
        finally:
            conn.close()

    def complete_reminder(self, reminder_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?", (reminder_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def advance_recurrence(self, reminder_id: str) -> bool:
        """Move trigger_at to the next occurrence for recurring reminders."""
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
            if not row:
                return False
            rec = row["recurrence"]
            if rec == "once":
                return False
            dt = datetime.fromisoformat(row["trigger_at"])
            if rec == "daily":
                new_dt = dt + timedelta(days=1)
            elif rec.startswith("weekly:"):
                new_dt = dt + timedelta(weeks=1)
            elif rec.startswith("monthly:"):
                month = dt.month + 1 if dt.month < 12 else 1
                year = dt.year if dt.month < 12 else dt.year + 1
                day = min(dt.day, monthrange(year, month)[1])
                new_dt = dt.replace(year=year, month=month, day=day)
            else:
                return False
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE reminders SET trigger_at = ?, last_fired_at = ? WHERE id = ?",
                (new_dt.isoformat(), now_iso, reminder_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def delete_reminder(self, reminder_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def find_by_query(self, query: str) -> Reminder | None:
        """Find first active reminder matching partial message or exact ID."""
        conn = _conn()
        try:
            # Try exact ID match first
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ? AND completed = 0", (query,)
            ).fetchone()
            if row:
                return _row_to_reminder(row)
            # Partial message match
            rows = conn.execute(
                "SELECT * FROM reminders WHERE completed = 0 AND LOWER(message) LIKE ? ORDER BY trigger_at ASC",
                (f"%{query.lower()}%",),
            ).fetchall()
            if rows:
                return _row_to_reminder(rows[0])
            return None
        finally:
            conn.close()
