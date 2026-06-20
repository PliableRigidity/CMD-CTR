"""Productivity REST API — auth, Gmail, Google Calendar (Phase 12G)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/productivity", tags=["productivity"])
logger = logging.getLogger(__name__)

# Single source of truth — defined in google_provider, imported here for status endpoint
from backend.app.services.productivity.google_provider import SCOPES as GOOGLE_SCOPES


# ── Config validation ─────────────────────────────────────────────────────────

def _config_status() -> dict:
    """Return config validity without raising — safe to call anytime."""
    try:
        from backend.config import (
            GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
            GOOGLE_OAUTH_REDIRECT_URI, GOOGLE_CLIENT_SECRETS_FILE,
        )
    except Exception as exc:
        return {
            "configured": False,
            "missing": [f"config import failed: {exc}"],
            "client_id_present": False,
            "client_secret_present": False,
            "redirect_uri": "",
            "secrets_file": "",
        }

    missing = []
    secrets_file = GOOGLE_CLIENT_SECRETS_FILE or ""

    if secrets_file:
        import os
        if not os.path.isfile(secrets_file):
            missing.append(f"GOOGLE_CLIENT_SECRETS_FILE file not found: {secrets_file}")
    else:
        if not GOOGLE_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID")
        if not GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_SECRET")

    return {
        "configured": len(missing) == 0,
        "missing": missing,
        "client_id_present": bool(GOOGLE_CLIENT_ID),
        "client_secret_present": bool(GOOGLE_CLIENT_SECRET),
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "secrets_file": secrets_file,
    }


def _provider():
    """Return a GoogleProvider or raise a clean HTTPException."""
    cfg = _config_status()
    if not cfg["configured"]:
        logger.warning("[Google OAuth] provider requested but config incomplete: %s", cfg["missing"])
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "error": "Google OAuth is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env",
                "missing": cfg["missing"],
                "client_id_present": cfg["client_id_present"],
                "client_secret_present": cfg["client_secret_present"],
                "redirect_uri": cfg["redirect_uri"],
            },
        )
    try:
        from backend.config import (
            GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
            GOOGLE_OAUTH_REDIRECT_URI, GOOGLE_CLIENT_SECRETS_FILE,
        )
        from backend.app.services.productivity.google_provider import GoogleProvider
        return GoogleProvider(
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            redirect_uri=GOOGLE_OAUTH_REDIRECT_URI,
            client_secrets_file=GOOGLE_CLIENT_SECRETS_FILE or "",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[Google OAuth] provider init failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "error": f"Google provider init failed: {exc}"},
        )


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/google/status")
def google_status():
    """Config + auth status — never crashes."""
    cfg = _config_status()
    token_exists = False
    authenticated = False
    email = None

    if cfg["configured"]:
        try:
            p = _provider()
            token_exists = p.is_authenticated()
            authenticated = token_exists
            if authenticated:
                try:
                    email = p.whoami()
                except Exception:
                    pass
        except HTTPException:
            pass
        except Exception:
            pass

    return {
        "configured": cfg["configured"],
        "missing": cfg["missing"],
        "client_id_present": cfg["client_id_present"],
        "client_secret_present": cfg["client_secret_present"],
        "redirect_uri": cfg["redirect_uri"],
        "token_exists": token_exists,
        "authenticated": authenticated,
        "email": email,
        "scopes": GOOGLE_SCOPES,
        "contacts_enabled": False,
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.get("/auth/status")
def auth_status():
    cfg = _config_status()
    if not cfg["configured"]:
        return {
            "connected": False,
            "provider": "google",
            "email": None,
            "configured": False,
            "missing": cfg["missing"],
        }
    try:
        p = _provider()
        if not p.is_authenticated():
            return {"connected": False, "provider": "google", "email": None, "configured": True}
        try:
            email = p.whoami()
        except Exception:
            email = None
        return {"connected": True, "provider": "google", "email": email, "configured": True}
    except HTTPException as exc:
        return {"connected": False, "provider": "google", "email": None,
                "configured": False, "error": exc.detail}
    except Exception as exc:
        logger.exception("[Google OAuth] auth_status error")
        return {"connected": False, "provider": "google", "email": None, "error": str(exc)}


@router.get("/auth/google")
def google_auth_url():
    """Return OAuth2 authorization URL. Never crashes — returns JSON error on failure."""
    try:
        p = _provider()
        url = p.get_auth_url()
        logger.info("[Google OAuth] auth URL generated successfully")
        return {"auth_url": url}
    except HTTPException as exc:
        # Re-raise clean HTTP errors from _provider() as-is
        raise
    except Exception as exc:
        logger.exception("[Google OAuth] get_auth_url failed")
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "error": f"Failed to generate auth URL: {exc}"},
        )


@router.get("/auth/callback")
async def google_auth_callback(code: str = Query(...), state: str = Query(default="")):
    """OAuth2 callback. Google redirects here after the user authorizes."""
    logger.info("[Google OAuth] callback received — code present=%s state=%s…", bool(code), state[:8] if state else "?")
    try:
        p = _provider()
        p.exchange_code(code, state=state)
        return HTMLResponse(content="""
<!DOCTYPE html><html><head><title>SILVIA — Connected</title>
<style>body{background:#0a0b0d;color:#d4a855;font-family:monospace;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;}
h2{font-size:1.2rem;letter-spacing:.1em;}p{opacity:.6;font-size:.85rem;}</style></head>
<body><div><h2>✓ Google account connected</h2>
<p>You can close this tab and return to SILVIA.</p></div></body></html>
""")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        logger.error("[Google OAuth] callback HTTP error: %s", detail)
        return HTMLResponse(
            content=_err_page(detail),
            status_code=exc.status_code,
        )
    except Exception as exc:
        logger.exception("[Google OAuth] callback unexpected error")
        return HTMLResponse(content=_err_page(str(exc)), status_code=500)


def _err_page(msg: str) -> str:
    safe = msg.replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html><html><head><title>SILVIA — Auth Error</title>
<style>body{{background:#0a0b0d;color:#c0392b;font-family:monospace;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;}}
p{{opacity:.7;font-size:.85rem;max-width:480px;}}</style></head>
<body><div><h2>Auth failed</h2><p>{safe}</p>
<p style="margin-top:16px;opacity:.4">Close this tab and try connecting again from SILVIA.</p>
</div></body></html>"""


@router.delete("/auth/google", status_code=204)
def google_disconnect():
    try:
        p = _provider()
        p.revoke()
    except HTTPException:
        pass  # Already disconnected / not configured — treat as success
    except Exception as exc:
        logger.warning("[Google OAuth] disconnect error (non-fatal): %s", exc)


# ── Gmail ─────────────────────────────────────────────────────────────────────

@router.get("/gmail/inbox")
def list_inbox(search: str = "", limit: int = Query(default=10, le=25)):
    from backend.app.tools.productivity_tool import list_emails
    return list_emails(folder="inbox", search=search, limit=limit)


@router.get("/gmail/search")
def search_gmail(q: str = Query(...), limit: int = Query(default=10, le=25)):
    from backend.app.tools.productivity_tool import search_emails
    return search_emails(query=q, limit=limit)


@router.get("/gmail/message/{message_id}")
def get_message(message_id: str):
    from backend.app.tools.productivity_tool import get_email
    result = get_email(message_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


class DraftRequest(BaseModel):
    to: str
    subject: str = ""
    body: str = ""


@router.post("/gmail/draft", status_code=201)
def create_draft(req: DraftRequest):
    from backend.app.tools.productivity_tool import draft_email
    result = draft_email(to=req.to, subject=req.subject, body=req.body)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/gmail/send")
def send_email_endpoint(req: DraftRequest):
    """Send email. Only use from UI after explicit user confirmation."""
    from backend.app.tools.productivity_tool import send_email_confirmed
    result = send_email_confirmed(to=req.to, subject=req.subject, body=req.body)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result.get("error"))
    return result


# ── Calendar ─────────────────────────────────────────────────────────────────

@router.get("/calendar/today")
def calendar_today():
    from backend.app.tools.productivity_tool import list_gcal_events
    return list_gcal_events(date="today", days=1)


@router.get("/calendar/events")
def calendar_events(days: int = Query(default=7, le=30)):
    from backend.app.tools.productivity_tool import list_gcal_events
    return list_gcal_events(date="today", days=days)


class CreateEventRequest(BaseModel):
    title: str
    start_iso: str
    end_iso: str = ""
    description: str = ""
    location: str = ""


@router.post("/calendar/events", status_code=201)
def create_event(req: CreateEventRequest):
    from backend.app.tools.productivity_tool import create_gcal_event
    result = create_gcal_event(
        title=req.title,
        start_iso=req.start_iso,
        end_iso=req.end_iso or None,
        description=req.description,
        location=req.location,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/calendar/events/{event_id}", status_code=204)
def delete_event(event_id: str):
    from backend.app.tools.productivity_tool import delete_gcal_event_confirmed
    result = delete_gcal_event_confirmed(event_id=event_id)
    if not result["ok"]:
        raise HTTPException(status_code=404, detail=result.get("error"))
