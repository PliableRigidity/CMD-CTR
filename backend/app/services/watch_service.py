"""Watch Officer — proactive infrastructure alert service."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models.watch_officer import WatchAlert, WatchAlertCreate

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

_SEED_ALERTS = [
    ("SILVIA v4.0.0 AI OS active — multi-agent stack initialised", "mission", "info"),
    ("Node Registry ready — Workstation registered as core node", "infra", "info"),
    ("Web search: DuckDuckGo fallback active — SearxNG not configured", "system", "info"),
    ("Voice pipeline ready — configure Whisper + Piper for local inference", "system", "info"),
]


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watch_alerts (
                id          TEXT PRIMARY KEY,
                message     TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'system',
                severity    TEXT NOT NULL DEFAULT 'info',
                created_at  TEXT NOT NULL,
                dismissed   INTEGER NOT NULL DEFAULT 0
            );
        """)
        conn.commit()
        # Runtime migration: add rule_key column if absent
        cols = {row[1] for row in conn.execute("PRAGMA table_info(watch_alerts)").fetchall()}
        if "rule_key" not in cols:
            conn.execute("ALTER TABLE watch_alerts ADD COLUMN rule_key TEXT")
            conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM watch_alerts").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            conn.executemany(
                """INSERT INTO watch_alerts (id, message, category, severity, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                [(str(uuid.uuid4())[:8], msg, cat, sev, now) for msg, cat, sev in _SEED_ALERTS],
            )
            conn.commit()
    finally:
        conn.close()


def _row_to_alert(row) -> WatchAlert:
    d = dict(row)
    d["dismissed"] = bool(d["dismissed"])
    return WatchAlert(**d)


class WatchService:
    def __init__(self) -> None:
        _init_db()

    def list_alerts(self, include_dismissed: bool = False) -> list[WatchAlert]:
        conn = _conn()
        try:
            sql = "SELECT * FROM watch_alerts"
            if not include_dismissed:
                sql += " WHERE dismissed = 0"
            sql += " ORDER BY created_at DESC"
            return [_row_to_alert(r) for r in conn.execute(sql).fetchall()]
        finally:
            conn.close()

    def create_alert(self, data: WatchAlertCreate) -> WatchAlert:
        alert_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO watch_alerts (id, message, category, severity, created_at, rule_key)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (alert_id, data.message, data.category, data.severity, now, data.rule_key),
            )
            conn.commit()
        finally:
            conn.close()
        return WatchAlert(
            id=alert_id,
            message=data.message,
            category=data.category,
            severity=data.severity,
            created_at=now,
            rule_key=data.rule_key,
        )

    def raise_alert(
        self,
        rule_key: str,
        message: str,
        category: str,
        severity: str,
    ) -> WatchAlert | None:
        """Idempotent — creates an alert only if no active alert with this rule_key exists.
        Returns the new WatchAlert, or None if one was already active."""
        conn = _conn()
        try:
            existing = conn.execute(
                "SELECT id FROM watch_alerts WHERE rule_key = ? AND dismissed = 0",
                (rule_key,),
            ).fetchone()
            if existing:
                return None
            alert_id = str(uuid.uuid4())[:8]
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO watch_alerts (id, message, category, severity, created_at, rule_key)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (alert_id, message, category, severity, now, rule_key),
            )
            conn.commit()
            return WatchAlert(
                id=alert_id, message=message, category=category,
                severity=severity, created_at=now, dismissed=False, rule_key=rule_key,
            )
        finally:
            conn.close()

    def resolve_alert(self, rule_key: str) -> bool:
        """Auto-dismiss any active alerts with this rule_key. Returns True if any were resolved."""
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE watch_alerts SET dismissed = 1 WHERE rule_key = ? AND dismissed = 0",
                (rule_key,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def dismiss_alert(self, alert_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute(
                "UPDATE watch_alerts SET dismissed = 1 WHERE id = ?", (alert_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_alert(self, alert_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM watch_alerts WHERE id = ?", (alert_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_alert(self, rule_key: str, message: str, severity: str | None = None) -> bool:
        """Update the message (and optionally severity) of an active alert by rule_key."""
        conn = _conn()
        try:
            if severity:
                cur = conn.execute(
                    "UPDATE watch_alerts SET message = ?, severity = ? WHERE rule_key = ? AND dismissed = 0",
                    (message, severity, rule_key),
                )
            else:
                cur = conn.execute(
                    "UPDATE watch_alerts SET message = ? WHERE rule_key = ? AND dismissed = 0",
                    (message, rule_key),
                )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_active_by_prefix(self, prefix: str) -> list[WatchAlert]:
        """Return all active alerts whose rule_key starts with the given prefix."""
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM watch_alerts WHERE rule_key LIKE ? AND dismissed = 0 ORDER BY created_at DESC",
                (f"{prefix}%",),
            ).fetchall()
            return [_row_to_alert(r) for r in rows]
        finally:
            conn.close()
