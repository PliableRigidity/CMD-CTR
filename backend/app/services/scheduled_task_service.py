"""Scheduled task service — autonomous Hermes tasks on a cron-like interval."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from backend.app.models.nodes import Node  # reuse DB_PATH location

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
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id               TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                prompt           TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                enabled          INTEGER NOT NULL DEFAULT 1,
                next_run         TEXT NOT NULL,
                last_run         TEXT,
                last_result      TEXT,
                created_at       TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return dict(row)


class ScheduledTaskService:
    def __init__(self) -> None:
        _init_db()

    def list_tasks(self) -> list[dict]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_tasks ORDER BY name ASC"
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_task(self, task_id: str) -> Optional[dict]:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()

    def create_task(self, name: str, prompt: str, interval_minutes: int) -> dict:
        task_id = str(uuid.uuid4())[:8]
        now = _utc_now()
        next_run = (datetime.now(timezone.utc) + timedelta(minutes=interval_minutes)).isoformat()
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO scheduled_tasks (id, name, prompt, interval_minutes, enabled, next_run, created_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (task_id, name, prompt, interval_minutes, next_run, now),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_task(task_id)

    def update_task(self, task_id: str, **fields) -> Optional[dict]:
        allowed = {"name", "prompt", "interval_minutes", "enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_task(task_id)
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [task_id]
        conn = _conn()
        try:
            conn.execute(f"UPDATE scheduled_tasks SET {cols} WHERE id = ?", vals)
            conn.commit()
        finally:
            conn.close()
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM scheduled_tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_due_tasks(self) -> list[dict]:
        now = _utc_now()
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM scheduled_tasks WHERE enabled = 1 AND next_run <= ?",
                (now,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def mark_ran(self, task_id: str, result: str) -> None:
        task = self.get_task(task_id)
        if not task:
            return
        interval = task["interval_minutes"]
        next_run = (datetime.now(timezone.utc) + timedelta(minutes=interval)).isoformat()
        conn = _conn()
        try:
            conn.execute(
                "UPDATE scheduled_tasks SET last_run = ?, last_result = ?, next_run = ? WHERE id = ?",
                (_utc_now(), result[:500] if result else "", next_run, task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def find_by_name(self, name: str) -> Optional[dict]:
        needle = name.lower().strip()
        tasks = self.list_tasks()
        for t in tasks:
            if t["name"].lower() == needle:
                return t
        for t in tasks:
            if needle in t["name"].lower():
                return t
        return None
