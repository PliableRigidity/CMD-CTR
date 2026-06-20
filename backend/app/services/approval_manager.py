"""Approval Manager — Phase 17A.

Manages the lifecycle of action approvals: create, approve, reject,
expire, execute. Pending approvals expire after 15 minutes.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("silvia.approval")

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

EXPIRY_SECONDS = 15 * 60  # 15 minutes

_STATUSES = frozenset({"pending", "approved", "rejected", "expired", "executed"})


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_ts() -> float:
    return time.time()


class ApprovalManager:
    """Manages pending action approvals."""

    def __init__(self) -> None:
        self._init_tables()
        self._counter = 0

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id          TEXT PRIMARY KEY,
                    code        TEXT NOT NULL UNIQUE,
                    tool_name   TEXT NOT NULL,
                    args        TEXT NOT NULL DEFAULT '{}',
                    risk_level  INTEGER NOT NULL,
                    risk_name   TEXT NOT NULL,
                    reason      TEXT NOT NULL DEFAULT '',
                    query       TEXT NOT NULL DEFAULT '',
                    session_id  TEXT NOT NULL DEFAULT '',
                    status      TEXT NOT NULL DEFAULT 'pending',
                    created_at  TEXT NOT NULL,
                    expires_at  TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_pa_status ON pending_approvals(status);
                CREATE INDEX IF NOT EXISTS idx_pa_code ON pending_approvals(code);
                CREATE INDEX IF NOT EXISTS idx_pa_session ON pending_approvals(session_id);
            """)

    def _next_code(self) -> str:
        """Generate a short human-readable approval code."""
        self._counter += 1
        with _conn() as db:
            count = db.execute("SELECT COUNT(*) FROM pending_approvals").fetchone()[0]
        return f"APR-{count + 1:03d}"

    # ── Create ──────────────────────────────────────────────────────────────

    def create(self, tool_name: str, args: dict, risk_level: int,
               risk_name: str, reason: str, query: str = "",
               session_id: str = "") -> dict[str, Any]:
        """Create a pending approval for a gated action."""
        self._expire_old()

        aid = f"apr_{uuid.uuid4().hex[:8]}"
        code = self._next_code()
        now = _now()
        expires = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() + EXPIRY_SECONDS),
        )

        with _conn() as db:
            db.execute(
                """INSERT INTO pending_approvals
                   (id, code, tool_name, args, risk_level, risk_name, reason,
                    query, session_id, status, created_at, expires_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    aid, code, tool_name, json.dumps(args), risk_level,
                    risk_name, reason, query, session_id,
                    "pending", now, expires,
                ),
            )

        return {
            "approval_id": aid,
            "code": code,
            "tool_name": tool_name,
            "args": args,
            "risk_level": risk_level,
            "risk_name": risk_name,
            "reason": reason,
            "status": "pending",
            "created_at": now,
            "expires_at": expires,
        }

    # ── Approve / Reject ────────────────────────────────────────────────────

    def approve(self, code: str, resolved_by: str = "user") -> dict[str, Any]:
        """Approve a pending action by its code."""
        self._expire_old()
        approval = self._find_by_code(code)
        if not approval:
            return {"ok": False, "error": f"Approval '{code}' not found."}
        if approval["status"] != "pending":
            return {"ok": False, "error": f"Approval '{code}' is already {approval['status']}."}

        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE pending_approvals SET status='approved', resolved_at=?, resolved_by=? WHERE id=?",
                (now, resolved_by, approval["id"]),
            )

        self._audit("approved", approval)

        return {
            "ok": True,
            "approval": {**approval, "status": "approved", "resolved_at": now},
            "tool_name": approval["tool_name"],
            "args": json.loads(approval["args"]) if isinstance(approval["args"], str) else approval["args"],
        }

    def reject(self, code: str, resolved_by: str = "user") -> dict[str, Any]:
        """Reject a pending action."""
        self._expire_old()
        approval = self._find_by_code(code)
        if not approval:
            return {"ok": False, "error": f"Approval '{code}' not found."}
        if approval["status"] != "pending":
            return {"ok": False, "error": f"Approval '{code}' is already {approval['status']}."}

        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE pending_approvals SET status='rejected', resolved_at=?, resolved_by=? WHERE id=?",
                (now, resolved_by, approval["id"]),
            )

        self._audit("rejected", approval)
        return {"ok": True, "code": code, "status": "rejected"}

    def mark_executed(self, code: str) -> None:
        """Mark an approved action as executed."""
        with _conn() as db:
            db.execute(
                "UPDATE pending_approvals SET status='executed', resolved_at=? WHERE code=? AND status='approved'",
                (_now(), code),
            )

    # ── Queries ─────────────────────────────────────────────────────────────

    def get_pending(self, session_id: str = "") -> list[dict]:
        """List pending approvals, optionally filtered by session."""
        self._expire_old()
        with _conn() as db:
            if session_id:
                rows = db.execute(
                    "SELECT * FROM pending_approvals WHERE status='pending' AND session_id=? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM pending_approvals WHERE status='pending' ORDER BY created_at DESC"
                ).fetchall()
        return [self._hydrate(r) for r in rows]

    def get_all(self, limit: int = 50) -> list[dict]:
        """List all approvals (all statuses)."""
        self._expire_old()
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM pending_approvals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._hydrate(r) for r in rows]

    def approve_all_pending(self, session_id: str = "", resolved_by: str = "user") -> dict[str, Any]:
        """Approve all pending approvals."""
        pending = self.get_pending(session_id)
        approved = []
        for p in pending:
            result = self.approve(p["code"], resolved_by=resolved_by)
            if result.get("ok"):
                approved.append(result)
        return {"ok": True, "approved_count": len(approved), "approved": approved}

    def reject_all_pending(self, session_id: str = "", resolved_by: str = "user") -> dict[str, Any]:
        """Reject all pending approvals."""
        pending = self.get_pending(session_id)
        rejected = 0
        for p in pending:
            result = self.reject(p["code"], resolved_by=resolved_by)
            if result.get("ok"):
                rejected += 1
        return {"ok": True, "rejected_count": rejected}

    def find_pending_for_session(self, session_id: str) -> Optional[dict]:
        """Find the most recent pending approval for a session."""
        pending = self.get_pending(session_id)
        return pending[0] if pending else None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_by_code(self, code: str) -> Optional[dict]:
        code_upper = code.upper().strip()
        with _conn() as db:
            row = db.execute(
                "SELECT * FROM pending_approvals WHERE UPPER(code) = ?",
                (code_upper,),
            ).fetchone()
        return dict(row) if row else None

    def _expire_old(self) -> None:
        """Expire approvals that have passed their expiry time."""
        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE pending_approvals SET status='expired' WHERE status='pending' AND expires_at < ?",
                (now,),
            )

    def _hydrate(self, row) -> dict:
        r = dict(row)
        try:
            r["args"] = json.loads(r["args"])
        except Exception:
            r["args"] = {}
        return r

    def _audit(self, action: str, approval: dict) -> None:
        """Record approval action in the execution ledger."""
        try:
            from backend.app.services.execution_ledger import get_ledger
            get_ledger().record(
                intent=f"Approval {action}: {approval.get('tool_name', '')}",
                tool=approval.get("tool_name", ""),
                args=approval.get("args", {}),
                result={"status": action, "code": approval.get("code", "")},
                status=action,
                message=f"{action.title()} {approval.get('code', '')} — {approval.get('tool_name', '')}",
            )
        except Exception:
            pass


_instance: Optional[ApprovalManager] = None


def get_approval_manager() -> ApprovalManager:
    global _instance
    if _instance is None:
        _instance = ApprovalManager()
    return _instance
