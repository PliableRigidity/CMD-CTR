"""KOSINE suggestion apply handler — Phase 19b.

The dedicated executor for approved KOSINE suggestion workflows. This is the ONLY
place that turns an approved workflow into a KOSINE write.

Design rule: the WorkflowEngine owns approval/rejection state; it never mutates
KOSINE. This handler reads an approved workflow, validates every precondition,
and — only if all pass — dispatches the write through the single audited write
chokepoint (kosine_audit.audited_write). It then marks the workflow completed or
failed based on the outcome.

Validated preconditions before any write:
  1. workflow exists and its type is `kosine_suggestion`
  2. KOSINE_ENABLED
  3. operation is a permitted NON-DESTRUCTIVE KOSINE tool
  4. the suggestion is approved (or is being approved in this call)
  5. KOSINE_ALLOW_WRITES  (real execution only; dry-run is exempt)

Guarantees:
  - No execution when KOSINE_ALLOW_WRITES is false.
  - No destructive operations (allowlist enforced here; the client also disables
    destructive tools at the transport layer as defense in depth).
  - Every applied suggestion produces an audit record (audited_write always logs).
  - A failed write marks the workflow `failed`, never `completed`.
  - Brain63 is never touched.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from backend import config

logger = logging.getLogger("silvia.kosine_apply")

# Non-destructive KOSINE tools a suggestion is permitted to invoke.
ALLOWED_TOOLS: frozenset[str] = frozenset({
    "create_memory", "update_memory", "create_relationship", "add_event",
})

SUGGESTION_CATEGORY = "kosine_suggestion"


def _engine():
    from backend.app.services.workflow_engine import get_workflow_engine
    return get_workflow_engine()


def _err(code: str, msg: str, **extra) -> dict[str, Any]:
    return {"ok": False, "code": code, "error": msg, **extra}


def apply_suggestion(
    code: str,
    *,
    approve: bool = False,
    dry_run: bool = False,
    actor: str = "user",
) -> dict[str, Any]:
    """Validate and (optionally) execute an approved KOSINE suggestion workflow.

    :param code: workflow code (e.g. "WF-042").
    :param approve: if True, approve the workflow first (draft → pending_review →
                    approved), then apply. If False, the workflow must already be
                    approved.
    :param dry_run: validate + report the write that WOULD run, without executing
                    and without changing workflow status. Exempt from the
                    allow-writes gate because it performs no write.
    :param actor: who initiated the apply.
    """
    engine = _engine()
    wf = engine.get(code)
    if not wf:
        return _err(code, f"Workflow '{code}' not found.")

    # 1) type check — refuse anything that isn't a KOSINE suggestion
    if wf.get("category") != SUGGESTION_CATEGORY:
        return _err(code, f"Workflow '{code}' is not a KOSINE suggestion "
                          f"(category={wf.get('category')!r}).")

    # 2) KOSINE must be enabled
    if not config.KOSINE_ENABLED:
        return _err(code, "KOSINE is disabled (KOSINE_ENABLED=false).")

    # 3) non-destructive operation only — enforced before approval/execution
    tool = wf.get("tool_name") or ""
    args = wf.get("tool_args") or {}
    if not isinstance(args, dict):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if tool not in ALLOWED_TOOLS:
        engine.mark_failed(code, f"Rejected: '{tool}' is not a permitted non-destructive KOSINE operation.")
        return _err(code, f"Operation '{tool}' is not permitted (destructive or unsupported). "
                          f"Allowed: {sorted(ALLOWED_TOOLS)}.", status="failed")

    # 4) approval — WorkflowEngine owns this state transition
    status = wf.get("status")
    if approve:
        if status == "draft":
            engine.submit(code)
            status = "pending_review"
        if status == "pending_review":
            res = engine.approve(code, resolved_by=actor)
            if not res.get("ok"):
                return _err(code, res.get("error", "Approval failed."))
        wf = engine.get(code) or wf
        status = wf.get("status")

    if status != "approved":
        return _err(code, f"Workflow '{code}' is {status}, not approved. "
                          f"Approve it first (or use 'approve and apply').", status=status)

    # dry-run: report the write, change nothing (status stays 'approved')
    if dry_run:
        return {
            "ok": True, "code": code, "dry_run": True, "status": status,
            "would_apply": {"tool": tool, "args": args},
            "allow_writes": config.KOSINE_ALLOW_WRITES,
        }

    # 5) hard write gate — real execution requires KOSINE_ALLOW_WRITES.
    # Deliberately NOT marked failed: the suggestion stays approved so it can be
    # applied later once writes are enabled.
    if not config.KOSINE_ALLOW_WRITES:
        return _err(code, "KOSINE writes are disabled (KOSINE_ALLOW_WRITES=false); nothing was applied.",
                    status=status)

    # ── execute through the single audited write chokepoint ──────────────────
    from backend.app.memory import kosine_audit
    engine.mark_executing(code)
    try:
        data = kosine_audit.audited_write(tool, args, actor=actor, reason=f"apply {code}")
    except Exception as e:
        engine.mark_failed(code, str(e))
        logger.warning("KOSINE apply %s failed: %s", code, e)
        return _err(code, str(e), status="failed")

    result = {"tool": tool, "args": args, "data": data}
    engine.mark_completed(code, json.dumps(result, default=str)[:2000])
    logger.info("KOSINE suggestion %s applied by %s", code, actor)
    return {"ok": True, "code": code, "status": "completed", "applied": True, "result": data}
