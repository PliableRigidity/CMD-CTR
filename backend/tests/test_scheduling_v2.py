from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.datetime_service import parse_datetime, parse_event_request


NOW = datetime(2026, 8, 25, 12, tzinfo=ZoneInfo("Europe/London"))


@pytest.mark.parametrize("phrase", [
    "27th August", "for 27th August", "on 27th August", "August 27th", "27 Aug",
])
def test_date_variants(monkeypatch, phrase):
    monkeypatch.setattr("backend.app.services.datetime_service.get_user_timezone", lambda: "Europe/London")
    result = parse_datetime(phrase, now=NOW)
    assert result.resolved_date == "2026-08-27"
    assert result.timezone == "Europe/London"
    assert result.resolved_time is None


@pytest.mark.parametrize(("phrase", "day", "clock"), [
    ("tomorrow", "2026-08-26", None),
    ("tomorrow at 5pm", "2026-08-26", "17:00:00"),
    ("Friday afternoon", "2026-08-28", "14:00:00"),
    ("in 20 minutes", "2026-08-25", "12:20:00"),
    ("the day after tomorrow", "2026-08-27", None),
])
def test_relative_variants(monkeypatch, phrase, day, clock):
    monkeypatch.setattr("backend.app.services.datetime_service.get_user_timezone", lambda: "Europe/London")
    result = parse_datetime(phrase, now=NOW)
    assert (result.resolved_date, result.resolved_time) == (day, clock)


@pytest.mark.parametrize("utterance", [
    "add a new event for 27th August. Ishaan Birthday",
    "Add Ishaan Birthday on 27th August",
    "Create event Ishaan Birthday August 27th",
    "add an event for whole day 27th August: Ishaan Birthday",
    "create an all-day event called Ishaan Birthday for 27 Aug",
    "put Ishaan Birthday in my calendar on August 27",
])
def test_birthday_regression_phrasings(monkeypatch, utterance):
    monkeypatch.setattr("backend.app.services.datetime_service.get_user_timezone", lambda: "Europe/London")
    title, result = parse_event_request(utterance, now=NOW)
    assert title == "Ishaan Birthday"
    assert result.resolved_date == "2026-08-27"
    assert result.timezone == "Europe/London"


def test_timezone_conversion_handles_bst(monkeypatch):
    monkeypatch.setattr("backend.app.services.datetime_service.get_user_timezone", lambda: "Europe/London")
    result = parse_datetime("tomorrow at 5pm", now=NOW)
    assert result.local_iso.endswith("+01:00")
    assert result.utc_iso == "2026-08-26T16:00:00+00:00"


def test_implicit_timed_event_phrase_is_not_a_task(monkeypatch, tmp_path):
    import backend.app.services.calendar_service as calendar_module
    monkeypatch.setattr(calendar_module, "DB_PATH", tmp_path / "calendar.db")
    monkeypatch.setattr("backend.app.services.datetime_service.get_user_timezone", lambda: "Europe/London")
    from backend.app.services.core_assistant import handle_core_intent
    result = handle_core_intent("add Dentist on 27th August at 2pm")
    assert result["result"]["operation"] == "create_event"
    assert result["result"]["data"]["title"] == "Dentist"
    assert result["result"]["data"]["start_at"] == "2026-08-27T13:00:00+00:00"
