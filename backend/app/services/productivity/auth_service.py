"""OAuth2 token storage for the productivity layer.

Tokens are persisted in the main cmdctr.db SQLite database alongside
nodes, tasks, reminders, and everything else.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "cmdctr.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


_INITED = False


def _init_db() -> None:
    global _INITED
    if _INITED:
        return
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id         TEXT PRIMARY KEY,
                provider   TEXT NOT NULL UNIQUE,
                token_data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()
    _INITED = True


class AuthService:
    """CRUD for OAuth2 tokens stored in cmdctr.db."""

    def __init__(self) -> None:
        _init_db()

    def store(self, provider: str, data: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO oauth_tokens (id, provider, token_data, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(provider)
                   DO UPDATE SET token_data = excluded.token_data,
                                 updated_at = excluded.updated_at""",
                (str(uuid.uuid4()), provider, json.dumps(data), now),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, provider: str) -> dict | None:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT token_data FROM oauth_tokens WHERE provider = ?",
                (provider,),
            ).fetchone()
            return json.loads(row["token_data"]) if row else None
        finally:
            conn.close()

    def clear(self, provider: str) -> None:
        conn = _conn()
        try:
            conn.execute("DELETE FROM oauth_tokens WHERE provider = ?", (provider,))
            conn.commit()
        finally:
            conn.close()
