"""Telegram Chat Bridge — Phase 14C+.

Polls the Telegram Bot API and routes incoming messages through SILVIA's
existing conversation pipeline, then sends the reply back to Telegram.

IMPORTANT: Only ONE process may poll a given bot token at a time.  Starting
a second poller produces a 409 Conflict from the Telegram API.  This module
uses a PID-based lock file to enforce the singleton constraint, and handles
Conflict errors gracefully (log once, stop, do not retry).

Security: only user IDs listed in TELEGRAM_ALLOWED_USER_IDS are processed.
All others receive "Unauthorized." and their messages are dropped.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.app.orchestration.assistant_router import AssistantPlatformRouter

logger = logging.getLogger("silvia.telegram")

_TELEGRAM_CHAR_LIMIT = 4000  # Telegram hard limit is 4096; leave headroom

_bridge_instance: Optional["TelegramBridge"] = None

# ── Lock file ────────────────────────────────────────────────────────────────

_LOCK_DIR = Path(__file__).resolve().parents[3] / ".runtime"
_LOCK_FILE = _LOCK_DIR / "telegram.lock"


def _pid_alive(pid: int) -> bool:
    """Check whether a process with *pid* is still running.

    On Windows, OpenProcess can succeed for recently-exited processes
    whose kernel objects haven't been cleaned up.  We check the exit
    code via GetExitCodeProcess — STILL_ACTIVE (259) means alive.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        if not ok:
            return False
        return exit_code.value == STILL_ACTIVE
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _is_uvicorn_reload_parent() -> bool:
    """Detect if we are the uvicorn reload *supervisor* (not the worker).

    When ``uvicorn --reload`` is used, the parent process spawns a child
    worker and watches files.  Both import the application, but only the
    worker should start the Telegram poller.  The parent sets
    ``UVICORN_STARTED`` but *not* ``WATCHFILES_`` env vars (the child
    inherits them).  A simpler heuristic: the ``--reload`` flag is in
    ``sys.argv`` and ``os.environ`` does not contain the watchfiles
    marker that uvicorn injects into the worker.
    """
    if "--reload" not in sys.argv:
        return False
    return "WATCHFILES_FORCE_POLLING" not in os.environ and not os.environ.get("_UVICORN_WORKER")


def _acquire_lock() -> bool:
    """Try to write our PID to the lock file.  Returns True on success."""
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()

    if _LOCK_FILE.exists():
        try:
            data = json.loads(_LOCK_FILE.read_text())
            existing_pid = data.get("pid", 0)
            if _pid_alive(existing_pid):
                logger.warning(
                    "Telegram lock held by PID %d (still alive) — skipping startup",
                    existing_pid,
                )
                return False
            logger.info(
                "Stale Telegram lock from PID %d (dead) — taking over",
                existing_pid,
            )
        except (json.JSONDecodeError, OSError):
            logger.info("Corrupt Telegram lock file — overwriting")

    _LOCK_FILE.write_text(json.dumps({
        "pid": pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }))
    atexit.register(_release_lock)
    logger.info("Acquired Telegram lock (PID %d)", pid)
    return True


def _release_lock() -> None:
    """Remove the lock file if we own it."""
    try:
        if _LOCK_FILE.exists():
            data = json.loads(_LOCK_FILE.read_text())
            if data.get("pid") == os.getpid():
                _LOCK_FILE.unlink(missing_ok=True)
                logger.info("Released Telegram lock (PID %d)", os.getpid())
    except Exception as exc:
        logger.debug("Could not release Telegram lock: %s", exc)


def _read_lock() -> Optional[dict]:
    """Read the lock file contents, or None."""
    try:
        if _LOCK_FILE.exists():
            return json.loads(_LOCK_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return None


# ── Bridge ───────────────────────────────────────────────────────────────────

class TelegramBridge:
    """Polls Telegram and routes messages through SILVIA's chat pipeline."""

    def __init__(
        self,
        token: str,
        allowed_user_ids: set[int],
        router: "AssistantPlatformRouter",
    ) -> None:
        self._token = token
        self._allowed = allowed_user_ids
        self._router = router
        self._app = None
        self._running = False
        self._started_at: str = ""
        self._conflict_logged = False

    async def start(self) -> bool:
        try:
            from telegram.ext import Application, MessageHandler, filters
            from telegram.error import Conflict
        except ImportError:
            logger.error(
                "python-telegram-bot is not installed. "
                "Run: pip install 'python-telegram-bot>=21'"
            )
            return False

        self._app = Application.builder().token(self._token).build()

        from telegram.ext import MessageHandler, filters as tg_filters
        self._app.add_handler(
            MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, self._on_message)
        )
        self._app.add_error_handler(self._on_error)

        try:
            await self._app.initialize()
            await self._app.bot.get_updates(timeout=0, limit=1)
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
        except Conflict:
            logger.error(
                "Telegram 409 Conflict: another process is already polling "
                "this bot token. Only one backend instance may use a given "
                "Telegram bot token. Stop the other instance or set "
                "TELEGRAM_ENABLED=false."
            )
            try:
                await self._app.shutdown()
            except Exception as exc:
                logger.debug("Telegram cleanup after conflict: %s", exc)
            return False
        except Exception as exc:
            logger.error("Telegram bridge failed to start: %s", exc)
            try:
                await self._app.shutdown()
            except Exception:
                pass
            return False

        self._running = True
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info(
            "Telegram bridge started — polling active, %d allowed user(s)",
            len(self._allowed),
        )
        return True

    async def stop(self) -> None:
        if not (self._app and self._running):
            return
        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:
            logger.warning("Telegram bridge shutdown error: %s", exc)
        self._running = False
        logger.info("Telegram bridge stopped")

    async def _on_error(self, update, context) -> None:
        """Handle errors from the polling loop, especially 409 Conflict."""
        try:
            from telegram.error import Conflict
        except ImportError:
            return

        error = context.error
        if isinstance(error, Conflict):
            if not self._conflict_logged:
                self._conflict_logged = True
                logger.error(
                    "Telegram 409 Conflict during polling — another instance "
                    "took over. Stopping bridge (will not retry)."
                )
            await self.stop()
            _release_lock()
            return

        logger.error("Telegram bridge error: %s", error, exc_info=error)

    async def _on_message(self, update, context) -> None:
        user = update.effective_user
        user_id: int | None = user.id if user else None
        text: str = (update.message.text or "").strip() if update.message else ""

        if not text or user_id is None:
            return

        if user_id not in self._allowed:
            logger.warning("Unauthorized Telegram user %s blocked", user_id)
            await update.message.reply_text("Unauthorized.")
            return

        logger.info("Authorized message from Telegram user %s: %r", user_id, text[:120])

        from backend.app.models.assistant import AssistantRequest

        request = AssistantRequest(
            query=text,
            mode="auto",
            session_id=f"telegram_{user_id}",
            metadata={
                "source": "telegram",
                "telegram_user_id": str(user_id),
            },
        )

        try:
            logger.info("Forwarding message to SILVIA pipeline")
            response = await self._router.handle(request)
            reply = response.answer
        except Exception as exc:
            logger.error("SILVIA pipeline error handling Telegram message: %s", exc)
            reply = "Sorry, an internal error occurred. Please try again."

        logger.info("Sending Telegram reply (%d chars)", len(reply))
        for chunk in _split_message(reply):
            await update.message.reply_text(chunk)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def started_at(self) -> str:
        return self._started_at

    @property
    def pid(self) -> int:
        return os.getpid()


def _split_message(text: str, limit: int = _TELEGRAM_CHAR_LIMIT) -> list[str]:
    """Split long messages into Telegram-safe chunks at newline boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip("\n")
    return chunks


def get_bridge() -> Optional[TelegramBridge]:
    """Return the running bridge instance, or None if not started."""
    return _bridge_instance


async def start_bridge(router: "AssistantPlatformRouter") -> Optional[TelegramBridge]:
    """Initialize and start the Telegram bridge if configured.

    Called at app startup.  Guards against multiple polling instances via
    a PID lock file and uvicorn-reload detection.
    """
    global _bridge_instance

    from backend.config import (
        TELEGRAM_ENABLED,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_ALLOWED_USER_IDS,
    )

    if not TELEGRAM_ENABLED:
        logger.info("Telegram bridge disabled (TELEGRAM_ENABLED=false)")
        return None

    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_ENABLED=true but TELEGRAM_BOT_TOKEN is not set — "
            "Telegram bridge will not start. Set TELEGRAM_BOT_TOKEN in .env"
        )
        return None

    if not TELEGRAM_ALLOWED_USER_IDS:
        logger.error(
            "TELEGRAM_BOT_TOKEN is set but TELEGRAM_ALLOWED_USER_IDS is empty. "
            "Refusing to start an open bot — add your Telegram user ID to .env"
        )
        return None

    # Guard 1: uvicorn --reload parent process should not poll
    if _is_uvicorn_reload_parent():
        logger.info("Telegram bridge skipped — uvicorn reload parent process")
        return None

    # Guard 2: PID lock file
    if not _acquire_lock():
        return None

    bridge = TelegramBridge(
        token=TELEGRAM_BOT_TOKEN,
        allowed_user_ids=TELEGRAM_ALLOWED_USER_IDS,
        router=router,
    )
    if not await bridge.start():
        _release_lock()
        return None
    _bridge_instance = bridge
    return bridge


async def stop_bridge() -> None:
    """Stop the Telegram bridge and release the lock. Called at app shutdown."""
    global _bridge_instance
    if _bridge_instance is not None:
        await _bridge_instance.stop()
        _bridge_instance = None
    _release_lock()
