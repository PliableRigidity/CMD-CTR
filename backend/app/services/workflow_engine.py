"""Workflow Engine — Phase 17B.

Structured approval workflows with state machine, templates,
diff system, and audit trail. Transforms SILVIA's simple
approve/reject flow into a full change management system.

States: draft → pending_review → approved → executing → completed
                              → rejected
                              → cancelled
        executing → failed
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

logger = logging.getLogger("silvia.workflow")

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

VALID_STATES = frozenset({
    "draft", "pending_review", "approved", "rejected",
    "executing", "completed", "failed", "cancelled",
})

WORKFLOW_CATEGORIES = frozenset({
    "procurement", "project_change", "brain63_update",
    "memory_update", "infrastructure", "service_action",
    "calendar_change", "email_action", "robotics",
})

EXPIRY_SECONDS = 30 * 60  # 30 minutes for workflows


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Workflow Templates ──────────────────────────────────────────────────────

WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "infrastructure_action": {
        "category": "infrastructure",
        "title_template": "{action} on {target}",
        "fields": ["action", "target", "impact"],
        "risk_level": "high",
    },
    "email_send": {
        "category": "email_action",
        "title_template": "Send email to {recipient}",
        "fields": ["recipient", "subject", "body"],
        "risk_level": "critical",
    },
    "calendar_event": {
        "category": "calendar_change",
        "title_template": "Create event: {title}",
        "fields": ["title", "date", "attendees"],
        "risk_level": "moderate",
    },
    "procurement_request": {
        "category": "procurement",
        "title_template": "Order {item} for {project}",
        "fields": ["item", "project", "vendor", "estimated_cost", "priority", "reason"],
        "risk_level": "moderate",
    },
    "project_update": {
        "category": "project_change",
        "title_template": "{change_type}: {project}",
        "fields": ["project", "change_type", "before", "after", "impact"],
        "risk_level": "moderate",
    },
    "memory_entry": {
        "category": "memory_update",
        "title_template": "Record {type}: {title}",
        "fields": ["type", "project", "title", "summary"],
        "risk_level": "low",
    },
    "brain63_update": {
        "category": "brain63_update",
        "title_template": "Brain63: {file} — {change}",
        "fields": ["file", "change", "preview"],
        "risk_level": "high",
    },
    "robotics_command": {
        "category": "robotics",
        "title_template": "{command} on {target}",
        "fields": ["command", "target", "impact"],
        "risk_level": "critical",
    },
}


class WorkflowEngine:
    """Manages structured approval workflows."""

    def __init__(self) -> None:
        self._init_tables()
        self._counter = 0

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id           TEXT PRIMARY KEY,
                    code         TEXT NOT NULL UNIQUE,
                    category     TEXT NOT NULL,
                    template     TEXT NOT NULL DEFAULT '',
                    title        TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    status       TEXT NOT NULL DEFAULT 'draft',
                    risk_level   TEXT NOT NULL DEFAULT 'moderate',
                    changes      TEXT NOT NULL DEFAULT '{}',
                    before_state TEXT NOT NULL DEFAULT '',
                    after_state  TEXT NOT NULL DEFAULT '',
                    diff_text    TEXT NOT NULL DEFAULT '',
                    tool_name    TEXT NOT NULL DEFAULT '',
                    tool_args    TEXT NOT NULL DEFAULT '{}',
                    affected     TEXT NOT NULL DEFAULT '[]',
                    project      TEXT NOT NULL DEFAULT '',
                    session_id   TEXT NOT NULL DEFAULT '',
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL,
                    expires_at   TEXT NOT NULL DEFAULT '',
                    resolved_at  TEXT,
                    resolved_by  TEXT,
                    executed_at  TEXT,
                    execution_result TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_wf_status ON workflows(status);
                CREATE INDEX IF NOT EXISTS idx_wf_code ON workflows(code);
                CREATE INDEX IF NOT EXISTS idx_wf_category ON workflows(category);
                CREATE INDEX IF NOT EXISTS idx_wf_project ON workflows(project);
            """)

    def _next_code(self) -> str:
        """Generate a short human-readable workflow code."""
        with _conn() as db:
            count = db.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
        return f"WF-{count + 1:03d}"

    # ── Create ──────────────────────────────────────────────────────────────

    def create(
        self,
        category: str,
        title: str,
        description: str = "",
        risk_level: str = "moderate",
        changes: dict | None = None,
        before_state: str = "",
        after_state: str = "",
        tool_name: str = "",
        tool_args: dict | None = None,
        affected: list[str] | None = None,
        project: str = "",
        session_id: str = "",
        template: str = "",
        auto_submit: bool = True,
    ) -> dict[str, Any]:
        """Create a new workflow. auto_submit=True moves directly to pending_review."""
        self._expire_old()

        wf_id = f"wf_{uuid.uuid4().hex[:8]}"
        code = self._next_code()
        now = _now()
        expires = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() + EXPIRY_SECONDS),
        )
        status = "pending_review" if auto_submit else "draft"

        diff_text = ""
        if before_state or after_state:
            diff_text = self._generate_diff(before_state, after_state)

        with _conn() as db:
            db.execute(
                """INSERT INTO workflows
                   (id, code, category, template, title, description, status,
                    risk_level, changes, before_state, after_state, diff_text,
                    tool_name, tool_args, affected, project, session_id,
                    created_at, updated_at, expires_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    wf_id, code, category, template, title, description, status,
                    risk_level, json.dumps(changes or {}),
                    before_state, after_state, diff_text,
                    tool_name, json.dumps(tool_args or {}),
                    json.dumps(affected or []), project, session_id,
                    now, now, expires,
                ),
            )

        logger.info("Workflow %s created: %s [%s]", code, title, category)

        return {
            "workflow_id": wf_id,
            "code": code,
            "category": category,
            "title": title,
            "description": description,
            "status": status,
            "risk_level": risk_level,
            "changes": changes or {},
            "before_state": before_state,
            "after_state": after_state,
            "diff_text": diff_text,
            "tool_name": tool_name,
            "tool_args": tool_args or {},
            "affected": affected or [],
            "project": project,
            "created_at": now,
            "expires_at": expires,
        }

    # ── Approve / Reject / Cancel ──────────────────────────────────────────

    def approve(self, code: str, resolved_by: str = "user") -> dict[str, Any]:
        """Approve a pending workflow."""
        self._expire_old()
        wf = self._find_by_code(code)
        if not wf:
            return {"ok": False, "error": f"Workflow '{code}' not found."}
        if wf["status"] != "pending_review":
            return {"ok": False, "error": f"Workflow '{code}' is {wf['status']}, not pending review."}

        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='approved', resolved_at=?, resolved_by=?, updated_at=? WHERE id=?",
                (now, resolved_by, now, wf["id"]),
            )
        self._audit("approved", wf)

        return {
            "ok": True,
            "workflow": {**wf, "status": "approved", "resolved_at": now},
            "tool_name": wf["tool_name"],
            "tool_args": json.loads(wf["tool_args"]) if isinstance(wf["tool_args"], str) else wf["tool_args"],
        }

    def reject(self, code: str, resolved_by: str = "user") -> dict[str, Any]:
        """Reject a pending workflow."""
        self._expire_old()
        wf = self._find_by_code(code)
        if not wf:
            return {"ok": False, "error": f"Workflow '{code}' not found."}
        if wf["status"] != "pending_review":
            return {"ok": False, "error": f"Workflow '{code}' is {wf['status']}, not pending review."}

        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='rejected', resolved_at=?, resolved_by=?, updated_at=? WHERE id=?",
                (now, resolved_by, now, wf["id"]),
            )
        self._audit("rejected", wf)
        return {"ok": True, "code": code, "status": "rejected"}

    def cancel(self, code: str) -> dict[str, Any]:
        """Cancel a workflow (any pending state)."""
        wf = self._find_by_code(code)
        if not wf:
            return {"ok": False, "error": f"Workflow '{code}' not found."}
        if wf["status"] in ("completed", "failed", "cancelled"):
            return {"ok": False, "error": f"Workflow '{code}' is already {wf['status']}."}

        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='cancelled', updated_at=? WHERE id=?",
                (now, wf["id"]),
            )
        self._audit("cancelled", wf)
        return {"ok": True, "code": code, "status": "cancelled"}

    def mark_executing(self, code: str) -> None:
        """Mark a workflow as executing."""
        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='executing', executed_at=?, updated_at=? WHERE code=? AND status='approved'",
                (now, now, code.upper()),
            )

    def mark_completed(self, code: str, result: str = "") -> None:
        """Mark a workflow as completed with execution result."""
        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='completed', execution_result=?, executed_at=COALESCE(executed_at, ?), updated_at=? WHERE code=?",
                (result, now, now, code.upper()),
            )
        logger.info("Workflow %s completed", code)

    def mark_failed(self, code: str, error: str = "") -> None:
        """Mark a workflow as failed with error detail."""
        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='failed', execution_result=?, executed_at=COALESCE(executed_at, ?), updated_at=? WHERE code=?",
                (error, now, now, code.upper()),
            )
        logger.warning("Workflow %s failed: %s", code, error[:200])

    # ── Queries ─────────────────────────────────────────────────────────────

    def get(self, code: str) -> Optional[dict]:
        """Get a single workflow by code."""
        self._expire_old()
        return self._find_by_code(code)

    def get_pending(self, session_id: str = "") -> list[dict]:
        """List pending workflows."""
        self._expire_old()
        with _conn() as db:
            if session_id:
                rows = db.execute(
                    "SELECT * FROM workflows WHERE status='pending_review' AND session_id=? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM workflows WHERE status='pending_review' ORDER BY created_at DESC"
                ).fetchall()
        return [self._hydrate(r) for r in rows]

    def get_all(self, limit: int = 50, status: str = "") -> list[dict]:
        """List workflows, optionally filtered by status."""
        self._expire_old()
        with _conn() as db:
            if status and status in VALID_STATES:
                rows = db.execute(
                    "SELECT * FROM workflows WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM workflows ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._hydrate(r) for r in rows]

    def get_history(self, limit: int = 50) -> list[dict]:
        """List completed/failed/rejected/cancelled workflows."""
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM workflows WHERE status IN ('completed','failed','rejected','cancelled') ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._hydrate(r) for r in rows]

    def find_pending_for_session(self, session_id: str) -> Optional[dict]:
        """Find the most recent pending workflow for a session."""
        pending = self.get_pending(session_id)
        return pending[0] if pending else None

    def approve_all_pending(self, session_id: str = "", resolved_by: str = "user",
                            max_risk: str = "") -> dict[str, Any]:
        """Approve all pending workflows, optionally filtered by max risk."""
        pending = self.get_pending(session_id)
        risk_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
        max_level = risk_order.get(max_risk, 999)

        approved = []
        for wf in pending:
            wf_level = risk_order.get(wf.get("risk_level", "moderate"), 1)
            if wf_level <= max_level:
                result = self.approve(wf["code"], resolved_by=resolved_by)
                if result.get("ok"):
                    approved.append(result)
        return {"ok": True, "approved_count": len(approved), "approved": approved}

    def reject_all_pending(self, session_id: str = "", resolved_by: str = "user") -> dict[str, Any]:
        """Reject all pending workflows."""
        pending = self.get_pending(session_id)
        rejected = 0
        for wf in pending:
            result = self.reject(wf["code"], resolved_by=resolved_by)
            if result.get("ok"):
                rejected += 1
        return {"ok": True, "rejected_count": rejected}

    # ── Diff system ─────────────────────────────────────────────────────────

    def _generate_diff(self, before: str, after: str) -> str:
        """Generate a simple diff view."""
        if not before and not after:
            return ""

        lines = []
        if before:
            lines.append("--- Before ---")
            for line in before.splitlines():
                lines.append(f"  {line}")
        if after:
            lines.append("+++ After +++")
            for line in after.splitlines():
                lines.append(f"  {line}")
        return "\n".join(lines)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_by_code(self, code: str) -> Optional[dict]:
        code_upper = code.upper().strip()
        with _conn() as db:
            row = db.execute(
                "SELECT * FROM workflows WHERE UPPER(code) = ?",
                (code_upper,),
            ).fetchone()
        return self._hydrate(row) if row else None

    def _expire_old(self) -> None:
        """Expire workflows past their expiry time."""
        now = _now()
        with _conn() as db:
            db.execute(
                "UPDATE workflows SET status='cancelled' WHERE status='pending_review' AND expires_at != '' AND expires_at < ?",
                (now,),
            )

    def _hydrate(self, row) -> dict:
        if not row:
            return {}
        r = dict(row)
        for key in ("changes", "tool_args"):
            try:
                r[key] = json.loads(r[key])
            except Exception:
                r[key] = {}
        try:
            r["affected"] = json.loads(r["affected"])
        except Exception:
            r["affected"] = []
        return r

    def _audit(self, action: str, wf: dict) -> None:
        """Record workflow action in the execution ledger."""
        try:
            from backend.app.services.execution_ledger import get_ledger
            get_ledger().log_execution(
                intent=f"Workflow {action}: {wf.get('title', '')}",
                tool=wf.get("tool_name", "workflow"),
                status=action,
                message=f"{action.title()} {wf.get('code', '')} — {wf.get('title', '')}",
            )
        except Exception:
            pass


# ── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    global _instance
    if _instance is None:
        _instance = WorkflowEngine()
    return _instance
