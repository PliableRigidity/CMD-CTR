"""SQLite-backed persistence for conversation history and user facts."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cmdctr.db"


def _get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
                content    TEXT    NOT NULL,
                mode       TEXT    NOT NULL DEFAULT 'conversation',
                ts         REAL    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, ts);

            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                created_at   REAL NOT NULL,
                last_active  REAL NOT NULL,
                label        TEXT
            );

            CREATE TABLE IF NOT EXISTS facts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                key        TEXT NOT NULL UNIQUE,
                value      TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def save_message(session_id: str, role: str, content: str, mode: str = "conversation") -> None:
    conn = _get_connection()
    try:
        now = time.time()
        conn.execute(
            "INSERT INTO messages (session_id, role, content, mode, ts) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, mode, now),
        )
        conn.execute(
            """
            INSERT INTO sessions (session_id, created_at, last_active)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET last_active=excluded.last_active
            """,
            (session_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return the last `limit` messages for a session, oldest first."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            """
            SELECT role, content, mode, ts
            FROM messages
            WHERE session_id = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def clear_session(session_id: str) -> int:
    """Delete all messages for a session. Returns number of rows deleted."""
    conn = _get_connection()
    try:
        cur = conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def list_sessions() -> list[dict[str, Any]]:
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT session_id, created_at, last_active, label FROM sessions ORDER BY last_active DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Facts (persistent key/value store for user preferences)
# ---------------------------------------------------------------------------

def set_fact(key: str, value: str) -> None:
    conn = _get_connection()
    try:
        conn.execute(
            """
            INSERT INTO facts (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def get_fact(key: str) -> str | None:
    conn = _get_connection()
    try:
        row = conn.execute("SELECT value FROM facts WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def get_all_facts() -> dict[str, str]:
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT key, value FROM facts").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()
