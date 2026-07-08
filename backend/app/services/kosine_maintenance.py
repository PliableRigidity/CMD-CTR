"""KOSINE autonomous maintenance loop — Phase 19.

Scans the KOSINE structured store for stale / incomplete / orphaned / duplicate
knowledge and turns findings into *suggestions*. It NEVER modifies knowledge on
its own:

- ``scan()`` is strictly read-only — it returns findings and nothing else.
- ``run(draft=True)`` may additionally create WorkflowEngine **drafts** (not
  auto-submitted, not executed) describing the proposed fix — but only when
  ``KOSINE_MAINTENANCE_AUTODRAFT`` is enabled. Drafts require explicit human
  review/approval before anything happens, mirroring the Brain63 steward pattern.

Every suggested fix carries the exact KOSINE tool + params that would apply it,
so an approved workflow is auditable and reproducible.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from backend import config

logger = logging.getLogger("silvia.kosine_maintenance")

# Thresholds (days)
STALE_DAYS = 90
TASK_STALE_DAYS = 30
# Bound expensive per-object relationship checks so a big graph can't stall a scan.
ORPHAN_CHECK_CAP = 60
# Types where an empty description is a real gap worth flagging.
DESCRIPTION_REQUIRED_TYPES = {"Project", "Goal", "Decision", "Task", "Milestone", "Risk"}
# Types we care about for orphan detection (structural anchors).
ORPHAN_CHECK_TYPES = {"Project", "Goal", "Decision", "Milestone"}


def _client():
    from backend.app.memory.kosine_client import get_client
    return get_client()


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _age_days(value: str, *, now: datetime) -> Optional[float]:
    dt = _parse_dt(value)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 86400.0


def _finding(kind: str, obj: dict, detail: str, severity: str, action: dict) -> dict:
    return {
        "kind": kind,
        "object_id": obj.get("id", ""),
        "title": obj.get("title", ""),
        "type": obj.get("type", ""),
        "detail": detail,
        "severity": severity,          # info | warn
        "suggested_action": action,    # {tool, params} — the exact fix, not applied
    }


# ── Detectors (read-only) ──────────────────────────────────────────────────────

def scan(limit: int = 100) -> dict[str, Any]:
    """Read-only scan. Returns findings grouped and flat; writes nothing."""
    client = _client()
    now = datetime.now(timezone.utc)
    objs = client.list_objects(limit=100000) or []

    findings: list[dict] = []

    # 1) stale active objects & 2) stale tasks
    for obj in objs:
        status = (obj.get("status") or "").lower()
        otype = obj.get("type") or ""
        age = _age_days(obj.get("updated_at") or obj.get("created_at") or "", now=now)
        if status == "active" and age is not None:
            if otype == "Task" and age >= TASK_STALE_DAYS:
                findings.append(_finding(
                    "stale_task", obj,
                    f"Active task untouched for {int(age)}d (>{TASK_STALE_DAYS}d).",
                    "warn",
                    {"tool": "add_event", "params": {
                        "target": obj.get("id", ""),
                        "description": "Maintenance: review — task may be stale/abandoned.",
                        "event_type": "observation_recorded",
                    }},
                ))
            elif otype != "Task" and age >= STALE_DAYS:
                findings.append(_finding(
                    "stale", obj,
                    f"Active {otype or 'object'} untouched for {int(age)}d (>{STALE_DAYS}d).",
                    "info",
                    {"tool": "add_event", "params": {
                        "target": obj.get("id", ""),
                        "description": "Maintenance: confirm still active or archive.",
                        "event_type": "observation_recorded",
                    }},
                ))

        # 3) incomplete (missing description)
        if otype in DESCRIPTION_REQUIRED_TYPES and not (obj.get("description") or "").strip():
            findings.append(_finding(
                "incomplete", obj,
                f"{otype} has no description.",
                "info",
                {"tool": "update_memory", "params": {
                    "target": obj.get("id", ""),
                    "description": "<add a one-line description>",
                }},
            ))

    # 4) duplicates — same type + normalized title
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for obj in objs:
        key = (obj.get("type", ""), re.sub(r"\s+", " ", (obj.get("title") or "").strip().lower()))
        if key[1]:
            groups[key].append(obj)
    for (otype, norm_title), members in groups.items():
        if len(members) > 1:
            ids = [m.get("id", "") for m in members]
            findings.append(_finding(
                "duplicate", members[0],
                f"{len(members)} {otype} objects share the title '{members[0].get('title')}': {ids}.",
                "warn",
                # Deliberately NOT a destructive merge — surfaced for human decision.
                {"tool": None, "params": {"duplicate_ids": ids}},
            ))

    # 5) orphans (no relationships) — bounded to structural anchor types
    orphan_candidates = [o for o in objs if o.get("type") in ORPHAN_CHECK_TYPES]
    checked = 0
    skipped = 0
    for obj in orphan_candidates:
        if checked >= ORPHAN_CHECK_CAP:
            skipped = len(orphan_candidates) - checked
            break
        checked += 1
        try:
            rels = client.get_related(obj.get("id", "")) or []
        except Exception:
            continue
        if not rels:
            findings.append(_finding(
                "orphan", obj,
                f"{obj.get('type')} '{obj.get('title')}' has no relationships.",
                "info",
                {"tool": None, "params": {"hint": "link to a related Project/Goal/Decision"}},
            ))
    if skipped:
        logger.info("Orphan check capped at %d; %d anchor objects not checked.", ORPHAN_CHECK_CAP, skipped)

    by_kind: dict[str, int] = defaultdict(int)
    for f in findings:
        by_kind[f["kind"]] += 1

    findings = findings[:limit]
    return {
        "scanned": len(objs),
        "findings": findings,
        "findings_count": len(findings),
        "by_kind": dict(by_kind),
        "orphan_check_skipped": skipped,
        "generated_at": now.isoformat(),
    }


# ── Suggestion drafting (approval-gated, never executed) ────────────────────────

def run(draft: bool = False) -> dict[str, Any]:
    """Scan and optionally draft suggestion workflows.

    Drafts are created only when ``draft=True`` AND KOSINE_MAINTENANCE_AUTODRAFT
    is enabled. They are WorkflowEngine drafts (auto_submit=False) — pure
    suggestions that a human must review; nothing is applied to KOSINE here.
    """
    result = scan()
    findings = result["findings"]
    autodraft_allowed = config.KOSINE_MAINTENANCE_AUTODRAFT
    drafted: list[str] = []

    if draft and autodraft_allowed and findings:
        try:
            from backend.app.services.workflow_engine import WorkflowEngine
            engine = WorkflowEngine()
            for f in findings:
                if not f.get("suggested_action", {}).get("tool"):
                    continue  # informational only (e.g. duplicates/orphans) — no auto-fix tool
                wf = engine.create(
                    category="kosine_suggestion",
                    title=f"KOSINE {f['kind']}: {f['title'] or f['object_id']}",
                    description=f["detail"],
                    risk_level="low",
                    changes={"suggested_action": f["suggested_action"], "finding": f},
                    tool_name=f["suggested_action"]["tool"],
                    tool_args=f["suggested_action"]["params"],
                    affected=[f["object_id"]] if f["object_id"] else [],
                    project="KOSINE",
                    template="kosine_suggestion",
                    auto_submit=False,  # draft only — requires explicit human review + apply
                )
                drafted.append(wf.get("code", ""))
        except Exception as e:
            logger.warning("Suggestion drafting failed: %s", e)

    return {
        **result,
        "autodraft_allowed": autodraft_allowed,
        "drafted": drafted,
        "drafted_count": len(drafted),
    }
