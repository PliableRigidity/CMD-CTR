"""Canonical Google Calendar gateway with typed failures and verification."""
from __future__ import annotations

from datetime import datetime, timezone


class CalendarError(RuntimeError):
    error_type = "external_api_failure"
class CalendarAuthError(CalendarError): error_type = "authentication_failure"
class CalendarExternalError(CalendarError): error_type = "network_failure"
class CalendarUnavailableError(CalendarExternalError): error_type = "unavailable_integration"
class AmbiguousEventError(CalendarError):
    error_type = "ambiguous_request"
    def __init__(self, matches): self.matches=matches; super().__init__("Multiple calendar events match.")


def _provider_error(exc: Exception) -> CalendarError:
    """Translate provider/OAuth internals into stable, user-safe failures."""
    message = str(exc).lower()
    if any(token in message for token in ("invalid_grant", "token has been expired", "token expired", "unauthorized")):
        return CalendarAuthError("Your Google Calendar connection has expired. Please reconnect Google Calendar and try again.")
    if any(token in message for token in ("timed out", "connection", "network", "name resolution")):
        return CalendarUnavailableError("Google Calendar is temporarily unreachable. Please try again shortly.")
    return CalendarExternalError("Google Calendar could not complete that request. Please try again.")


class CoreCalendarService:
    def __init__(self, provider=None): self._provider = provider
    def _get(self):
        if self._provider is None:
            try:
                from backend.app.tools.productivity_tool import _provider
                self._provider = _provider()
            except Exception as exc: raise CalendarUnavailableError(str(exc)) from exc
        if not self._provider.is_authenticated(): raise CalendarAuthError("Google Calendar is not authenticated.")
        return self._provider
    def list_events(self, date="today", days=1):
        try: return self._get().list_events(date=date,days=days)
        except CalendarError: raise
        except Exception as exc: raise _provider_error(exc) from exc
    def resolve(self, query, date="today", days=365):
        events=self.list_events(date,days); q=query.lower().strip()
        exact=[e for e in events if e.get("title","").lower().strip()==q]
        matches=exact or [e for e in events if q in e.get("title","").lower()]
        if len(matches)>1: raise AmbiguousEventError(matches)
        return matches[0] if matches else None
    def create(self, **data):
        p=self._get()
        try: created=p.create_event(**data)
        except Exception as exc: raise _provider_error(exc) from exc
        if not created.get("id"): raise CalendarError("Calendar did not return an event ID.")
        verified=p.get_event(created["id"])
        if verified.get("id") != created["id"]: raise CalendarError("Created event could not be verified.")
        return verified
    def update(self,event_id,start_iso,end_iso=None):
        p=self._get()
        try: updated=p.update_event(event_id,start_iso,end_iso); verified=p.get_event(event_id)
        except Exception as exc: raise _provider_error(exc) from exc
        if verified.get("start") != updated.get("start"): raise CalendarError("Updated event could not be verified.")
        return verified
    def delete(self,event_id):
        p=self._get()
        try: deleted=p.delete_event(event_id)
        except Exception as exc: raise _provider_error(exc) from exc
        if not deleted: raise CalendarError("Calendar rejected the deletion.")
        try: p.get_event(event_id)
        except Exception: return True
        raise CalendarError("Deleted event still exists after verification.")
