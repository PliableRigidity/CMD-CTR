"""KOSINE client accessor — Phase 19 (boundary-hardened).

Returns the shared KOSINE client singleton. The COMPLIANT, default transport is
``KOSINE_TRANSPORT=rest``: a SILVIA-owned HTTP client
(``backend.app.integrations.kosine.KosineHTTPClient``) that talks to a standalone
KOSINE service over its public REST contract only — **no ``import kos``, no direct
DB access**.

A legacy ``KOSINE_TRANSPORT=local`` mode remains for migration/dev tooling that
needs KOSINE's in-process importer/backup APIs (which are not exposed over REST).
It lazily imports ``kos.sdk.KOSClient`` and is the ONLY place ``import kos`` can
occur. It is off by default and slated to move to KOSINE's CLI.

Either transport is created with ``allow_destructive=False``: SILVIA can never
trigger a destructive KOSINE tool. Non-destructive writes are additionally gated
by ``KOSINE_ALLOW_WRITES`` and audited in the provider/audit layer.
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


def _make_rest_client() -> Any:
    """Build the SILVIA-owned HTTP client (compliant, public-REST transport)."""
    from backend.app.integrations.kosine import KosineHTTPClient
    client = KosineHTTPClient(
        base_url=config.KOSINE_BASE_URL,
        timeout=config.KOSINE_TIMEOUT_SECONDS,
        max_retries=config.KOSINE_MAX_RETRIES,
        allow_destructive=False,
        api_token=config.KOSINE_API_TOKEN,
    )
    logger.info("KOSINE client ready (REST: %s)", config.KOSINE_BASE_URL)
    return client


def _make_local_client() -> Any:
    """Legacy in-process transport via the public KOSINE SDK (migration/dev only).

    This is the only code path that imports ``kos``. It opens KOSINE's SQLite DB
    directly and is therefore NOT the spec-compliant boundary — it exists solely
    for the migration tooling that needs KOSINE's importer/backup APIs.
    """
    try:
        from kos.sdk import KOSClient  # type: ignore
    except Exception:
        repo = config.KOSINE_REPO_PATH
        if repo and repo not in sys.path:
            sys.path.insert(0, repo)
        from kos.sdk import KOSClient  # type: ignore
    client = KOSClient(db_path=config.KOSINE_DB_PATH, allow_destructive=False)
    logger.info("KOSINE client ready (legacy in-process: %s)", config.KOSINE_DB_PATH)
    return client


def get_client() -> Any:
    """Return the shared KOSINE client singleton, creating it on first use.

    Raises RuntimeError if KOSINE is disabled or the client cannot be built.
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
            if config.KOSINE_TRANSPORT == "local":
                _client = _make_local_client()
            else:
                _client = _make_rest_client()
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
