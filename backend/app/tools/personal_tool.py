"""Personal Operations tools — reminders, tasks, calendar."""
from __future__ import annotations

import re
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Shared result helper ──────────────────────────────────────────────────────

def _make_result(ok: bool, tool: str, summary: str, data, error: str | None) -> dict:
    return {"ok": ok, "tool": tool, "node": None, "summary": summary, "data": data, "error": error}


# ── Time utilities ────────────────────────────────────────────────────────────

_DAYS_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}

_DEFAULT_HOUR = 9
_DEFAULT_MIN = 0


def _parse_clock(s: str) -> Optional[tuple[int, int]]:
    """Parse "9am", "9:30pm", "14:00" → (hour, minute). Returns None on failure."""
    s = s.strip().lower()
    m = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$', s)
    if not m:
        return None
    h, mins = int(m.group(1)), int(m.group(2) or 0)
    ampm = m.group(3)
    if ampm == 'pm' and h != 12:
        h += 12
    elif ampm == 'am' and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mins <= 59):
        return None
    return h, mins


def _local_to_utc(dt: datetime) -> str:
    """Convert naive local datetime to UTC ISO string."""
    return dt.astimezone().astimezone(timezone.utc).isoformat()


def _utc_to_local(iso: str) -> datetime:
    """Convert UTC ISO string to naive local datetime."""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().replace(tzinfo=None)


def _fmt_time(dt: datetime) -> str:
    """Format as "9:00am" (no leading zero)."""
    s = dt.strftime("%I:%M%p").lower()
    return s.lstrip("0") or "12:00am"


def _fmt_datetime(dt: datetime) -> str:
    """Format as "Mon Jun 12 at 9:00am"."""
    return dt.strftime("%a %b %-d") + f" at {_fmt_time(dt)}"


def _fmt_datetime_win(dt: datetime) -> str:
    """Windows-safe format (no %-d)."""
    day = str(dt.day)
    return dt.strftime("%a %b ") + day + f" at {_fmt_time(dt)}"


def _recurrence_label(recurrence: str, dt: datetime) -> str:
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if recurrence == "once":
        return _fmt_datetime_win(dt)
    if recurrence == "daily":
        return f"every day at {_fmt_time(dt)}"
    if recurrence.startswith("weekly:"):
        wd = int(recurrence.split(":")[1])
        return f"every {day_names[wd]} at {_fmt_time(dt)}"
    if recurrence.startswith("monthly:"):
        day_n = recurrence.split(":")[1]
        return f"every month on the {day_n} at {_fmt_time(dt)}"
    return recurrence


def parse_when(when_text: str) -> tuple[str, str]:
    """Parse natural language time → (utc_iso, recurrence).

    recurrence: "once" | "daily" | "weekly:N" | "monthly:N"
    Raises ValueError if unparseable.
    """
    now = datetime.now()  # naive local
    text = when_text.lower().strip()

    # Extract explicit clock time
    clock_m = re.search(
        r'\bat\s+(\d{1,2}(?::\d{2})?\s*[ap]m?)\b'
        r'|\bat\s+(\d{1,2}:\d{2})\b',
        text,
    )
    if clock_m:
        raw = (clock_m.group(1) or clock_m.group(2) or "").strip()
        clock = _parse_clock(raw)
    else:
        clock = None
    h, mins = clock if clock else (_DEFAULT_HOUR, _DEFAULT_MIN)

    # ── "in N seconds/minutes/hours/days" ────────────────────────────────────
    m = re.search(r'\bin\s+(\d+)\s+(second|minute|hour|day)s?\b', text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {'second': timedelta(seconds=n), 'minute': timedelta(minutes=n),
                 'hour': timedelta(hours=n), 'day': timedelta(days=n)}[unit]
        return _local_to_utc(now + delta), 'once'

    # ── "every ..." ───────────────────────────────────────────────────────────
    every_m = re.search(
        r'\bevery\s+(day|morning|evening|night|week|month'
        r'|monday|tuesday|wednesday|thursday|friday|saturday|sunday'
        r'|mon|tue|wed|thu|fri|sat|sun)\b',
        text,
    )
    if every_m:
        period = every_m.group(1)
        if period == 'morning' and not clock:
            h = 8
        elif period in ('evening', 'night') and not clock:
            h = 19
        if period in ('day', 'morning', 'evening', 'night'):
            trigger = now.replace(hour=h, minute=mins, second=0, microsecond=0)
            if trigger <= now:
                trigger += timedelta(days=1)
            return _local_to_utc(trigger), 'daily'
        if period == 'week':
            trigger = (now + timedelta(weeks=1)).replace(hour=h, minute=mins, second=0, microsecond=0)
            return _local_to_utc(trigger), f'weekly:{now.weekday()}'
        if period == 'month':
            month = now.month + 1 if now.month < 12 else 1
            year = now.year if now.month < 12 else now.year + 1
            day = min(now.day, monthrange(year, month)[1])
            trigger = now.replace(year=year, month=month, day=day, hour=h, minute=mins, second=0, microsecond=0)
            return _local_to_utc(trigger), f'monthly:{now.day}'
        if period in _DAYS_MAP:
            target_wd = _DAYS_MAP[period]
            days_ahead = (target_wd - now.weekday()) % 7 or 7
            trigger = (now + timedelta(days=days_ahead)).replace(hour=h, minute=mins, second=0, microsecond=0)
            return _local_to_utc(trigger), f'weekly:{target_wd}'

    # ── "tomorrow" ────────────────────────────────────────────────────────────
    if 'tomorrow' in text:
        trigger = (now + timedelta(days=1)).replace(hour=h, minute=mins, second=0, microsecond=0)
        return _local_to_utc(trigger), 'once'

    # ── "today" / "tonight" ──────────────────────────────────────────────────
    if 'tonight' in text and not clock:
        h = 20
    if 'today' in text or 'tonight' in text:
        trigger = now.replace(hour=h, minute=mins, second=0, microsecond=0)
        if trigger <= now:
            trigger += timedelta(days=1)
        return _local_to_utc(trigger), 'once'

    # ── "this morning/evening/afternoon" ─────────────────────────────────────
    if re.search(r'\bthis\s+morning\b', text) and not clock:
        h = 8
    elif re.search(r'\bthis\s+(?:evening|night)\b', text) and not clock:
        h = 19
    elif re.search(r'\bthis\s+afternoon\b', text) and not clock:
        h = 14
    if re.search(r'\bthis\s+(?:morning|evening|night|afternoon)\b', text):
        trigger = now.replace(hour=h, minute=mins, second=0, microsecond=0)
        if trigger <= now:
            trigger += timedelta(days=1)
        return _local_to_utc(trigger), 'once'

    # ── Named day ────────────────────────────────────────────────────────────
    day_m = re.search(
        r'\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b',
        text,
    )
    if day_m:
        force_next = bool(day_m.group(1))
        target_wd = _DAYS_MAP[day_m.group(2)]
        days_ahead = (target_wd - now.weekday()) % 7
        if days_ahead == 0 or force_next:
            days_ahead = days_ahead or 7
            if force_next:
                days_ahead = max(days_ahead, 7)
        trigger = (now + timedelta(days=days_ahead)).replace(hour=h, minute=mins, second=0, microsecond=0)
        return _local_to_utc(trigger), 'once'

    # ── Just a clock time ────────────────────────────────────────────────────
    if clock:
        trigger = now.replace(hour=h, minute=mins, second=0, microsecond=0)
        if trigger <= now:
            trigger += timedelta(days=1)
        return _local_to_utc(trigger), 'once'

    raise ValueError(f"Could not understand time: {when_text!r}")


def _split_remind_raw(raw: str) -> tuple[str, str]:
    """Extract (message, when_text) from raw reminder text.

    Handles:
      "in 10 minutes to check pi5"
      "tomorrow at 9am to review logs"
      "every Friday to backup Brain63"
      "to check pi5 tomorrow"
    """
    # Strip leading intent phrase
    text = re.sub(
        r'^(?:remind\s+me|set\s+(?:a\s+)?reminder(?:\s+for)?)\s*',
        '', raw, flags=re.I
    ).strip()

    _WHEN_PAT = (
        r'(?:'
        r'in\s+\d+\s+\w+'                                       # "in 10 minutes"
        r'|tomorrow(?:\s+at\s+\d{1,2}(?::\d{2})?\s*[apm]*)?'   # "tomorrow [at X]"
        r'|today(?:\s+at\s+\d{1,2}(?::\d{2})?\s*[apm]*)?'      # "today [at X]"
        r'|tonight'
        r'|every\s+\w+(?:\s+at\s+\d{1,2}(?::\d{2})?\s*[apm]*)?' # "every Monday [at X]"
        r'|next\s+\w+(?:\s+at\s+\d{1,2}(?::\d{2})?\s*[apm]*)?'  # "next Monday [at X]"
        r'|(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)(?:\s+at\s+\d{1,2}(?::\d{2})?\s*[apm]*)?'
        r'|at\s+\d{1,2}(?::\d{2})?\s*[apm]+'                   # "at 9am"
        r'|this\s+(?:morning|evening|night|afternoon)'
        r')'
    )

    # Pattern: "[when] to [message]"
    m = re.match(rf'^({_WHEN_PAT})\s+to\s+(.+)$', text, re.I)
    if m:
        return m.group(2).strip(), m.group(1).strip()

    # Pattern: "to [message] [when]"
    m = re.match(rf'^to\s+(.+?)\s+({_WHEN_PAT})[\?\.!]?$', text, re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # Pattern: "to [message]" — no time, fire in 1 minute
    m = re.match(r'^to\s+(.+)$', text, re.I)
    if m:
        return m.group(1).strip(), 'in 1 minute'

    # Raw message with no structure
    return text.strip(), 'in 1 minute'


def _parse_event_raw(raw: str) -> tuple[str, str, Optional[str]]:
    """Extract (title, start_text, end_text|None) from raw event description."""
    text = re.sub(
        r'^(?:create|add|schedule|book)\s+(?:a[n]?\s+)?(?:new\s+)?'
        r'(?:event|meeting|appointment|call)(?:\s+(?:called|named|titled))?\s*',
        '', raw, flags=re.I,
    ).strip()

    # "[time] called/named/for [title]"
    m = re.search(r'\b(?:called|named|titled|:)\s+(.+?)[\?\.!]?$', text, re.I)
    if m:
        title = m.group(1).strip()
        when_text = text[:m.start()].strip()
        return title, when_text, None

    # "[title] on/tomorrow/Monday/... [at X]"
    m = re.match(
        r'^(.+?)\s+((?:on\s+)?(?:tomorrow|today|next\s+\w+'
        r'|monday|tuesday|wednesday|thursday|friday|saturday|sunday'
        r'|\d+/\d+)(?:\s+at\s+\S+)?)',
        text, re.I,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip(), None

    return text, '', None


# ── Reminder tools ────────────────────────────────────────────────────────────

def set_reminder(raw: str) -> dict:
    """Create a reminder from natural language text."""
    from backend.app.services.reminder_service import ReminderService

    message, when_text = _split_remind_raw(raw)
    if not message:
        return _make_result(
            False, "set_reminder",
            "No message found in reminder text.",
            None, "Say: 'remind me [when] to [what]'",
        )
    try:
        trigger_at, recurrence = parse_when(when_text)
    except ValueError as exc:
        return _make_result(
            False, "set_reminder",
            f"Could not parse time: {when_text!r}",
            None, str(exc),
        )

    svc = ReminderService()
    reminder = svc.create_reminder(message=message, trigger_at=trigger_at, recurrence=recurrence)
    local_dt = _utc_to_local(trigger_at)
    when_label = _recurrence_label(recurrence, local_dt)
    return _make_result(
        True, "set_reminder",
        f"Reminder set: '{message}' — {when_label}",
        {"id": reminder.id, "message": message, "trigger_at": trigger_at,
         "recurrence": recurrence, "when_label": when_label},
        None,
    )


def list_reminders() -> dict:
    from backend.app.services.reminder_service import ReminderService
    svc = ReminderService()
    reminders = svc.list_reminders(include_completed=False)
    data = []
    for r in reminders:
        local_dt = _utc_to_local(r.trigger_at)
        data.append({
            "id": r.id, "message": r.message,
            "trigger_at": r.trigger_at,
            "recurrence": r.recurrence,
            "when_label": _recurrence_label(r.recurrence, local_dt),
        })
    return _make_result(
        True, "list_reminders",
        f"{len(reminders)} active reminder{'s' if len(reminders) != 1 else ''}",
        {"reminders": data, "count": len(reminders)},
        None,
    )


def delete_reminder(query: str) -> dict:
    from backend.app.services.reminder_service import ReminderService
    svc = ReminderService()
    reminder = svc.find_by_query(query)
    if not reminder:
        return _make_result(
            False, "delete_reminder",
            f"No active reminder matching '{query}'.",
            None, "Not found.",
        )
    svc.delete_reminder(reminder.id)
    return _make_result(
        True, "delete_reminder",
        f"Deleted reminder: '{reminder.message}'",
        {"id": reminder.id, "message": reminder.message},
        None,
    )


def complete_reminder(query: str) -> dict:
    from backend.app.services.reminder_service import ReminderService
    svc = ReminderService()
    reminder = svc.find_by_query(query)
    if not reminder:
        return _make_result(
            False, "complete_reminder",
            f"No active reminder matching '{query}'.",
            None, "Not found.",
        )
    svc.complete_reminder(reminder.id)
    return _make_result(
        True, "complete_reminder",
        f"Marked complete: '{reminder.message}'",
        {"id": reminder.id, "message": reminder.message},
        None,
    )


# ── Task tools ────────────────────────────────────────────────────────────────

def add_task(title: str, project: str = "") -> dict:
    from backend.app.services.task_service import TaskService
    if not title.strip():
        return _make_result(False, "add_task", "No task title provided.", None, "Provide a title.")
    svc = TaskService()
    task = svc.create_task(title=title.strip(), project=project.strip() or None)
    proj_note = f" [{task.project}]" if task.project else ""
    return _make_result(
        True, "add_task",
        f"Task added: '{task.title}'{proj_note}",
        {"id": task.id, "title": task.title, "project": task.project, "status": task.status},
        None,
    )


def list_tasks(filter: str = "pending") -> dict:
    from backend.app.services.task_service import TaskService
    svc = TaskService()
    status_key = filter if filter in ("pending", "done", "all") else "pending"
    tasks = svc.list_tasks(status=status_key)
    data = [{"id": t.id, "title": t.title, "status": t.status,
             "priority": t.priority, "project": t.project} for t in tasks]
    label = f"{len(tasks)} {status_key} task{'s' if len(tasks) != 1 else ''}"
    return _make_result(True, "list_tasks", label, {"tasks": data, "count": len(tasks), "filter": status_key}, None)


def complete_task(query: str) -> dict:
    from backend.app.services.task_service import TaskService
    svc = TaskService()
    task = svc.find_by_query(query)
    if not task:
        return _make_result(False, "complete_task", f"No task matching '{query}'.", None, "Not found.")
    svc.complete_task(task.id)
    return _make_result(True, "complete_task", f"Completed: '{task.title}'",
                        {"id": task.id, "title": task.title}, None)


def delete_task(query: str) -> dict:
    from backend.app.services.task_service import TaskService
    svc = TaskService()
    task = svc.find_by_query(query)
    if not task:
        return _make_result(False, "delete_task", f"No task matching '{query}'.", None, "Not found.")
    svc.delete_task(task.id)
    return _make_result(True, "delete_task", f"Deleted: '{task.title}'",
                        {"id": task.id, "title": task.title}, None)


# ── Calendar tools ────────────────────────────────────────────────────────────

def get_calendar_today() -> dict:
    from backend.app.services.calendar_service import CalendarService
    svc = CalendarService()
    events = svc.get_today()
    data = [{"id": e.id, "title": e.title, "start_at": e.start_at, "end_at": e.end_at,
             "location": e.location} for e in events]
    return _make_result(
        True, "get_calendar_today",
        f"{len(events)} event{'s' if len(events) != 1 else ''} today",
        {"events": data, "count": len(events)},
        None,
    )


def get_upcoming_events(days: int = 7) -> dict:
    from backend.app.services.calendar_service import CalendarService
    svc = CalendarService()
    days = max(1, min(days, 90))
    events = svc.get_upcoming(days)
    data = [{"id": e.id, "title": e.title, "start_at": e.start_at, "end_at": e.end_at,
             "location": e.location} for e in events]
    return _make_result(
        True, "get_upcoming_events",
        f"{len(events)} event{'s' if len(events) != 1 else ''} in the next {days} day{'s' if days != 1 else ''}",
        {"events": data, "count": len(events), "days": days},
        None,
    )


def create_calendar_event(raw: str) -> dict:
    from backend.app.services.calendar_service import CalendarService
    from backend.app.models.personal import CalendarEventCreate

    title, start_text, end_text = _parse_event_raw(raw)
    if not title:
        return _make_result(
            False, "create_calendar_event",
            "No event title found.",
            None, "Say: 'create an event [title] [when]'",
        )
    if not start_text:
        return _make_result(
            False, "create_calendar_event",
            "No time specified for the event.",
            None, "Include a date/time: 'create event DroneHive Review tomorrow at 3pm'",
        )
    try:
        start_iso, _ = parse_when(start_text)
    except ValueError as exc:
        return _make_result(
            False, "create_calendar_event",
            f"Could not parse start time: {start_text!r}",
            None, str(exc),
        )

    end_iso = None
    if end_text:
        try:
            end_iso, _ = parse_when(end_text)
        except ValueError:
            end_iso = None

    svc = CalendarService()
    event = svc.create_event(CalendarEventCreate(title=title, start_at=start_iso, end_at=end_iso))
    local_dt = _utc_to_local(start_iso)
    when_label = _fmt_datetime_win(local_dt)
    return _make_result(
        True, "create_calendar_event",
        f"Event created: '{event.title}' — {when_label}",
        {"id": event.id, "title": event.title, "start_at": start_iso,
         "end_at": end_iso, "when_label": when_label},
        None,
    )


def delete_calendar_event(query: str) -> dict:
    from backend.app.services.calendar_service import CalendarService
    svc = CalendarService()
    event = svc.find_event(query)
    if not event:
        return _make_result(
            False, "delete_calendar_event",
            f"No event matching '{query}'.",
            None, "Not found.",
        )
    svc.delete_event(event.id)
    return _make_result(
        True, "delete_calendar_event",
        f"Deleted event: '{event.title}'",
        {"id": event.id, "title": event.title},
        None,
    )
