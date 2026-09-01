"""Canonical natural-language date/time interpretation for SILVIA.

All returned datetimes are timezone-aware.  Callers decide whether a date-only
result is acceptable; the parser never invents a clock time for one.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.app.tools.time_tool import get_user_timezone


MONTHS = {name: i for i, names in enumerate((
    ("january", "jan"), ("february", "feb"), ("march", "mar"),
    ("april", "apr"), ("may",), ("june", "jun"), ("july", "jul"),
    ("august", "aug"), ("september", "sep", "sept"),
    ("october", "oct"), ("november", "nov"), ("december", "dec")), 1)
    for name in names}
DAYS = {name: i for i, name in enumerate(
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}
DAYS.update({name[:3]: value for name, value in list(DAYS.items())})
PARTS = {"morning": time(8), "afternoon": time(14), "evening": time(19), "night": time(20)}


@dataclass(frozen=True)
class DateTimeParseResult:
    resolved_date: str | None
    resolved_time: str | None
    local_iso: str | None
    utc_iso: str | None
    timezone: str
    precision: str
    all_day: bool
    needs_time: bool
    recurrence: str | None
    ambiguity: str | None
    original_input: str

    def model_dump(self) -> dict:
        return asdict(self)


def _clock(text: str) -> time | None:
    match = re.search(r"(?:\bat(?:\s+around)?\s+|(?<!\d))([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)?\b", text)
    if not match:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2) or 0), match.group(3)
    if meridiem and not 1 <= hour <= 12:
        return None
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return time(hour, minute)


def parse_datetime(text: str, *, now: datetime | None = None) -> DateTimeParseResult:
    original = text
    clean = re.sub(r"\b(?:for|on)\s+(?:the\s+)?(?=\d|tomorrow|today|next|this)", "", text.lower().strip())
    clean = re.sub(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)?\s+of\s+", r"\1 ", clean)
    tz_name = get_user_timezone()
    tz = ZoneInfo(tz_name)
    current = now.astimezone(tz) if now else datetime.now(tz)
    clock = _clock(clean)
    ambiguity = None
    recurrence = None
    target: date | None = None

    relative = re.search(r"\bin\s+(\d+)\s+(minute|hour|day)s?\b", clean)
    if relative:
        amount, unit = int(relative.group(1)), relative.group(2)
        instant = current + {"minute": timedelta(minutes=amount), "hour": timedelta(hours=amount), "day": timedelta(days=amount)}[unit]
        return _result(original, tz_name, instant.date(), instant.timetz().replace(tzinfo=None), "minute", False, None, None)

    if "day after tomorrow" in clean:
        target = current.date() + timedelta(days=2)
    elif "tomorrow" in clean:
        target = current.date() + timedelta(days=1)
    elif "tonight" in clean or "later today" in clean or re.search(r"\btoday\b", clean):
        target = current.date()
        if not clock:
            clock = time(20) if "tonight" in clean else None
    elif "this weekend" in clean:
        target = current.date() + timedelta(days=(5 - current.weekday()) % 7)
        ambiguity = "weekend interpreted as Saturday"
    elif "next week" in clean:
        target = current.date() + timedelta(days=7 - current.weekday())

    explicit = re.search(
        r"\b(?:(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)|([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?)(?:[,.]?\s+(\d{4}))?\b", clean)
    if explicit and (explicit.group(2) in MONTHS or explicit.group(3) in MONTHS):
        day = int(explicit.group(1) or explicit.group(4))
        month = MONTHS[explicit.group(2) or explicit.group(3)]
        year = int(explicit.group(5) or current.year)
        target = date(year, month, day)
        if not explicit.group(5) and target < current.date():
            target = target.replace(year=year + 1)

    every = re.search(r"\bevery\s+(weekday|day|morning|evening|night|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", clean)
    first_month = re.search(r"\b(?:on\s+)?the\s+first\s+of\s+every\s+month\b", text.lower())
    if first_month:
        recurrence = "monthly:1"
        first = current.date().replace(day=1)
        target = first if first > current.date() else (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    elif every:
        token = every.group(1)
        if token == "weekday":
            recurrence = "weekdays"
            days = 1
            while (current + timedelta(days=days)).weekday() > 4:
                days += 1
            target = current.date() + timedelta(days=days)
        elif token in DAYS:
            recurrence = f"weekly:{DAYS[token]}"
            delta = (DAYS[token] - current.weekday()) % 7 or 7
            target = current.date() + timedelta(days=delta)
        else:
            recurrence = "daily"
            target = current.date() + timedelta(days=1)
            if not clock and token in PARTS:
                clock = PARTS[token]

    weekday = re.search(r"\b(this|next)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", clean)
    if not recurrence and weekday and not explicit:
        qualifier, token = weekday.group(1), weekday.group(2)
        delta = (DAYS[token] - current.weekday()) % 7
        if qualifier == "next":
            delta = delta or 7
            if delta < 7:
                delta += 7
        elif delta == 0:
            delta = 7
        target = current.date() + timedelta(days=delta)

    if not clock:
        for label, value in PARTS.items():
            if re.search(rf"\b{label}\b", clean):
                clock = value
                break
        if "after lunch" in clean:
            clock = time(14)

    if target is None and clock:
        target = current.date()
        candidate = datetime.combine(target, clock, tz)
        if candidate <= current:
            target += timedelta(days=1)
    if target is None:
        raise ValueError(f"Could not understand date/time: {original!r}")
    return _result(original, tz_name, target, clock, "minute" if clock else "date", clock is None, recurrence, ambiguity)


def _result(original: str, tz_name: str, day: date, clock: time | None, precision: str,
            all_day: bool, recurrence: str | None, ambiguity: str | None) -> DateTimeParseResult:
    if clock is None:
        return DateTimeParseResult(day.isoformat(), None, None, None, tz_name, precision, all_day, True, recurrence, ambiguity, original)
    local = datetime.combine(day, clock, ZoneInfo(tz_name))
    return DateTimeParseResult(day.isoformat(), clock.strftime("%H:%M:%S"), local.isoformat(),
                               local.astimezone(timezone.utc).isoformat(), tz_name, precision, False,
                               False, recurrence, ambiguity, original)


def parse_event_request(text: str, *, now: datetime | None = None) -> tuple[str, DateTimeParseResult]:
    """Extract an event title and schedule regardless of title/date order."""
    stripped = re.sub(r"^(?:please\s+)?(?:create|add|schedule|book)\s+(?:a[n]?\s+)?(?:new\s+)?(?:calendar\s+)?(?:event|meeting|appointment|call)?\s*", "", text, flags=re.I).strip()
    stripped = re.sub(r"^put\s+", "", stripped, flags=re.I)
    # Natural date-first forms: "for whole day 27th August: Title".
    date_first = re.match(r"^(?:for\s+)?(?:(?:the\s+)?whole\s+day|all[- ]day)\s+(.+?)\s*:\s*(.+)$", stripped, re.I)
    if date_first:
        return date_first.group(2).strip(), parse_datetime(date_first.group(1), now=now)
    # Date-first requests commonly use punctuation as a natural title separator.
    pieces = [piece.strip(" .") for piece in re.split(r"[.;]\s*", stripped, maxsplit=1)]
    if len(pieces) == 2:
        try:
            parsed = parse_datetime(pieces[0], now=now)
            return pieces[1], parsed
        except ValueError:
            pass
    month = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    date_pattern = rf"(?:for|on)?\s*(?:the\s+)?(?:\d{{1,2}}(?:st|nd|rd|th)?(?:\s+of)?\s+{month}|{month}\s+\d{{1,2}}(?:st|nd|rd|th)?|tomorrow|today|this\s+\w+|next\s+\w+)(?:\s+at(?:\s+around)?\s+\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm)?)?"
    match = re.search(date_pattern, stripped, re.I)
    if not match:
        raise ValueError("No date/time found in event request")
    title = (stripped[:match.start()] + " " + stripped[match.end():]).strip(" ,.-")
    title = re.sub(r"\b(?:in\s+my\s+calendar|calendar|event\s+called|called|all[- ]day|whole\s+day)\b", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" ,.-:")
    parsed = parse_datetime(match.group(0), now=now)
    if not title:
        raise ValueError("No event title found")
    return title, parsed
