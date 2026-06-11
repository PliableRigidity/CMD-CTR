"""Calendar service — adapter-based calendar abstraction.

LocalCalendarAdapter is the default (SQLite). Future adapters (Google, Outlook)
implement BaseCalendarAdapter and register via CalendarService.register_adapter().
"""
from __future__ import annotations

import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.models.personal import CalendarEvent, CalendarEventCreate

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
            CREATE TABLE IF NOT EXISTS calendar_events (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                start_at    TEXT NOT NULL,
                end_at      TEXT,
                location    TEXT,
                description TEXT,
                source      TEXT NOT NULL DEFAULT 'local',
                created_at  TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()


def _row_to_event(row) -> CalendarEvent:
    return CalendarEvent(**dict(row))


# ── Adapter interface ─────────────────────────────────────────────────────────

class BaseCalendarAdapter(ABC):
    @abstractmethod
    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    @abstractmethod
    def create_event(self, data: CalendarEventCreate) -> CalendarEvent: ...

    @abstractmethod
    def delete_event(self, event_id: str) -> bool: ...

    def find_event(self, query: str) -> CalendarEvent | None:
        """Find event by partial title match within ±1 year window."""
        now = datetime.now(timezone.utc)
        events = self.get_events(now - timedelta(days=1), now + timedelta(days=365))
        q = query.lower()
        for e in events:
            if q in e.title.lower():
                return e
        return None


# ── Local SQLite adapter ──────────────────────────────────────────────────────

class LocalCalendarAdapter(BaseCalendarAdapter):
    def __init__(self) -> None:
        _init_db()

    def get_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM calendar_events WHERE start_at >= ? AND start_at <= ? ORDER BY start_at ASC",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [_row_to_event(r) for r in rows]
        finally:
            conn.close()

    def create_event(self, data: CalendarEventCreate) -> CalendarEvent:
        eid = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO calendar_events (id, title, start_at, end_at, location, description, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, data.title, data.start_at, data.end_at, data.location, data.description, data.source, now),
            )
            conn.commit()
        finally:
            conn.close()
        return CalendarEvent(
            id=eid, title=data.title, start_at=data.start_at, end_at=data.end_at,
            location=data.location, description=data.description, source=data.source, created_at=now,
        )

    def delete_event(self, event_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# ── Calendar service (adapter registry) ──────────────────────────────────────

class CalendarService:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseCalendarAdapter] = {
            "local": LocalCalendarAdapter(),
        }
        self._default = "local"

    def register_adapter(self, name: str, adapter: BaseCalendarAdapter) -> None:
        self._adapters[name] = adapter

    def _adapter(self, source: str = "local") -> BaseCalendarAdapter:
        return self._adapters.get(source, self._adapters[self._default])

    def get_today(self) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self._adapter().get_events(start, end)

    def get_upcoming(self, days: int = 7) -> list[CalendarEvent]:
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)
        return self._adapter().get_events(now, end)

    def create_event(self, data: CalendarEventCreate) -> CalendarEvent:
        return self._adapter(data.source).create_event(data)

    def delete_event(self, event_id: str) -> bool:
        for adapter in self._adapters.values():
            if adapter.delete_event(event_id):
                return True
        return False

    def find_event(self, query: str) -> CalendarEvent | None:
        for adapter in self._adapters.values():
            e = adapter.find_event(query)
            if e:
                return e
        return None
