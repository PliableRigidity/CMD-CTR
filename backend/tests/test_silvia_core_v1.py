from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest

import backend.app.services.task_service as task_module
import backend.app.services.reminder_service as reminder_module
from backend.app.models.assistant import AssistantRequest
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.app.services.task_service import AmbiguousTaskError, TaskService
from backend.app.services.reminder_service import AmbiguousReminderError, ReminderService
from backend.app.services.core_assistant import handle_core_intent
from backend.app.services.core_calendar_service import CoreCalendarService, CalendarAuthError, CalendarExternalError
from backend.utils.logger import SecretRedactionFilter, redact_secrets


@pytest.fixture()
def core_db(tmp_path, monkeypatch):
    path = tmp_path / "core.db"
    monkeypatch.setattr(task_module, "DB_PATH", path)
    monkeypatch.setattr(reminder_module, "DB_PATH", path)
    return path


def iso_after(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


def test_task_crud_reschedule_reopen_and_persistence(core_db):
    svc = TaskService()
    task = svc.create_task("Finish PCB schematic", priority="high", due_at=iso_after(days=1))
    assert svc.get_task(task.id).title == "Finish PCB schematic"
    moved = svc.reschedule_task(task.id, iso_after(days=3))
    assert moved.id == task.id
    assert svc.complete_task(task.id)
    assert TaskService().get_task(task.id).status == "completed"
    assert TaskService().reopen_task(task.id)
    assert TaskService().get_task(task.id).status == "open"
    assert TaskService().cancel_task(task.id)
    assert TaskService().get_task(task.id).status == "cancelled"


def test_task_duplicate_avoidance_and_ambiguity(core_db):
    svc = TaskService()
    one = svc.create_task("Finish ARM benchmark")
    duplicate = svc.create_task(" finish arm benchmark ")
    assert duplicate.id == one.id
    svc.create_task("Review ARM benchmark results")
    with pytest.raises(AmbiguousTaskError):
        svc.resolve("ARM benchmark")


def test_task_project_association_and_active_filter(core_db):
    svc = TaskService()
    task = svc.create_task("Run tests", project="SILVIA")
    assert svc.list_tasks(project="silvia")[0].id == task.id
    svc.complete_task(task.id)
    assert task.id not in {t.id for t in svc.list_tasks("active")}


def test_reminder_lifecycle_restart_and_no_duplicate_delivery(core_db):
    svc = ReminderService()
    due = iso_after(seconds=-1)
    reminder = svc.create_reminder("Collect parcel", due)
    assert ReminderService().get_reminder(reminder.id).status == "scheduled"
    assert [r.id for r in ReminderService().get_due_reminders()] == [reminder.id]
    delivered = ReminderService().record_delivery(reminder.id, True)
    assert delivered.status == "delivered"
    assert delivered.delivered_at
    assert ReminderService().get_due_reminders() == []
    ack = ReminderService().acknowledge(reminder.id)
    assert ack.status == "acknowledged" and ack.acknowledged_at


def test_reminder_snooze_cancel_recurrence_and_timezone(core_db):
    svc = ReminderService()
    reminder = svc.create_reminder("Backup notes", iso_after(seconds=-1), "daily")
    snoozed = svc.snooze(reminder.id, iso_after(hours=1))
    assert snoozed.status == "snoozed" and snoozed.trigger_at.endswith("+00:00")
    assert svc.get_due_reminders() == []
    assert svc.reschedule(reminder.id, iso_after(seconds=-1)).status == "scheduled"
    assert svc.advance_recurrence(reminder.id)
    assert svc.get_reminder(reminder.id).status == "scheduled"
    assert svc.cancel(reminder.id).status == "cancelled"


def test_reminder_duplicate_and_ambiguous_reference(core_db):
    svc = ReminderService(); when = iso_after(days=1)
    first = svc.create_reminder("Call dentist", when)
    assert svc.create_reminder(" call dentist ", when).id == first.id
    svc.create_reminder("Call dentist about invoice", iso_after(days=2))
    with pytest.raises(AmbiguousReminderError): svc.resolve("dentist")


def test_conversational_task_scenario_updates_same_task(core_db):
    created = handle_core_intent("Add finish PCB schematic to my tasks for Friday")
    assert created["result"]["ok"]
    task_id = created["result"]["data"]["id"]
    moved = handle_core_intent("Actually move the PCB schematic task to Monday")
    assert moved["result"]["ok"] and moved["result"]["data"]["id"] == task_id
    completed = handle_core_intent("Mark the PCB schematic task as done")
    assert completed["result"]["ok"]
    assert TaskService().get_task(task_id).status == "completed"


def test_conversational_reminder_scenario_updates_same_reminder(core_db):
    created = handle_core_intent("Remind me tomorrow at 5 PM to collect my parcel")
    assert created["result"]["verification"]["persisted"]
    rid = created["result"]["data"]["id"]
    moved = handle_core_intent("Move my parcel reminder to tomorrow at 6 PM")
    assert moved["result"]["data"]["id"] == rid
    cancelled = handle_core_intent("Cancel my parcel reminder")
    assert cancelled["result"]["ok"]
    assert ReminderService().get_reminder(rid).status == "cancelled"


def test_agenda_combines_real_state_and_reports_calendar_failure(core_db, monkeypatch):
    TaskService().create_task("Due item", due_at=iso_after(hours=2))
    ReminderService().create_reminder("Due reminder", iso_after(hours=3))
    import backend.app.tools.productivity_tool as productivity
    monkeypatch.setattr(productivity, "list_gcal_events", lambda **_: {
        "ok": False, "summary": "Calendar unavailable", "data": None, "error": "network_failure"})
    result = handle_core_intent("What do I need to do today?")
    assert "Due item" in result["answer"] and "Due reminder" in result["answer"]
    assert "Calendar unavailable" in result["answer"]


class FakeCalendar:
    def __init__(self, authenticated=True, fail=False): self.authenticated=authenticated; self.fail=fail; self.events=[]
    def is_authenticated(self): return self.authenticated
    def list_events(self, date=None, days=1):
        if self.fail: raise OSError("network down")
        return list(self.events)
    def create_event(self, title, start_iso, end_iso=None, description="", location=""):
        event={"id":"evt-1","title":title,"start":start_iso,"end":end_iso or start_iso}; self.events.append(event); return event
    def get_event(self,event_id):
        match=next((e for e in self.events if e["id"]==event_id),None)
        if not match: raise KeyError(event_id)
        return dict(match)
    def update_event(self,event_id,start_iso,end_iso=None):
        event=self.get_event(event_id); event["start"]=start_iso
        self.events=[event if e["id"]==event_id else e for e in self.events]; return event
    def delete_event(self,event_id): self.events=[e for e in self.events if e["id"]!=event_id]; return True


def test_calendar_list_create_update_delete_and_verification():
    provider=FakeCalendar(); service=CoreCalendarService(provider)
    assert service.list_events()==[]
    event=service.create(title="Dentist",start_iso=iso_after(days=2),end_iso=None,description="",location="")
    assert event["id"]=="evt-1"
    moved=service.update(event["id"],iso_after(days=2,hours=1)); assert moved["id"]==event["id"]
    assert service.delete(event["id"]); assert service.list_events()==[]


def test_calendar_auth_and_api_failures_are_explicit():
    with pytest.raises(CalendarAuthError): CoreCalendarService(FakeCalendar(authenticated=False)).list_events()
    with pytest.raises(CalendarExternalError): CoreCalendarService(FakeCalendar(fail=True)).list_events()


def test_recommendation_uses_real_actionable_tasks(core_db):
    svc=TaskService(); chosen=svc.create_task("Urgent real task",priority="high",due_at=iso_after(hours=3),estimated_minutes=45)
    blocked=svc.create_task("Blocked task",priority="critical",due_at=iso_after(hours=1)); svc.update_task(blocked.id,status="blocked")
    done=svc.create_task("Completed task",priority="critical"); svc.complete_task(done.id)
    result=handle_core_intent("I have one hour. What should I work on?")
    assert chosen.title in result["answer"]
    assert blocked.title not in result["answer"] and done.title not in result["answer"]


def test_magi_nonexistent_project_is_grounded():
    router = AssistantPlatformRouter()
    request = AssistantRequest(query="What should I work on for ProjectThatDoesNotExist?", mode="decision", session_id="core-test")
    response = asyncio.run(router.handle(request))
    assert "couldn't find a project" in response.answer.lower()
    assert "ProjectThatDoesNotExist" in response.answer


@pytest.mark.parametrize("secret", [
    "https://api.telegram.org/bot123456:ABC_secret/getMe",
    "https://x.test/?api_key=abc123&foo=bar",
    "Authorization: Bearer abc.def.ghi",
    "client_secret=super-secret",
])
def test_secret_redaction(secret):
    redacted = redact_secrets(secret)
    assert "[REDACTED]" in redacted
    assert "abc123" not in redacted and "super-secret" not in redacted and "abc.def.ghi" not in redacted


def test_logging_filter_redacts_formatted_arguments():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "request %s", ("?token=secret",), None)
    assert SecretRedactionFilter().filter(record)
    assert "secret" not in record.msg
