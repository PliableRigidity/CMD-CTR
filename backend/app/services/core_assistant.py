"""Deterministic SILVIA Core conversational intents.

This runs before the general planner/LLM. It owns everyday task, reminder,
calendar, project and agenda mutations so every interface reaches the same
persistent services and no response can claim success without a re-read.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from backend.app.services.task_service import TaskService, AmbiguousTaskError
from backend.app.services.reminder_service import ReminderService, AmbiguousReminderError
from backend.app.services.project_service import ProjectService
from backend.app.tools.personal_tool import parse_when, _utc_to_local, _fmt_datetime_win


def _result(ok, operation, data=None, error=None, verification=None, error_type=None):
    return {"ok": ok, "operation": operation, "data": data, "error": error,
            "error_type": error_type, "verification": verification or {},
            "timestamp": datetime.now(timezone.utc).isoformat()}


def _ambiguous(kind, matches):
    labels = [f"[{x.id}] {getattr(x, 'title', getattr(x, 'message', ''))}" for x in matches]
    return {"title": "Clarification needed", "answer": f"I found multiple {kind}s. Which one did you mean?\n" + "\n".join(labels),
            "result": _result(False, f"resolve_{kind}", error="ambiguous reference", error_type="ambiguous_request", data={"matches": labels})}


def _when_label(iso): return _fmt_datetime_win(_utc_to_local(iso))


def _date_window(q: str):
    now = datetime.now().astimezone(); lower=q.lower()
    if "tomorrow" in lower: start=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0); days=1
    elif "next week" in lower: start=(now+timedelta(days=(7-now.weekday()))).replace(hour=0,minute=0,second=0,microsecond=0); days=7
    elif "weekend" in lower: start=(now+timedelta(days=(5-now.weekday())%7)).replace(hour=0,minute=0,second=0,microsecond=0); days=2
    else:
        names={"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
        hit=next((v for k,v in names.items() if k in lower),None)
        if hit is None: start=now.replace(hour=0,minute=0,second=0,microsecond=0); days=1
        else: start=(now+timedelta(days=(hit-now.weekday())%7)).replace(hour=0,minute=0,second=0,microsecond=0); days=1
    end=start+timedelta(days=days)
    return start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat(), start.date().isoformat(), days


def handle_core_intent(query: str):
    q=query.strip(); lower=q.lower(); tasks=TaskService(); reminders=ReminderService()

    # Reminder create/update/cancel/list.
    if re.match(r"^(?:remind me|set (?:a )?reminder)", lower):
        from backend.app.tools.personal_tool import _split_remind_raw
        message, when_text=_split_remind_raw(q)
        try: trigger, recurrence=parse_when(when_text); saved=reminders.create_reminder(message,trigger,recurrence)
        except Exception as exc: return {"title":"Reminder error","answer":f"I couldn't save that reminder: {exc}","result":_result(False,"create_reminder",error=str(exc),error_type="validation_error")}
        verified=reminders.get_reminder(saved.id)
        if not verified: return {"title":"Reminder error","answer":"I couldn't verify that the reminder was saved.","result":_result(False,"create_reminder",error="verification failed",error_type="database_failure")}
        return {"title":"Reminder saved","answer":f"Done — I'll remind you {_when_label(saved.trigger_at)} to {saved.message}.","result":_result(True,"create_reminder",saved.model_dump(),verification={"persisted":True,"id":saved.id})}

    m=re.match(r"^(?:actually\s+)?make\s+that\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))$",lower)
    if m:
        from backend.app.services.datetime_service import parse_datetime
        from backend.app.tools.time_tool import get_user_timezone
        from zoneinfo import ZoneInfo
        item=reminders.most_recent_active()
        if not item: return {"title":"Not found","answer":"I couldn't find a recent reminder to change.","result":_result(False,"reschedule_reminder",error="not found",error_type="not_found")}
        parsed=parse_datetime(m.group(1)); local=_aware_iso(item.trigger_at).astimezone(ZoneInfo(get_user_timezone()))
        moved=local.replace(hour=int(parsed.resolved_time[:2]),minute=int(parsed.resolved_time[3:5]),second=0,microsecond=0)
        updated=reminders.reschedule(item.id,moved.astimezone(timezone.utc).isoformat())
        return {"title":"Reminder rescheduled","answer":f"Done — I moved '{updated.message}' to {_when_label(updated.trigger_at)}.","result":_result(True,"reschedule_reminder",updated.model_dump(),verification={"persisted":True,"same_id":updated.id==item.id})}

    m=re.match(r"^snooze\s+that(?:\s+reminder)?\s+for\s+(\d+)\s+(minute|hour)s?$",lower)
    if m:
        item=reminders.most_recent_active()
        if not item: return {"title":"Not found","answer":"I couldn't find a recent reminder to snooze.","result":_result(False,"snooze_reminder",error="not found",error_type="not_found")}
        amount=int(m.group(1)); delta=timedelta(minutes=amount) if m.group(2)=="minute" else timedelta(hours=amount)
        updated=reminders.snooze(item.id,(datetime.now(timezone.utc)+delta).isoformat())
        return {"title":"Reminder snoozed","answer":f"Done — snoozed '{updated.message}' until {_when_label(updated.trigger_at)}.","result":_result(True,"snooze_reminder",updated.model_dump(),verification={"persisted":True,"same_id":updated.id==item.id,"status":updated.status})}

    m=re.match(r"^(?:move|reschedule|snooze) (?:my )?(.+?) reminder (?:to|until) (.+)$",lower)
    if m:
        try: item=reminders.resolve(m.group(1))
        except AmbiguousReminderError as exc: return _ambiguous("reminder",exc.matches)
        if not item: return {"title":"Not found","answer":f"I couldn't find a reminder matching '{m.group(1)}'.","result":_result(False,"reschedule_reminder",error="not found",error_type="not_found")}
        try: at,_=parse_when(m.group(2)); updated=reminders.reschedule(item.id,at)
        except Exception as exc: return {"title":"Reminder error","answer":f"I couldn't reschedule that reminder: {exc}","result":_result(False,"reschedule_reminder",error=str(exc),error_type="validation_error")}
        return {"title":"Reminder rescheduled","answer":f"Done — I moved '{updated.message}' to {_when_label(updated.trigger_at)}.","result":_result(True,"reschedule_reminder",updated.model_dump(),verification={"persisted":True,"same_id":updated.id==item.id})}

    m=re.match(r"^(?:cancel|delete|remove) (?:my )?(.+?) reminder$",lower)
    if m:
        try: item=reminders.most_recent_active() if m.group(1)=="that" else reminders.resolve(m.group(1))
        except AmbiguousReminderError as exc: return _ambiguous("reminder",exc.matches)
        if not item: return {"title":"Not found","answer":f"I couldn't find a reminder matching '{m.group(1)}'.","result":_result(False,"cancel_reminder",error="not found",error_type="not_found")}
        updated=reminders.cancel(item.id)
        return {"title":"Reminder cancelled","answer":f"Cancelled — '{item.message}' will not be delivered.","result":_result(bool(updated),"cancel_reminder",updated.model_dump() if updated else None,verification={"status":updated.status if updated else None})}

    if "reminder" in lower and re.search(r"\b(?:what|show|list|have)\b",lower):
        start,end,_,_=_date_window(q); found=[r for r in reminders.list_reminders() if start<=r.trigger_at<end] if any(x in lower for x in ("tomorrow","friday","monday","tuesday","wednesday","thursday","weekend","next week")) else reminders.list_reminders()
        answer="You have no matching reminders." if not found else "Your reminders:\n"+"\n".join(f"- {r.message} — {_when_label(r.trigger_at)}" for r in found)
        return {"title":"Reminders","answer":answer,"result":_result(True,"list_reminders",[r.model_dump() for r in found],verification={"source":"database"})}

    # Task create and mutation.
    m=re.match(r"^(?:add|create) (?:task )?(.+?)(?: to my tasks)?(?: (?:for|due) (tomorrow|today|(?:next )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)))?[.!]?$",q,re.I)
    implicit_timed_event = bool(re.search(r"\b(?:on|for)\s+.+?\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", lower))
    if m and not implicit_timed_event and not re.match(r"^(?:add|create)\s+(?:an?\s+)?(?:new\s+)?(?:event|appointment|meeting|call|project)\b", lower):
        title=m.group(1).strip(); due=None
        if m.group(2): due,_=parse_when(m.group(2))
        try: saved=tasks.create_task(title,due_at=due)
        except Exception as exc: return {"title":"Task error","answer":f"I couldn't save that task: {exc}","result":_result(False,"create_task",error=str(exc),error_type="database_failure")}
        return {"title":"Task saved","answer":f"Done — added '{saved.title}'"+(f" for {_when_label(saved.due_at)}." if saved.due_at else "."),"result":_result(True,"create_task",saved.model_dump(),verification={"persisted":tasks.get_task(saved.id) is not None,"id":saved.id})}

    m=re.match(r"^(?:actually )?(?:move|reschedule) (?:the |my )?(.+?) task (?:to|for) (.+)$",lower)
    if m:
        try: item=tasks.resolve(m.group(1))
        except AmbiguousTaskError as exc: return _ambiguous("task",exc.matches)
        if not item: return {"title":"Not found","answer":f"I couldn't find a task matching '{m.group(1)}'.","result":_result(False,"reschedule_task",error="not found",error_type="not_found")}
        try: due,_=parse_when(m.group(2)); updated=tasks.reschedule_task(item.id,due)
        except Exception as exc: return {"title":"Task error","answer":f"I couldn't reschedule that task: {exc}","result":_result(False,"reschedule_task",error=str(exc),error_type="validation_error")}
        return {"title":"Task rescheduled","answer":f"Done — moved '{updated.title}' to {_when_label(updated.due_at)}.","result":_result(True,"reschedule_task",updated.model_dump(),verification={"same_id":updated.id==item.id,"persisted":True})}

    m=re.match(r"^(?:mark|complete|finish) (?:the |my )?(.+?)(?: task)? (?:as )?(?:done|complete|completed)$",lower)
    if not m: m=re.match(r"^(?:mark|complete) (?:task )?(.+)$",lower)
    if m:
        ref=re.sub(r"\s+task$","",m.group(1)).strip()
        try: item=tasks.resolve(ref)
        except AmbiguousTaskError as exc: return _ambiguous("task",exc.matches)
        if not item: return {"title":"Not found","answer":f"I couldn't find a task matching '{ref}'.","result":_result(False,"complete_task",error="not found",error_type="not_found")}
        tasks.complete_task(item.id); verified=tasks.get_task(item.id)
        return {"title":"Task completed","answer":f"Done — marked '{item.title}' as completed.","result":_result(verified.status=="completed","complete_task",verified.model_dump(),verification={"status":verified.status})}

    # Canonical internal calendar remains usable offline. Google is an optional
    # adapter, not a prerequisite for SILVIA remembering an event.
    event_create = re.match(r"^(?:(?:create|add|schedule|book)\s+|put\s+)(?:an?\s+)?(?:new\s+)?(?:event|appointment|meeting)?\s*(.+)$", q, re.I)
    if event_create:
        from backend.app.services.datetime_service import parse_event_request
        from backend.app.services.calendar_service import CalendarService
        from backend.app.models.personal import CalendarEventCreate
        try:
            title, parsed = parse_event_request(q)
            all_day = parsed.resolved_time is None and ("all-day" in lower or "all day" in lower or "whole day" in lower or any(x in title.lower() for x in ("birthday","anniversary","holiday")))
            if parsed.resolved_time is None and not all_day:
                return {"title":"Time needed","answer":f"What time is {title}?","result":_result(False,"create_event",error="time required",error_type="missing_parameter")}
            start = parsed.resolved_date if all_day else parsed.utc_iso
            saved = CalendarService().create_event(CalendarEventCreate(title=title,start_at=start or "",timezone=parsed.timezone,all_day=all_day))
            event = CalendarService().get_event(saved.id)
            if not event: raise RuntimeError("Event was not persisted")
        except Exception as exc:
            return {"title":"Calendar error","answer":f"I couldn't create that event: {exc}","result":_result(False,"create_event",error=str(exc),error_type="validation_error")}
        label = f"{parsed.resolved_date} (all day)" if all_day else parsed.local_iso
        return {"title":"Event created","answer":f"Done — created '{event.title}' for {label}.","result":_result(True,"create_event",event.model_dump(),verification={"provider":"silvia","retrieved":True,"id":event.id})}

    event_move = re.match(r"^(?:move|reschedule) (?:the )?(.+?)(?: appointment| event| meeting)? to (.+)$", lower)
    if event_move:
        from backend.app.services.calendar_service import CalendarService
        from backend.app.services.datetime_service import parse_datetime
        from backend.app.tools.time_tool import get_user_timezone
        from zoneinfo import ZoneInfo
        try:
            service=CalendarService(); event=service.find_event(event_move.group(1))
            if not event: return {"title":"Not found","answer":f"I couldn't find a calendar event matching '{event_move.group(1)}'.","result":_result(False,"update_event",error="not found",error_type="not_found")}
            parsed=parse_datetime(event_move.group(2))
            if parsed.resolved_time and not re.search(r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}\s+[a-z]+|[a-z]+\s+\d{1,2})\b",event_move.group(2)):
                local=datetime.fromisoformat(event.start_at).astimezone(ZoneInfo(get_user_timezone()))
                moved=local.replace(hour=int(parsed.resolved_time[:2]),minute=int(parsed.resolved_time[3:5]))
                start=moved.astimezone(timezone.utc).isoformat()
            else: start=parsed.utc_iso or parsed.resolved_date
            updated=service.update_event(event.id,start_at=start,all_day=False,timezone=get_user_timezone())
        except Exception as exc: return {"title":"Calendar error","answer":f"I couldn't move that event: {exc}","result":_result(False,"update_event",error=str(exc),error_type="validation_error")}
        return {"title":"Event moved","answer":f"Done — moved '{updated.title}' to {start}.","result":_result(True,"update_event",updated.model_dump(),verification={"provider":"silvia","retrieved":True,"same_id":updated.id==event.id})}

    event_delete = re.match(r"^(?:delete|cancel|remove) (?:the )?(.+?)(?: appointment| event| meeting)$", lower)
    if event_delete:
        from backend.app.services.core_calendar_service import CoreCalendarService, CalendarError, AmbiguousEventError
        try:
            service=CoreCalendarService(); event=service.resolve(event_delete.group(1))
            if not event: return {"title":"Not found","answer":f"I couldn't find a calendar event matching '{event_delete.group(1)}'.","result":_result(False,"delete_event",error="not found",error_type="not_found")}
            service.delete(event["id"])
        except AmbiguousEventError as exc: return {"title":"Clarification needed","answer":"I found multiple matching calendar events. Please specify which one.","result":_result(False,"delete_event",data={"matches":exc.matches},error="ambiguous",error_type="ambiguous_request")}
        except CalendarError as exc: return {"title":"Calendar unavailable","answer":f"I couldn't delete that event: {exc}","result":_result(False,"delete_event",error=str(exc),error_type=exc.error_type)}
        return {"title":"Event deleted","answer":f"Deleted — '{event.get('title','event')}'.","result":_result(True,"delete_event",event,verification={"provider":"google","absent":True})}

    # Grounded agenda combines tasks, reminders and authoritative Google calendar.
    if re.search(r"what (?:do i (?:need to do|have)|have i got)|what'?s (?:happening|on my calendar)",lower):
        start,end,date,days=_date_window(q); due=tasks.list_tasks("active",due_from=start,due_to=end)
        rem=[r for r in reminders.list_reminders() if start<=r.trigger_at<end]
        from backend.app.tools.productivity_tool import list_gcal_events
        cal=list_gcal_events(date=date,days=days); events=cal.get("data",{}).get("events",[]) if cal.get("ok") else []
        lines=[]
        if due: lines.append("Tasks:\n"+"\n".join(f"- {t.title}" for t in due))
        if rem: lines.append("Reminders:\n"+"\n".join(f"- {r.message} — {_when_label(r.trigger_at)}" for r in rem))
        if events: lines.append("Calendar:\n"+"\n".join(f"- {e.get('title','(untitled)')} — {e.get('start','')}" for e in events))
        if not lines: lines.append("I found no tasks, reminders, or calendar events for that period.")
        if not cal.get("ok"): lines.append(f"Calendar unavailable: {cal.get('summary') or cal.get('error')}")
        return {"title":"Agenda","answer":"\n\n".join(lines),"result":_result(True,"get_agenda",{"tasks":[t.model_dump() for t in due],"reminders":[r.model_dump() for r in rem],"events":events},verification={"tasks":"database","reminders":"database","calendar":"google" if cal.get('ok') else "unavailable"})}

    if re.search(r"what should i (?:work on|do)|i have (?:an?|one|\d+) (?:minutes?|hours?).*what", lower):
        minute_m=re.search(r"(\d+)\s*minutes?",lower); hour_m=re.search(r"(?:an?|one|\d+)\s*hours?",lower)
        available=int(minute_m.group(1)) if minute_m else (60 if hour_m else None)
        now=datetime.now(timezone.utc)
        priority={"critical":40,"high":30,"normal":20,"low":10}
        candidates=[]
        for task in tasks.list_tasks("active"):
            if task.status=="blocked": continue
            if available and task.estimated_minutes and task.estimated_minutes>available: continue
            score=priority.get(task.priority,20); reasons=[f"{task.priority} priority"]
            if task.due_at:
                hours=(_aware_iso(task.due_at)-now).total_seconds()/3600
                if hours<0: score+=50; reasons.append("overdue")
                elif hours<=24: score+=35; reasons.append("due within 24 hours")
                elif hours<=72: score+=20; reasons.append("due soon")
            candidates.append((score,task,reasons))
        candidates.sort(key=lambda x:(-x[0],x[1].due_at or "9999"))
        if not candidates:
            answer="I couldn't find an actionable stored task"+(" that fits the available time." if available else ".")
            data=[]
        else:
            data=[{"task":t.model_dump(),"score":s,"reasons":r} for s,t,r in candidates[:3]]
            answer="I recommend:\n"+"\n".join(f"- {x['task']['title']} — {', '.join(x['reasons'])}" for x in data)
            if any(x["task"].get("estimated_minutes") is None for x in data): answer+="\nI don't have duration estimates for every task, so I did not invent them."
        return {"title":"Recommended work","answer":answer,"result":_result(True,"recommend_tasks",data,verification={"source":"tasks","blocked_excluded":True})}

    # Lightweight grounded project lookup.
    m=re.search(r"(?:for|on|blocking) (?:the )?([a-z0-9_-]+) project",lower)
    if m:
        projects=ProjectService().list_projects(); project=next((p for p in projects if p.name.lower()==m.group(1).lower() or p.id.lower()==m.group(1).lower()),None)
        if not project: return {"title":"Project not found","answer":f"I couldn't find a project called {m.group(1)}.","result":_result(False,"get_project_context",error="not found",error_type="not_found")}

    return None


def _aware_iso(value: str) -> datetime:
    dt=datetime.fromisoformat(value)
    return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone(timezone.utc)
