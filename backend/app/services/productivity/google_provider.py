"""Google productivity provider — Gmail, Google Calendar, Google Contacts.

Requires: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

Set in .env:
    GOOGLE_CLIENT_ID=...
    GOOGLE_CLIENT_SECRET=...
    GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/productivity/auth/callback
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Optional

from backend.app.services.productivity.base import ProductivityProvider
from backend.app.services.productivity.auth_service import AuthService

logger = logging.getLogger(__name__)

PROVIDER_ID = "google"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://mail.google.com/",  # TODO: remove if gmail.readonly+send proves sufficient
]


def _require_deps() -> None:
    try:
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Google API packages not installed. Run: "
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc


def _client_config(client_id: str, client_secret: str, redirect_uri: str = "") -> dict:
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri] if redirect_uri else [],
        }
    }


def _generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _parse_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(part: dict) -> str:
    data = (part.get("body") or {}).get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_text(payload: dict) -> str:
    """Recursively find the first text/plain part."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        return _decode_body(payload)
    for part in payload.get("parts", []):
        text = _extract_text(part)
        if text:
            return text
    return _decode_body(payload)


def _fmt_gcal_event(ev: dict) -> dict:
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "id": ev.get("id", ""),
        "title": ev.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "location": ev.get("location", ""),
        "description": ev.get("description", ""),
        "link": ev.get("htmlLink", ""),
    }


class GoogleProvider(ProductivityProvider):
    """Concrete Google provider — Gmail, Calendar, Contacts."""

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        client_secrets_file: str = "",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._client_secrets_file = client_secrets_file
        self._auth = AuthService()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make_flow(self):
        _require_deps()
        from google_auth_oauthlib.flow import Flow
        if self._client_secrets_file:
            flow = Flow.from_client_secrets_file(
                self._client_secrets_file,
                scopes=SCOPES,
                redirect_uri=self._redirect_uri,
            )
        else:
            flow = Flow.from_client_config(
                _client_config(self._client_id, self._client_secret, self._redirect_uri),
                scopes=SCOPES,
                redirect_uri=self._redirect_uri,
            )
        return flow

    def _credentials(self):
        _require_deps()
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        data = self._auth.load(PROVIDER_ID)
        if not data:
            raise RuntimeError(
                "Not connected to Google. Say 'connect to Google' to authorize."
            )

        # Detect tokens issued under a different scope set and force re-auth
        stored_scopes = set(data.get("scopes") or [])
        if stored_scopes and stored_scopes != set(SCOPES):
            logger.warning(
                "[Google OAuth] stored scopes differ from current SCOPES — clearing stale token. "
                "stored=%s  current=%s", sorted(stored_scopes), sorted(SCOPES)
            )
            self._auth.clear(PROVIDER_ID)
            self._auth.clear(f"{PROVIDER_ID}_pkce")
            raise RuntimeError(
                "Google OAuth scopes have changed since last login. "
                "Please reconnect: say 'connect to Google' or click Connect Google."
            )

        # Use the scopes the token was actually issued for when refreshing
        token_scopes = data.get("scopes") or SCOPES

        creds = Credentials(
            token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=token_scopes,
        )
        if creds.expired and creds.refresh_token:
            logger.info("[Google OAuth] refreshing token — scopes=%s", token_scopes)
            creds.refresh(Request())
            self._auth.store(PROVIDER_ID, {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "expiry": creds.expiry.isoformat() if creds.expiry else None,
                "scopes": list(creds.scopes or token_scopes),
            })
        return creds

    def _gmail(self):
        from googleapiclient.discovery import build
        return build("gmail", "v1", credentials=self._credentials(), cache_discovery=False)

    def _calendar(self):
        from googleapiclient.discovery import build
        return build("calendar", "v3", credentials=self._credentials(), cache_discovery=False)

    # ── Auth ─────────────────────────────────────────────────────────────────

    def get_auth_url(self) -> str:
        _require_deps()
        if not self._client_id or not self._client_secret:
            raise RuntimeError(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set in .env. "
                "Create a Google Cloud project, enable Gmail + Calendar + People APIs, "
                "and set these credentials."
            )
        code_verifier, code_challenge = _generate_pkce()
        flow = self._make_flow()
        url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        # Store state and verifier together — retrieved on callback
        self._auth.store(f"{PROVIDER_ID}_pkce", {"state": state, "code_verifier": code_verifier})
        logger.info("[Google OAuth] auth session created — state=%s… verifier stored, scopes=%s", state[:8], SCOPES)
        return url

    def exchange_code(self, code: str, state: str = "") -> dict:
        # Retrieve the stored PKCE verifier
        pkce = self._auth.load(f"{PROVIDER_ID}_pkce") or {}
        code_verifier = pkce.get("code_verifier")
        stored_state = pkce.get("state", "")
        logger.info(
            "[Google OAuth] callback received — state=%s… verifier=%s",
            state[:8] if state else "?",
            "found" if code_verifier else "MISSING",
        )

        # Validate state to prevent CSRF
        if state and stored_state and state != stored_state:
            logger.warning("[Google OAuth] state mismatch — stored=%s… got=%s…", stored_state[:8], state[:8])
            raise RuntimeError("OAuth state mismatch — possible CSRF. Try connecting again.")

        flow = self._make_flow()
        try:
            if code_verifier:
                flow.fetch_token(code=code, code_verifier=code_verifier)
            else:
                logger.warning("[Google OAuth] no code_verifier found — attempting exchange without PKCE")
                flow.fetch_token(code=code)
            logger.info("[Google OAuth] token exchange success")
        except Exception as exc:
            logger.error("[Google OAuth] token exchange failed: %s", exc)
            raise

        creds = flow.credentials
        granted = sorted(creds.scopes or SCOPES)
        logger.info("[Google OAuth] token exchange success — granted scopes=%s", granted)
        data = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
            "scopes": granted,
        }
        self._auth.store(PROVIDER_ID, data)
        self._auth.clear(f"{PROVIDER_ID}_pkce")
        return data

    def is_authenticated(self) -> bool:
        return self._auth.load(PROVIDER_ID) is not None

    def whoami(self) -> str:
        try:
            gmail = self._gmail()
            profile = gmail.users().getProfile(userId="me").execute()
            return profile.get("emailAddress", "")
        except Exception:
            data = self._auth.load(PROVIDER_ID) or {}
            return data.get("email", "connected")

    def revoke(self) -> None:
        import requests as _req
        data = self._auth.load(PROVIDER_ID) or {}
        token = data.get("access_token") or data.get("refresh_token")
        if token:
            try:
                _req.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    timeout=5,
                )
            except Exception:
                pass
        self._auth.clear(PROVIDER_ID)
        self._auth.clear(f"{PROVIDER_ID}_state")

    # ── Gmail ────────────────────────────────────────────────────────────────

    def list_emails(
        self,
        folder: str = "inbox",
        search: str = "",
        limit: int = 10,
    ) -> list[dict]:
        gmail = self._gmail()
        query_parts = []
        if folder.lower() == "inbox":
            query_parts.append("in:inbox")
        elif folder.lower() == "unread":
            query_parts.append("is:unread in:inbox")
        if search:
            query_parts.append(search)
        q = " ".join(query_parts) if query_parts else ""

        result = gmail.users().messages().list(
            userId="me", q=q, maxResults=min(limit, 25)
        ).execute()

        messages = result.get("messages", [])
        emails = []
        for m in messages:
            try:
                msg = gmail.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]
                ).execute()
                headers = msg.get("payload", {}).get("headers", [])
                unread = "UNREAD" in msg.get("labelIds", [])
                emails.append({
                    "id": msg["id"],
                    "subject": _parse_header(headers, "Subject") or "(no subject)",
                    "sender": _parse_header(headers, "From"),
                    "date": _parse_header(headers, "Date"),
                    "snippet": msg.get("snippet", ""),
                    "unread": unread,
                })
            except Exception:
                continue
        return emails

    def get_email(self, message_id: str) -> dict:
        gmail = self._gmail()
        msg = gmail.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        body = _extract_text(msg.get("payload", {}))
        return {
            "id": msg["id"],
            "subject": _parse_header(headers, "Subject") or "(no subject)",
            "sender": _parse_header(headers, "From"),
            "date": _parse_header(headers, "Date"),
            "body_text": body[:4000],
            "snippet": msg.get("snippet", ""),
        }

    def draft_email(self, to: str, subject: str, body: str) -> dict:
        gmail = self._gmail()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = gmail.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
        return {
            "draft_id": draft.get("id"),
            "to": to,
            "subject": subject,
            "preview": body[:200],
        }

    def send_email(self, to: str, subject: str, body: str) -> dict:
        gmail = self._gmail()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = gmail.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"id": sent.get("id"), "to": to, "subject": subject}

    # ── Calendar ─────────────────────────────────────────────────────────────

    def list_events(self, date: str | None = None, days: int = 1) -> list[dict]:
        cal = self._calendar()
        now = datetime.now(timezone.utc)

        if date in (None, "today", ""):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            try:
                start = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        end = start + timedelta(days=max(1, days))

        result = cal.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()
        return [_fmt_gcal_event(ev) for ev in result.get("items", [])]

    def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str | None = None,
        description: str = "",
        location: str = "",
    ) -> dict:
        cal = self._calendar()
        start_dt = datetime.fromisoformat(start_iso)
        if end_iso:
            end_dt = datetime.fromisoformat(end_iso)
        else:
            end_dt = start_dt + timedelta(hours=1)

        body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        }
        ev = cal.events().insert(calendarId="primary", body=body).execute()
        return _fmt_gcal_event(ev)

    def delete_event(self, event_id: str) -> bool:
        cal = self._calendar()
        try:
            cal.events().delete(calendarId="primary", eventId=event_id).execute()
            return True
        except Exception:
            return False

    def get_event(self, event_id: str) -> dict:
        return _fmt_gcal_event(
            self._calendar().events().get(calendarId="primary", eventId=event_id).execute()
        )

    def update_event(self, event_id: str, start_iso: str, end_iso: str | None = None) -> dict:
        cal = self._calendar()
        current = cal.events().get(calendarId="primary", eventId=event_id).execute()
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso) if end_iso else start_dt + timedelta(hours=1)
        current["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "UTC"}
        current["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "UTC"}
        updated = cal.events().update(calendarId="primary", eventId=event_id, body=current).execute()
        return _fmt_gcal_event(updated)
