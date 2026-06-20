"""External notification service — webhook and email alerts.

Fires when Watch Officer raises alerts matching NOTIFICATION_MIN_SEVERITY.
Debounces per rule_key (30 min) so repeated alerts don't flood channels.
"""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import httpx

from backend.config import (
    NOTIFICATION_EMAIL_HOST,
    NOTIFICATION_EMAIL_PASS,
    NOTIFICATION_EMAIL_PORT,
    NOTIFICATION_EMAIL_TO,
    NOTIFICATION_EMAIL_USER,
    NOTIFICATION_MIN_SEVERITY,
    NOTIFICATION_WEBHOOK_FORMAT,
    NOTIFICATION_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)

_DEBOUNCE_MINUTES = 30
_last_notified: dict[str, datetime] = {}

_SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}
_DISCORD_COLORS = {"info": 3447003, "warning": 16776960, "critical": 15158332}


def _severity_meets_threshold(severity: str) -> bool:
    min_level = _SEVERITY_ORDER.get(NOTIFICATION_MIN_SEVERITY, 2)
    return _SEVERITY_ORDER.get(severity, 0) >= min_level


def _debounced(rule_key: str) -> bool:
    """Return True if we should skip this notification (debounced)."""
    last = _last_notified.get(rule_key)
    if last and datetime.now(timezone.utc) - last < timedelta(minutes=_DEBOUNCE_MINUTES):
        return True
    _last_notified[rule_key] = datetime.now(timezone.utc)
    return False


async def send_alert(alert) -> None:
    """Send an alert via all configured channels."""
    severity = getattr(alert, "severity", "info")
    rule_key = getattr(alert, "rule_key", "unknown")

    if not _severity_meets_threshold(severity):
        return

    if _debounced(rule_key):
        logger.debug("Notification debounced for rule_key=%s", rule_key)
        return

    message = getattr(alert, "message", str(alert))
    category = getattr(alert, "category", "infra")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if NOTIFICATION_WEBHOOK_URL:
        await _send_webhook(message, severity, category, ts)

    if NOTIFICATION_EMAIL_HOST and NOTIFICATION_EMAIL_TO:
        _send_email(message, severity, category, ts)


async def _send_webhook(message: str, severity: str, category: str, ts: str) -> None:
    fmt = NOTIFICATION_WEBHOOK_FORMAT.lower()
    try:
        if fmt == "discord":
            payload = {
                "embeds": [{
                    "title": f"SILVIA Watch Officer — {severity.upper()}",
                    "description": message,
                    "color": _DISCORD_COLORS.get(severity, 3447003),
                    "footer": {"text": f"{category} · {ts}"},
                }]
            }
        elif fmt == "slack":
            color = {"info": "good", "warning": "warning", "critical": "danger"}.get(severity, "good")
            payload = {
                "attachments": [{
                    "color": color,
                    "title": f"SILVIA Watch Officer — {severity.upper()}",
                    "text": message,
                    "footer": f"{category} · {ts}",
                }]
            }
        else:
            payload = {
                "severity": severity,
                "message": message,
                "category": category,
                "timestamp": ts,
            }

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                NOTIFICATION_WEBHOOK_URL,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        logger.info("Webhook notification sent (%s): %s", severity, message[:80])
    except Exception as exc:
        logger.warning("Webhook notification failed: %s", exc)


def _send_email(message: str, severity: str, category: str, ts: str) -> None:
    try:
        subject = f"[SILVIA] {severity.upper()}: {message[:60]}"
        body = f"Watch Officer Alert\n\nSeverity: {severity.upper()}\nCategory: {category}\nTime: {ts}\n\nMessage:\n{message}"
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = NOTIFICATION_EMAIL_USER or "silvia@local"
        msg["To"] = NOTIFICATION_EMAIL_TO

        context = ssl.create_default_context()
        with smtplib.SMTP(NOTIFICATION_EMAIL_HOST, NOTIFICATION_EMAIL_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            if NOTIFICATION_EMAIL_USER and NOTIFICATION_EMAIL_PASS:
                server.login(NOTIFICATION_EMAIL_USER, NOTIFICATION_EMAIL_PASS)
            server.sendmail(msg["From"], NOTIFICATION_EMAIL_TO.split(","), msg.as_string())
        logger.info("Email notification sent (%s): %s", severity, message[:80])
    except Exception as exc:
        logger.warning("Email notification failed: %s", exc)
