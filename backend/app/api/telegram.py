"""Telegram bridge status endpoint."""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["telegram"])


@router.get("/telegram/status")
async def telegram_status() -> dict:
    from backend.config import (
        TELEGRAM_ENABLED,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_ALLOWED_USER_IDS,
    )
    from backend.app.services.telegram_bridge import get_bridge, _read_lock

    bridge = get_bridge()
    lock = _read_lock()

    return {
        "enabled": TELEGRAM_ENABLED,
        "configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS),
        "running": bridge.running if bridge is not None else False,
        "pid": bridge.pid if bridge is not None and bridge.running else (lock.get("pid") if lock else None),
        "started_at": bridge.started_at if bridge is not None and bridge.running else (lock.get("started_at") if lock else None),
        "allowed_users_count": len(TELEGRAM_ALLOWED_USER_IDS),
        "lock_held": lock is not None,
        "lock_pid": lock.get("pid") if lock else None,
    }
