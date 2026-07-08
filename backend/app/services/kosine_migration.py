"""Brain63 → KOSINE migration — Phase 19.

Gradual, safe, reversible migration of the Brain63 Obsidian vault into KOSINE's
structured store. Rides KOSINE's own vault importer (kos.importing), which is
idempotent (natural-key + content-hash dedup) so re-running is a no-op for
unchanged notes.

Safety:
- ``preview()`` computes the effect against a throwaway copy — writes nothing.
- ``migrate()`` snapshots the KOSINE db (KOSINE BackupManager) BEFORE importing,
  so any migration is one ``restore()`` away from being undone.
- Brain63 itself is never touched — it stays the read-only human-readable archive.
- Requires in-process (local) mode; REST mode can't share a Database handle.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config

logger = logging.getLogger("silvia.kosine_migration")

_REPORT_DIR = config.BASE_DIR.parent / "data" / "kosine_migration"
_BACKUP_DIR = Path(config.KOSINE_DB_PATH).parent / "backups"


class MigrationError(RuntimeError):
    pass


def _require_local() -> None:
    if config.KOSINE_BASE_URL:
        raise MigrationError(
            "Migration requires in-process mode (KOSINE_BASE_URL must be empty)."
        )
    if not config.KOSINE_ENABLED:
        raise MigrationError("KOSINE is disabled (set KOSINE_ENABLED=true).")


def _database():
    """Return a kos Database handle bound to the configured KOSINE db.

    Reuses the shared KOSClient's connection when available so we don't open a
    second writer against the same SQLite file.
    """
    from backend.app.memory.kosine_client import get_client
    client = get_client()
    db = getattr(client, "_db", None)
    if db is not None:
        return db
    from kos.database import Database  # type: ignore
    return Database(Path(config.KOSINE_DB_PATH))


def _backup_manager():
    from kos.backups import BackupManager  # type: ignore
    return BackupManager(Path(config.KOSINE_DB_PATH), _BACKUP_DIR)


def _vault_path() -> Path:
    vault = Path(config.BRAIN63_VAULT_PATH)
    if not vault.is_dir():
        raise MigrationError(f"Brain63 vault not found: {vault}")
    return vault


# ── Public API ───────────────────────────────────────────────────────────────

def preview() -> dict[str, Any]:
    """Dry-run: report what a Brain63 import would create/update. Writes nothing."""
    _require_local()
    vault = _vault_path()
    from kos.importing import preview_import  # type: ignore
    db = _database()
    report = preview_import(db, "obsidian", vault)
    result = report.to_dict()
    result["vault"] = str(vault)
    result["preview"] = True
    result["note"] = (
        "Dry-run counts are file-level estimates; the actual import extracts "
        "multiple structured objects per note, so applied counts will be higher."
    )
    logger.info("KOSINE migration preview: %s", result)
    return result


def migrate(backup: bool = True, actor: str = "silvia") -> dict[str, Any]:
    """Apply the Brain63 import into KOSINE. Snapshots the db first (reversible)."""
    _require_local()
    vault = _vault_path()

    backup_path: Optional[str] = None
    if backup:
        try:
            bp = _backup_manager().create(reason="pre_brain63_migration")
            backup_path = str(bp) if bp else None
            logger.info("KOSINE pre-migration backup: %s", backup_path)
        except Exception as e:
            raise MigrationError(f"Backup failed, aborting migration: {e}") from e

    from kos.importing import run_import  # type: ignore
    db = _database()
    report = run_import(db, "obsidian", vault)
    result = report.to_dict()
    result["vault"] = str(vault)
    result["preview"] = False
    result["backup_path"] = backup_path
    result["actor"] = actor
    result["completed_at"] = datetime.now(timezone.utc).isoformat()

    _write_report(result)
    logger.info("KOSINE migration complete: %s", result)
    return result


def list_backups() -> list[dict[str, Any]]:
    _require_local()
    try:
        return [b.to_dict() for b in _backup_manager().list_backups()]
    except Exception as e:
        logger.warning("list_backups failed: %s", e)
        return []


def restore(backup_name: str, confirm: bool = False) -> dict[str, Any]:
    """Restore the KOSINE db from a backup (undo a migration). Requires confirm=True."""
    _require_local()
    mgr = _backup_manager()
    match = next((b for b in mgr.list_backups() if b.path.name == backup_name), None)
    if not match:
        raise MigrationError(f"Backup not found: {backup_name}")
    if not confirm:
        return {"confirmation_required": True, **mgr.restore_preview(match.path)}
    # Drop the cached client so it reopens against the restored file.
    result = mgr.restore(match.path, confirm=True)
    from backend.app.memory.kosine_client import reset
    reset()
    return result


def _write_report(result: dict) -> None:
    try:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = result["completed_at"].replace(":", "").replace("-", "")[:15]
        path = _REPORT_DIR / f"migration_{stamp}.json"
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write migration report: %s", e)
