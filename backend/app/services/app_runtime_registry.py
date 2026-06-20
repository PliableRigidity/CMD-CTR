"""In-memory runtime registry: tracks apps launched by SILVIA this session.

Separate from the app_registry (what *can* be launched).
This tracks what *is currently running* — PIDs, windows, launch timestamp.
Resets on backend restart; entries are verified live before use.
"""
from __future__ import annotations

import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

_lock = Lock()
_registry: dict[str, dict] = {}  # normalized_name → runtime entry


def _key(name: str) -> str:
    return name.lower().strip()


def register(
    app_name: str,
    command: str,
    pids: list[int],
    windows: list[dict],
    launch_source: str = "",
) -> None:
    entry = {
        "app_name": app_name,
        "command": command,
        "launched_at": time.time(),
        "launched_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pids": list(pids),
        "windows": list(windows),
        "launch_source": launch_source,
    }
    with _lock:
        _registry[_key(app_name)] = entry
    logger.info(
        "APP_LAUNCH Application=%r PID=%r Window=%r State=Running",
        app_name,
        pids,
        [w.get("title", "") for w in windows],
    )


def get(app_name: str) -> dict | None:
    with _lock:
        return _registry.get(_key(app_name))


def get_all() -> list[dict]:
    with _lock:
        return list(_registry.values())


def unregister(app_name: str) -> None:
    with _lock:
        removed = _registry.pop(_key(app_name), None)
    if removed:
        logger.info("APP_CLOSE Application=%r State=Closed", app_name)


def update_pids(app_name: str, pids: list[int]) -> None:
    with _lock:
        entry = _registry.get(_key(app_name))
        if entry:
            entry["pids"] = list(pids)


def purge_dead() -> list[str]:
    """Remove entries where ALL tracked PIDs have exited. Returns removed app names."""
    try:
        import psutil
    except ImportError:
        return []
    removed = []
    with _lock:
        for key, entry in list(_registry.items()):
            if entry["pids"] and not any(psutil.pid_exists(p) for p in entry["pids"]):
                del _registry[key]
                removed.append(entry["app_name"])
    if removed:
        logger.debug("RUNTIME_PURGE Removed=%r", removed)
    return removed
