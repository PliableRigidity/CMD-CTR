"""Brain63 → KOSINE migration — Phase 19 (spec-compliant, CLI-driven).

Gradual, safe, reversible migration of the Brain63 Obsidian vault into KOSINE's
structured store. SILVIA drives this entirely through **KOSINE's own public
CLI** (``kosine import obsidian``, ``backup``, ``backups``, ``restore``) run as a
subprocess — it does **not** ``import kos`` and does **not** open KOSINE's
database. KOSINE's importer is idempotent (natural-key + content-hash dedup), so
re-running is a no-op for unchanged notes.

Safety:
- ``preview()`` runs ``import ... --dry-run`` — writes nothing.
- ``migrate()`` runs ``backup`` first (reversible), then the import.
- Brain63 itself is never touched — it stays the read-only human-readable archive.

The CLI operates on the DB at ``KOSINE_DB_PATH``. If a KOSINE REST service is
running against the same DB, run migration while it is idle (KOSINE owns its own
concurrency; SILVIA only invokes the public CLI).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend import config

logger = logging.getLogger("silvia.kosine_migration")

_REPORT_DIR = config.BASE_DIR.parent / "data" / "kosine_migration"
_CLI_TIMEOUT = 600  # seconds; vault imports can take a while


class MigrationError(RuntimeError):
    pass


def _require_enabled() -> None:
    if not config.KOSINE_ENABLED:
        raise MigrationError("KOSINE is disabled (set KOSINE_ENABLED=true).")


def _cli_base() -> list[str]:
    """Resolve KOSINE's CLI invocation without importing kos.

    Order: explicit ``KOSINE_CLI`` → ``kosine`` on PATH → ``python <repo>/kos.py``.
    """
    if config.KOSINE_CLI:
        return config.KOSINE_CLI.split()
    exe = shutil.which("kosine")
    if exe:
        return [exe]
    kos_py = Path(config.KOSINE_REPO_PATH) / "kos.py"
    if kos_py.is_file():
        return [sys.executable, str(kos_py)]
    raise MigrationError(
        "KOSINE CLI not found. Install KOSINE (`kosine` on PATH), set KOSINE_CLI, "
        f"or ensure {kos_py} exists."
    )


def _run_cli(*args: str, timeout: int = _CLI_TIMEOUT) -> tuple[int, str]:
    """Run `kosine --db <KOSINE_DB_PATH> <args...>`; return (returncode, output)."""
    cmd = _cli_base() + ["--db", config.KOSINE_DB_PATH, *args]
    logger.info("KOSINE CLI: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise MigrationError(f"KOSINE CLI timed out after {timeout}s") from e
    except OSError as e:
        raise MigrationError(f"KOSINE CLI failed to launch: {e}") from e
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _vault_path() -> str:
    vault = Path(config.BRAIN63_VAULT_PATH)
    if not vault.is_dir():
        raise MigrationError(f"Brain63 vault not found: {vault}")
    return str(vault)


# ── Public API (unchanged signatures — api/kosine.py stays compatible) ────────

def preview() -> dict[str, Any]:
    """Dry-run a Brain63 import via the KOSINE CLI. Writes nothing."""
    _require_enabled()
    vault = _vault_path()
    rc, out = _run_cli("import", "obsidian", vault, "--dry-run")
    if rc != 0:
        raise MigrationError(f"KOSINE import --dry-run failed:\n{out[-1500:]}")
    return {
        "preview": True,
        "vault": vault,
        "output": out[-4000:],
        "note": ("Dry-run via `kosine import obsidian --dry-run`; the importer is "
                 "idempotent so re-running applies only new/changed notes."),
    }


def migrate(backup: bool = True, actor: str = "silvia") -> dict[str, Any]:
    """Import Brain63 into KOSINE via the CLI, snapshotting the db first."""
    _require_enabled()
    vault = _vault_path()

    backup_output: Optional[str] = None
    if backup:
        rc, out = _run_cli("backup")
        if rc != 0:
            raise MigrationError(f"Backup failed, aborting migration:\n{out[-1500:]}")
        backup_output = out[-2000:]
        logger.info("KOSINE pre-migration backup done")

    rc, out = _run_cli("import", "obsidian", vault, "--yes")
    if rc != 0:
        raise MigrationError(f"KOSINE import failed:\n{out[-1500:]}")

    result = {
        "preview": False,
        "vault": vault,
        "actor": actor,
        "backup_output": backup_output,
        "output": out[-4000:],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_report(result)
    logger.info("KOSINE migration complete via CLI")
    return result


def list_backups() -> dict[str, Any]:
    """List KOSINE backups via the CLI (raw output; format is KOSINE's own)."""
    _require_enabled()
    rc, out = _run_cli("backups")
    if rc != 0:
        logger.warning("KOSINE backups listing failed: %s", out[-500:])
        return {"available": False, "output": out[-2000:]}
    return {"available": True, "output": out[-4000:]}


def restore(backup_name: str, confirm: bool = False) -> dict[str, Any]:
    """Restore the KOSINE db from a backup via the CLI. Requires confirm=True."""
    _require_enabled()
    if not backup_name:
        raise MigrationError("A backup name/path is required to restore.")
    if not confirm:
        return {
            "confirmation_required": True,
            "backup": backup_name,
            "note": "Re-call with confirm=true to run `kosine restore` "
                    "(confirmation phrase RESTORE is supplied automatically).",
        }
    rc, out = _run_cli("restore", backup_name, "--confirm", "RESTORE", "--yes")
    if rc != 0:
        raise MigrationError(f"KOSINE restore failed:\n{out[-1500:]}")
    # Drop any cached client so subsequent reads see the restored data.
    try:
        from backend.app.memory.kosine_client import reset
        reset()
    except Exception:
        pass
    return {"restored": True, "backup": backup_name, "output": out[-2000:]}


def _write_report(result: dict) -> None:
    try:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = result["completed_at"].replace(":", "").replace("-", "")[:15]
        path = _REPORT_DIR / f"migration_{stamp}.json"
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write migration report: %s", e)
