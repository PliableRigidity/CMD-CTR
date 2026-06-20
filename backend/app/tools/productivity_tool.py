"""Productivity tools — Gmail, Google Calendar.

These functions are called by conversation_service when the planner routes
to email/calendar tools. All functions return the standard result dict:
    {ok, tool, summary, data, error}
"""
from __future__ import annotations

from typing import Optional


def _make_result(ok: bool, tool: str, summary: str, data, error: Optional[str]) -> dict:
    return {"ok": ok, "tool": tool, "node": None, "summary": summary, "data": data, "error": error}


def _provider():
    """Return a GoogleProvider instance or raise with a helpful message."""
    from backend.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI
    from backend.app.services.productivity.google_provider import GoogleProvider
    return GoogleProvider(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_productivity_auth_status() -> dict:
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(True, "auth_status", "Not connected", {"connected": False, "email": None}, None)
        email = p.whoami()
        return _make_result(True, "auth_status", f"Connected as {email}", {"connected": True, "email": email}, None)
    except RuntimeError as e:
        return _make_result(True, "auth_status", "Not connected", {"connected": False, "email": None, "reason": str(e)}, None)
    except Exception as e:
        return _make_result(False, "auth_status", str(e), None, str(e))


def get_google_auth_url() -> dict:
    try:
        p = _provider()
        url = p.get_auth_url()
        return _make_result(True, "google_auth_url", "Authorization URL generated", {"auth_url": url}, None)
    except Exception as e:
        return _make_result(False, "google_auth_url", str(e), None, str(e))


# ── Gmail tools ──────────────────────────────────────────────────────────────

def list_emails(folder: str = "inbox", search: str = "", limit: int = 10) -> dict:
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "list_emails", "Not connected to Google. Say 'connect to Google' to authorize.", None, "unauthenticated")
        emails = p.list_emails(folder=folder, search=search, limit=limit)
        unread_count = sum(1 for e in emails if e.get("unread"))
        summary = f"{len(emails)} email{'s' if len(emails) != 1 else ''}"
        if unread_count:
            summary += f" ({unread_count} unread)"
        return _make_result(True, "list_emails", summary, {"emails": emails, "count": len(emails), "folder": folder}, None)
    except RuntimeError as e:
        return _make_result(False, "list_emails", str(e), None, str(e))
    except Exception as e:
        return _make_result(False, "list_emails", f"Gmail error: {e}", None, str(e))


def search_emails(query: str, limit: int = 10) -> dict:
    return list_emails(folder="", search=query, limit=limit)


def get_email(message_id: str) -> dict:
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "get_email", "Not connected to Google.", None, "unauthenticated")
        email = p.get_email(message_id)
        return _make_result(True, "get_email", f"Email: {email['subject']}", {"email": email}, None)
    except Exception as e:
        return _make_result(False, "get_email", str(e), None, str(e))


def draft_email(to: str, subject: str, body: str) -> dict:
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "draft_email", "Not connected to Google. Say 'connect to Google' to authorize.", None, "unauthenticated")
        if not to.strip():
            return _make_result(False, "draft_email", "No recipient specified.", None, "missing_to")
        draft = p.draft_email(to=to, subject=subject, body=body)
        return _make_result(
            True, "draft_email",
            f"Draft created — to: {to}, subject: {subject or '(no subject)'}",
            {"draft": draft},
            None,
        )
    except Exception as e:
        return _make_result(False, "draft_email", str(e), None, str(e))


def send_email_confirmed(to: str, subject: str, body: str) -> dict:
    """Send an email. Call ONLY after user has confirmed via conversation."""
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "send_email", "Not connected to Google.", None, "unauthenticated")
        sent = p.send_email(to=to, subject=subject, body=body)
        return _make_result(
            True, "send_email",
            f"Email sent to {to}",
            {"sent": sent},
            None,
        )
    except Exception as e:
        return _make_result(False, "send_email", f"Send failed: {e}", None, str(e))


# ── Calendar tools ────────────────────────────────────────────────────────────

def list_gcal_events(date: str = "today", days: int = 1) -> dict:
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "list_gcal_events", "Not connected to Google. Say 'connect to Google' to authorize.", None, "unauthenticated")
        events = p.list_events(date=date, days=days)
        period = f"today" if days == 1 else f"next {days} days"
        summary = f"{len(events)} event{'s' if len(events) != 1 else ''} {period}"
        return _make_result(True, "list_gcal_events", summary, {"events": events, "count": len(events), "period": period}, None)
    except RuntimeError as e:
        return _make_result(False, "list_gcal_events", str(e), None, str(e))
    except Exception as e:
        return _make_result(False, "list_gcal_events", f"Calendar error: {e}", None, str(e))


def create_gcal_event(title: str, start_iso: str, end_iso: Optional[str] = None, description: str = "", location: str = "") -> dict:
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "create_gcal_event", "Not connected to Google. Say 'connect to Google' to authorize.", None, "unauthenticated")
        ev = p.create_event(title=title, start_iso=start_iso, end_iso=end_iso, description=description, location=location)
        return _make_result(
            True, "create_gcal_event",
            f"Event created: '{title}' at {ev.get('start', '')}",
            {"event": ev},
            None,
        )
    except Exception as e:
        return _make_result(False, "create_gcal_event", str(e), None, str(e))


def delete_gcal_event_confirmed(event_id: str, title: str = "") -> dict:
    """Delete a calendar event. Call ONLY after user has confirmed."""
    try:
        p = _provider()
        if not p.is_authenticated():
            return _make_result(False, "delete_gcal_event", "Not connected to Google.", None, "unauthenticated")
        ok = p.delete_event(event_id)
        label = f"'{title}'" if title else event_id
        return _make_result(ok, "delete_gcal_event",
                            f"Event {label} deleted" if ok else f"Could not delete event {label}",
                            {"event_id": event_id, "title": title}, None if ok else "delete_failed")
    except Exception as e:
        return _make_result(False, "delete_gcal_event", str(e), None, str(e))


