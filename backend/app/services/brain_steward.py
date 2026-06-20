"""Brain Steward — Phase 18B.

Safe Brain63 maintenance through the Workflow Engine.
All modifications go through: Draft → Review → Approval → Commit.
No direct vault writes outside of approved workflows.

Safety rules:
- Never delete Brain63 files automatically
- Never rewrite entire documents automatically
- Never modify files without workflow approval
- Always generate drafts, show diffs, require approval
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from backend.config import BRAIN63_VAULT_PATH

logger = logging.getLogger("silvia.brain_steward")

# ── Vault file mapping ─────────────────────────────────────────────────────

_PROJECT_FOLDERS: dict[str, str] = {
    "cyberdeck":   "02_Projects_Robotics_Hardware/Cyberdeck",
    "dronehive":   "02_Projects_Robotics_Hardware/DroneHive",
    "artoo":       "02_Projects_Robotics_Hardware/Artoo",
    "fpv_aircraft": "02_Projects_Robotics_Hardware/FPV_Aircraft",
    "koi":         "01_Projects_AI/KOI",
    "magi":        "01_Projects_AI/MAGI",
    "cmd-ctr":     "01_Projects_AI/CMD-CTR",
    "silvia":      "01_Projects_AI/CMD-CTR",
    "bespoketome": "01_Projects_AI/BespokeToMe",
    "projfreeguy": "01_Projects_AI/ProjFreeGuy",
    "brain63":     ".",
}

_DOC_FILES: dict[str, str] = {
    "decision":    "Decisions.md",
    "lesson":      "Lessons_Learned.md",
    "milestone":   "Status.md",
    "status":      "Status.md",
    "roadmap":     "Roadmap.md",
    "overview":    "Overview.md",
}

_EXPECTED_DOCS = {"Decisions.md", "Lessons_Learned.md", "Status.md", "Roadmap.md", "Overview.md"}


def _vault() -> Path:
    return Path(BRAIN63_VAULT_PATH)


def _resolve_project_folder(project: str) -> str:
    """Resolve a project name to its Brain63 folder path."""
    key = project.lower().replace(" ", "").replace("-", "").replace("_", "")
    for k, v in _PROJECT_FOLDERS.items():
        if k.replace("-", "").replace("_", "") == key:
            return v
    for folder in _vault().iterdir():
        if folder.is_dir():
            for sub in folder.iterdir():
                if sub.is_dir() and sub.name.lower().replace("-", "").replace("_", "") == key:
                    return str(sub.relative_to(_vault()))
    return ""


def _resolve_file(project: str, doc_type: str) -> Optional[Path]:
    """Resolve a project + doc type to a vault file path."""
    folder = _resolve_project_folder(project)
    if not folder:
        return None
    filename = _DOC_FILES.get(doc_type, "")
    if not filename:
        return None
    return _vault() / folder / filename


class BrainSteward:
    """Safe Brain63 maintenance through workflow-gated drafts."""

    # ── Draft Generation ────────────────────────────────────────────────────

    def draft_decision(self, project: str, title: str, reason: str = "",
                       status: str = "decided") -> dict[str, Any]:
        """Generate a draft decision entry for Brain63."""
        entry = f"\n## {title}\n\n"
        entry += f"- Decision: {title}\n"
        if reason:
            entry += f"- Why: {reason}\n"
        entry += f"- Status: {status}\n"

        target_file = _resolve_file(project, "decision")
        before = self._read_file(target_file) if target_file else ""

        return {
            "type": "decision",
            "project": project,
            "title": title,
            "entry": entry,
            "target_file": str(target_file.relative_to(_vault())) if target_file else f"{project}/Decisions.md",
            "before": before[-500:] if before else "(new file)",
            "after": (before + entry) if before else entry,
            "append": True,
        }

    def draft_lesson(self, project: str, title: str, detail: str = "") -> dict[str, Any]:
        """Generate a draft lesson entry."""
        entry = f"\n### {title}\n\n"
        if detail:
            entry += f"{detail}\n"
        else:
            entry += f"{title}\n"

        target_file = _resolve_file(project, "lesson")
        before = self._read_file(target_file) if target_file else ""

        return {
            "type": "lesson",
            "project": project,
            "title": title,
            "entry": entry,
            "target_file": str(target_file.relative_to(_vault())) if target_file else f"{project}/Lessons_Learned.md",
            "before": before[-500:] if before else "(new file)",
            "after": (before + entry) if before else entry,
            "append": True,
        }

    def draft_milestone(self, project: str, title: str, detail: str = "") -> dict[str, Any]:
        """Generate a draft milestone entry for Status.md."""
        date = time.strftime("%Y-%m-%d")
        entry = f"\n### {title} ({date})\n\n"
        if detail:
            entry += f"{detail}\n"

        target_file = _resolve_file(project, "milestone")
        before = self._read_file(target_file) if target_file else ""

        return {
            "type": "milestone",
            "project": project,
            "title": title,
            "entry": entry,
            "target_file": str(target_file.relative_to(_vault())) if target_file else f"{project}/Status.md",
            "before": before[-500:] if before else "(new file)",
            "after": (before + entry) if before else entry,
            "append": True,
        }

    def draft_status_update(self, project: str, field: str, old_value: str,
                            new_value: str) -> dict[str, Any]:
        """Generate a draft status field update."""
        target_file = _resolve_file(project, "status")
        before = self._read_file(target_file) if target_file else ""

        return {
            "type": "status_update",
            "project": project,
            "title": f"Update {field}: {old_value} → {new_value}",
            "entry": "",
            "target_file": str(target_file.relative_to(_vault())) if target_file else f"{project}/Status.md",
            "before": old_value,
            "after": new_value,
            "append": False,
            "field": field,
        }

    def draft_roadmap_update(self, project: str, change: str) -> dict[str, Any]:
        """Generate a draft roadmap update."""
        target_file = _resolve_file(project, "roadmap")
        before = self._read_file(target_file) if target_file else ""

        return {
            "type": "roadmap_update",
            "project": project,
            "title": f"Roadmap: {change}",
            "entry": f"\n{change}\n",
            "target_file": str(target_file.relative_to(_vault())) if target_file else f"{project}/Roadmap.md",
            "before": before[-500:] if before else "(new file)",
            "after": (before + f"\n{change}\n") if before else change,
            "append": True,
        }

    # ── Workflow Creation ───────────────────────────────────────────────────

    def create_draft_workflow(self, draft: dict, session_id: str = "") -> dict[str, Any]:
        """Create a workflow for a Brain63 draft."""
        from backend.app.services.workflow_engine import get_workflow_engine
        we = get_workflow_engine()

        doc_type_labels = {
            "decision": "Decision", "lesson": "Lesson",
            "milestone": "Milestone", "status_update": "Status Update",
            "roadmap_update": "Roadmap Update",
        }
        label = doc_type_labels.get(draft["type"], draft["type"].title())

        description_lines = [
            f"File: {draft['target_file']}",
            f"Action: {'Append' if draft.get('append') else 'Update'}",
        ]
        if draft.get("entry"):
            description_lines.append("")
            description_lines.append("Content:")
            description_lines.append(draft["entry"].strip())

        wf = we.create(
            category="brain63_update",
            title=f"Brain63 {label}: {draft['title'][:60]}",
            description="\n".join(description_lines),
            risk_level="moderate",
            changes={
                "type": draft["type"],
                "target_file": draft["target_file"],
                "entry": draft.get("entry", ""),
                "append": draft.get("append", True),
                "field": draft.get("field", ""),
            },
            before_state=draft.get("before", ""),
            after_state=draft.get("after", ""),
            tool_name="brain63_commit",
            tool_args=draft,
            affected=[draft["target_file"]],
            project=draft["project"],
            session_id=session_id,
            template="brain63_update",
        )
        return wf

    # ── Commit (only called after workflow approval) ────────────────────────

    def commit(self, draft: dict) -> dict[str, Any]:
        """Write an approved draft to the Brain63 vault.

        ONLY called after workflow approval. Never directly.
        """
        target_path = _vault() / draft["target_file"]

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if draft.get("append") and draft.get("entry"):
            existing = self._read_file(target_path)
            new_content = existing + draft["entry"]
            target_path.write_text(new_content, encoding="utf-8")
            logger.info("Brain63 commit: appended to %s", draft["target_file"])
        elif draft.get("field") and not draft.get("append"):
            logger.info("Brain63 commit: field update on %s (not implemented for safety)", draft["target_file"])
            return {"ok": True, "action": "field_update_skipped", "file": draft["target_file"]}
        else:
            logger.warning("Brain63 commit: unknown draft type, skipping")
            return {"ok": False, "error": "Unknown draft type"}

        return {"ok": True, "action": "appended", "file": draft["target_file"]}

    # ── Coverage & Health ───────────────────────────────────────────────────

    def get_health(self) -> dict[str, Any]:
        """Assess Brain63 documentation health."""
        vault = _vault()
        if not vault.exists():
            return {"available": False, "error": "Vault not found"}

        projects = []
        total_files = 0
        total_missing = 0
        project_dirs = []

        for category in vault.iterdir():
            if not category.is_dir() or category.name.startswith("."):
                continue
            for proj_dir in category.iterdir():
                if not proj_dir.is_dir() or proj_dir.name.startswith("."):
                    continue
                if any(skip in proj_dir.name for skip in ("Template", "template", "Index", "Log", "Review")):
                    continue
                project_dirs.append(proj_dir)

        for proj_dir in project_dirs:
            existing = {f.name for f in proj_dir.iterdir() if f.is_file() and f.suffix == ".md"}
            missing = _EXPECTED_DOCS - existing
            total_files += len(existing)
            total_missing += len(missing)
            coverage = (len(_EXPECTED_DOCS) - len(missing)) / max(len(_EXPECTED_DOCS), 1)
            projects.append({
                "name": proj_dir.name,
                "path": str(proj_dir.relative_to(vault)),
                "files": sorted(existing),
                "missing": sorted(missing),
                "coverage": round(coverage * 100),
            })

        projects.sort(key=lambda p: p["coverage"])
        overall = round((total_files / max(total_files + total_missing, 1)) * 100)

        return {
            "available": True,
            "projects": projects,
            "total_projects": len(projects),
            "total_files": total_files,
            "total_missing": total_missing,
            "overall_coverage": overall,
        }

    def get_coverage(self, project: str = "") -> dict[str, Any]:
        """Get documentation coverage for a specific project or all."""
        health = self.get_health()
        if not health.get("available"):
            return health
        if project:
            proj_lower = project.lower().replace("-", "").replace("_", "")
            for p in health["projects"]:
                if p["name"].lower().replace("-", "").replace("_", "") == proj_lower:
                    return {"project": p, "overall_coverage": health["overall_coverage"]}
            return {"error": f"Project '{project}' not found in Brain63"}
        return health

    def get_drafts(self) -> list[dict]:
        """Get all pending Brain63 workflows (drafts awaiting review)."""
        from backend.app.services.workflow_engine import get_workflow_engine
        we = get_workflow_engine()
        all_wfs = we.get_pending()
        return [wf for wf in all_wfs if wf.get("category") == "brain63_update"]

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _read_file(self, path: Optional[Path]) -> str:
        """Read a vault file. Returns empty string if not found."""
        if not path or not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""


# ── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[BrainSteward] = None


def get_brain_steward() -> BrainSteward:
    global _instance
    if _instance is None:
        _instance = BrainSteward()
    return _instance
