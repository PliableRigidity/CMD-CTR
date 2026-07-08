"""KOSINE client wrapper — Phase 19.

Thin singleton around ``kos.sdk.KOSClient`` so the rest of SILVIA never imports
KOSINE internals directly. Talks to KOSINE in-process (local SQLite mode) by
default, or over REST when ``KOSINE_BASE_URL`` is set.

Design notes:
- ``import kos`` is attempted normally first; if KOSINE isn't installed on the
  path we fall back to ``KOSINE_REPO_PATH`` so a plain source checkout works.
- The shared client is created with ``allow_destructive=False``. Destructive
  KOSINE tools (delete/merge) therefore stay disabled at the transport layer —
  SILVIA can never trigger one, even by accident. Non-destructive writes
  (create/update/relate) are additionally gated by ``KOSINE_ALLOW_WRITES`` and
  audited in the provider layer.
"""
from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Optional

from backend import config

logger = logging.getLogger("silvia.memory.kosine_client")

_client: Any = None
_import_error: Optional[str] = None
_lock = threading.Lock()


def _load_kosclient_cls():
    """Import kos.sdk.KOSClient, adding the repo path to sys.path if needed."""
    try:
        from kos.sdk import KOSClient  # type: ignore
        return KOSClient
    except Exception as first_err:  # not installed on the path — try the repo dir
        repo = config.KOSINE_REPO_PATH
        if repo and repo not in sys.path:
            sys.path.insert(0, repo)
        try:
            from kos.sdk import KOSClient  # type: ignore
            return KOSClient
        except Exception as second_err:
            raise ImportError(
                f"KOSINE SDK unavailable (import error: {first_err}; "
                f"after adding {repo!r}: {second_err})"
            ) from second_err


def get_client() -> Any:
    """Return the shared KOSClient singleton, creating it on first use.

    Raises RuntimeError if KOSINE is disabled or the SDK cannot be loaded.
    """
    global _client, _import_error
    if not config.KOSINE_ENABLED:
        raise RuntimeError("KOSINE is disabled (set KOSINE_ENABLED=true)")
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        try:
            KOSClient = _load_kosclient_cls()
            if config.KOSINE_BASE_URL:
                _client = KOSClient(
                    base_url=config.KOSINE_BASE_URL,
                    allow_destructive=False,
                )
                logger.info("KOSINE client ready (REST mode: %s)", config.KOSINE_BASE_URL)
            else:
                _client = KOSClient(
                    db_path=config.KOSINE_DB_PATH,
                    allow_destructive=False,
                )
                logger.info("KOSINE client ready (in-process: %s)", config.KOSINE_DB_PATH)
            _import_error = None
        except Exception as e:
            _import_error = str(e)
            logger.warning("KOSINE client init failed: %s", e)
            raise RuntimeError(f"KOSINE client init failed: {e}") from e
    return _client


def is_available() -> bool:
    """True if KOSINE is enabled and a client can be obtained + answers a call."""
    if not config.KOSINE_ENABLED:
        return False
    try:
        client = get_client()
        # A cheap read that exercises the transport. Bounded to keep it fast.
        client.list_objects(limit=1)
        return True
    except Exception as e:
        logger.debug("KOSINE availability check failed: %s", e)
        return False


def last_error() -> Optional[str]:
    return _import_error


def reset() -> None:
    """Drop the cached client (used by tests and after config changes)."""
    global _client
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
        _client = None
