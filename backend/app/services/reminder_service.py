"""Canonical persistent reminder lifecycle and delivery ledger."""
from __future__ import annotations

import re
import sqlite3
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.models.personal import Reminder

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"
ACTIVE = {"scheduled", "delivered", "snoozed", "failed"}


class AmbiguousReminderError(ValueError):
    def __init__(self, query: str, matches: list[Reminder]):
        self.query, self.matches = query, matches
        super().__init__(f"Multiple reminders match '{query}'.")


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False); c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); return c


def _init_db():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS reminders (
          id TEXT PRIMARY KEY, message TEXT NOT NULL, trigger_at TEXT NOT NULL,
          recurrence TEXT NOT NULL DEFAULT 'once', completed INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, last_fired_at TEXT)""")
        existing = {r[1] for r in c.execute("PRAGMA table_info(reminders)")}
        additions = {"status":"TEXT NOT NULL DEFAULT 'scheduled'", "updated_at":"TEXT",
          "delivered_at":"TEXT", "acknowledged_at":"TEXT", "snoozed_until":"TEXT",
          "delivery_status":"TEXT NOT NULL DEFAULT 'pending'", "delivery_error":"TEXT",
          "source":"TEXT NOT NULL DEFAULT 'chat'", "task_id":"TEXT", "event_id":"TEXT"}
        for n, ddl in additions.items():
            if n not in existing: c.execute(f"ALTER TABLE reminders ADD COLUMN {n} {ddl}")
        now = datetime.now(timezone.utc).isoformat()
        c.execute("UPDATE reminders SET status='acknowledged' WHERE completed=1 AND status='scheduled'")
        c.execute("UPDATE reminders SET updated_at=COALESCE(updated_at,created_at,?)", (now,))
        c.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status,trigger_at)")


def _rem(row):
    d = dict(row); d["completed"] = bool(d["completed"]); return Reminder(**d)
def _norm(s): return " ".join(re.findall(r"[a-z0-9]+", s.lower()))
def _aware(iso: str) -> datetime:
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


class ReminderService:
    def __init__(self): _init_db()

    def get_reminder(self, reminder_id: str) -> Reminder | None:
        with _conn() as c:
            r = c.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
            return _rem(r) if r else None

    def create_reminder(self, message: str, trigger_at: str, recurrence: str = "once",
                        source: str = "chat", task_id: str | None = None,
                        event_id: str | None = None) -> Reminder:
        message = message.strip()
        if not message: raise ValueError("Reminder message is required.")
        trigger_at = _aware(trigger_at).isoformat()
        duplicate = self.find_exact_active(message, trigger_at, recurrence)
        if duplicate: return duplicate
        rid, now = str(uuid.uuid4())[:8], datetime.now(timezone.utc).isoformat()
        with _conn() as c:
            c.execute("""INSERT INTO reminders
              (id,message,trigger_at,recurrence,completed,created_at,status,updated_at,delivery_status,source,task_id,event_id)
              VALUES (?,?,?,?,0,?,'scheduled',?,'pending',?,?,?)""",
              (rid,message,trigger_at,recurrence,now,now,source,task_id,event_id))
        stored = self.get_reminder(rid)
        if not stored: raise RuntimeError("Reminder could not be verified after saving.")
        return stored

    def list_reminders(self, include_completed: bool = False) -> list[Reminder]:
        sql = "SELECT * FROM reminders"
        if not include_completed: sql += " WHERE status IN ('scheduled','delivered','snoozed','failed')"
        sql += " ORDER BY trigger_at"
        with _conn() as c: return [_rem(r) for r in c.execute(sql).fetchall()]

    def get_due_reminders(self, now: datetime | None = None) -> list[Reminder]:
        now_iso = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        with _conn() as c:
            rows = c.execute("""SELECT * FROM reminders WHERE status IN ('scheduled','snoozed','failed')
              AND COALESCE(snoozed_until,trigger_at)<=? ORDER BY trigger_at""", (now_iso,)).fetchall()
            return [_rem(r) for r in rows]

    def find_matches(self, query: str) -> list[Reminder]:
        q = _norm(query)
        with _conn() as c:
            row = c.execute("SELECT * FROM reminders WHERE id=?", (query,)).fetchone()
            if row: return [_rem(row)]
            items = [_rem(r) for r in c.execute("SELECT * FROM reminders WHERE status IN ('scheduled','delivered','snoozed','failed') ORDER BY trigger_at").fetchall()]
        exact = [r for r in items if _norm(r.message) == q]
        if exact: return exact
        words = set(q.split())
        return [r for r in items if q in _norm(r.message) or words.issubset(set(_norm(r.message).split()))]

    def resolve(self, query: str) -> Reminder | None:
        matches = self.find_matches(query)
        if len(matches)>1: raise AmbiguousReminderError(query,matches)
        return matches[0] if matches else None
    def most_recent_active(self) -> Reminder | None:
        """Return the last actively modified reminder for conversational 'that'."""
        with _conn() as c:
            row = c.execute("""SELECT * FROM reminders
              WHERE status IN ('scheduled','delivered','snoozed','failed')
              ORDER BY COALESCE(updated_at,created_at) DESC LIMIT 1""").fetchone()
            return _rem(row) if row else None
    def find_by_query(self, query: str): return self.resolve(query)

    def find_exact_active(self, message, trigger_at, recurrence):
        with _conn() as c:
            r = c.execute("""SELECT * FROM reminders WHERE LOWER(TRIM(message))=LOWER(TRIM(?))
              AND trigger_at=? AND recurrence=? AND status IN ('scheduled','delivered','snoozed','failed') LIMIT 1""",
              (message,trigger_at,recurrence)).fetchone()
            return _rem(r) if r else None

    def _update(self, reminder_id: str, **changes) -> Reminder | None:
        allowed = {"message","trigger_at","recurrence","status","delivered_at","acknowledged_at",
                   "snoozed_until","delivery_status","delivery_error","last_fired_at","completed"}
        changes = {k:v for k,v in changes.items() if k in allowed}; changes["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ",".join(f"{k}=?" for k in changes)
        with _conn() as c:
            cur=c.execute(f"UPDATE reminders SET {sets} WHERE id=?",(*changes.values(),reminder_id))
            if not cur.rowcount: return None
        return self.get_reminder(reminder_id)

    def record_delivery(self, reminder_id: str, delivered: bool, error: str | None = None) -> Reminder | None:
        now=datetime.now(timezone.utc).isoformat()
        return self._update(reminder_id, status="delivered" if delivered else "failed",
          delivered_at=now if delivered else None, last_fired_at=now,
          delivery_status="delivered" if delivered else "failed", delivery_error=error)

    def acknowledge(self, reminder_id: str) -> Reminder | None:
        return self._update(reminder_id,status="acknowledged",completed=1,
                            acknowledged_at=datetime.now(timezone.utc).isoformat())
    def complete_reminder(self, reminder_id: str) -> bool: return self.acknowledge(reminder_id) is not None
    def cancel(self, reminder_id: str) -> Reminder | None: return self._update(reminder_id,status="cancelled",completed=1)
    def delete_reminder(self, reminder_id: str) -> bool: return self.cancel(reminder_id) is not None
    def snooze(self, reminder_id: str, until: str) -> Reminder | None:
        until=_aware(until).isoformat()
        return self._update(reminder_id,status="snoozed",trigger_at=until,snoozed_until=until,
                            delivery_status="pending",delivery_error=None)
    def reschedule(self, reminder_id: str, trigger_at: str) -> Reminder | None:
        trigger_at=_aware(trigger_at).isoformat()
        return self._update(reminder_id,status="scheduled",trigger_at=trigger_at,snoozed_until=None,
                            delivery_status="pending",delivery_error=None,completed=0)

    def advance_recurrence(self, reminder_id: str) -> bool:
        r=self.get_reminder(reminder_id)
        if not r or r.recurrence=="once": return False
        dt=_aware(r.trigger_at); rec=r.recurrence
        if rec=="daily": new=dt+timedelta(days=1)
        elif rec.startswith("weekly:"): new=dt+timedelta(weeks=1)
        elif rec.startswith("monthly:"):
            month=dt.month+1 if dt.month<12 else 1; year=dt.year if dt.month<12 else dt.year+1
            new=dt.replace(year=year,month=month,day=min(dt.day,monthrange(year,month)[1]))
        else: return False
        return self.reschedule(reminder_id,new.isoformat()) is not None
