"""KOSINE write audit log — Phase 19.

Every SILVIA-originated KOSINE write flows through :func:`audited_write`, which:

1. dispatches the tool via the shared KOSClient (``client.call`` → full envelope),
2. appends an immutable JSONL record capturing the tool, params, actor, result
   status, and the objects/events the write touched, and
3. returns the envelope's ``data`` (or raises on failure).

Because KOSINE records a per-object event for every change, and this log records
the SILVIA-side intent + the exact objects_changed / events_created ids, writes
are both auditable (who/what/when) and reversible (the touched ids are known).

Destructive KOSINE tools stay disabled at the transport layer, so this log only
ever contains additive/updating operations.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config

logger = logging.getLogger("silvia.memory.kosine_audit")

_AUDIT_DIR = config.BASE_DIR.parent / "data"
_AUDIT_PATH = _AUDIT_DIR / "kosine_audit.jsonl"
_write_lock = threading.Lock()


class KosineWriteError(RuntimeError):
    """Raised when an audited KOSINE write does not complete successfully."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(record: dict) -> None:
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        with _write_lock:
            with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:  # auditing must never crash the write path silently…
        logger.error("Failed to append KOSINE audit record: %s", e)


def audited_write(
    tool_name: str,
    params: dict,
    actor: str = "silvia",
    reason: str = "",
) -> Any:
    """Dispatch a KOSINE write tool and record it to the audit log.

    :param tool_name: KOSINE tool name (e.g. 'create_memory', 'update_memory',
                      'create_relationship', 'add_event').
    :param params: tool params (may include the reserved 'from' key).
    :param actor: who initiated the write (e.g. 'silvia', 'maintenance', 'user').
    :param reason: optional human-readable justification (for suggestions/loops).
    :returns: the envelope's ``data``.
    :raises KosineWriteError: if writes are disabled or the tool fails.
    """
    if not config.KOSINE_ALLOW_WRITES:
        raise KosineWriteError("KOSINE writes are disabled (set KOSINE_ALLOW_WRITES=true)")

    from backend.app.memory.kosine_client import get_client
    client = get_client()

    started = _now_iso()
    env: dict = {}
    error: Optional[str] = None
    try:
        env = client.call(tool_name, **params) or {}
    except Exception as e:
        error = str(e)

    status = (env.get("status") if isinstance(env, dict) else None) or ("error" if error else "unknown")
    record = {
        "ts": started,
        "completed": _now_iso(),
        "actor": actor,
        "reason": reason,
        "tool": tool_name,
        "params": params,
        "status": status,
        "objects_changed": env.get("objects_changed", []) if isinstance(env, dict) else [],
        "events_created": env.get("events_created", []) if isinstance(env, dict) else [],
        "confirmation_required": env.get("confirmation_required") if isinstance(env, dict) else None,
        "error": error or (env.get("error") if isinstance(env, dict) else None),
    }
    _append(record)

    if error:
        raise KosineWriteError(f"KOSINE '{tool_name}' failed: {error}")
    if status != "ok":
        raise KosineWriteError(
            f"KOSINE '{tool_name}' returned status={status}: {record['error']}"
        )
    return env.get("data")


def read_audit(limit: int = 50) -> list[dict]:
    """Return the most recent audit records (newest first)."""
    if not _AUDIT_PATH.exists():
        return []
    try:
        lines = _AUDIT_PATH.read_text(encoding="utf-8").splitlines()
        records = [json.loads(ln) for ln in lines if ln.strip()]
        return list(reversed(records))[:limit]
    except Exception as e:
        logger.error("Failed to read KOSINE audit log: %s", e)
        return []


def audit_path() -> Path:
    return _AUDIT_PATH
