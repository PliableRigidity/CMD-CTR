"""Generate a focused repair prompt for a coding agent (Claude/Codex).

Reads the latest failure report (agent/reports/latest_failure_report.md)
plus the latest raw run log (agent/logs/run_*.json, for structured detail)
and writes agent/reports/latest_repair_prompt.md.

Usage:
    python agent/generate_repair_prompt.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
REPORT_DIR = AGENT_DIR / "reports"
LOG_DIR = AGENT_DIR / "logs"
REPORT_PATH = REPORT_DIR / "latest_failure_report.md"
PROMPT_PATH = REPORT_DIR / "latest_repair_prompt.md"

# Where to start looking, per failure category. Hints, not orders — the
# repair agent must inspect before editing.
CATEGORY_FILE_HINTS = {
    "obsidian_grounding": [
        "backend/app/services/conversation_service.py",
        "backend/app/services/brain63_service.py",
        "GROUNDING_POLICY.md",
    ],
    "hallucination": [
        "backend/app/services/conversation_service.py",
        "backend/app/services/brain63_service.py",
        "backend/tests/test_anti_hallucination.py",
        "GROUNDING_POLICY.md",
    ],
    "latency": [
        "backend/config.py",
        "backend/app/services/conversation_service.py",
    ],
    "voice_pipeline": [
        "backend/app/api/voice.py",
        "backend/app/voice/",
        "backend/voice/",
    ],
    "tool_usage": [
        "backend/app/services/conversation_service.py",
    ],
}

RULES = """\
## Hard rules — do not violate

1. Fix ONLY the failures listed below. Do not refactor unrelated code.
2. Inspect the relevant files FIRST; understand the existing flow before editing.
3. Make the smallest safe change that fixes each failure.
4. Do NOT rewrite SILVIA's architecture.
5. Do NOT modify the Obsidian vault (BRAIN63_VAULT_PATH) content — it is read-only.
6. Do NOT delete or disable working features to make tests pass.
7. Do NOT hide, fake, or skip failures; do not weaken test cases to force passes.
8. After fixing, rerun: `python agent/run_tests.py` and confirm the specific
   failing tests now pass without breaking previously passing ones.
9. Log every change in CHANGELOG_AGENT.md (what, why, files touched).
10. If a failure cannot be fixed safely, document it in BLOCKERS.md instead of
    forcing a change.
"""


def latest_run_log() -> dict | None:
    runs = sorted(LOG_DIR.glob("run_*.json"))
    if not runs:
        return None
    try:
        return json.loads(runs[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_prompt() -> str:
    if not REPORT_PATH.exists():
        raise FileNotFoundError(
            f"{REPORT_PATH} not found — run `python agent/run_tests.py` first."
        )
    report = REPORT_PATH.read_text(encoding="utf-8")

    run = latest_run_log()
    failed_categories: set[str] = set()
    failed_count = 0
    if run:
        for r in run.get("results", []):
            if not r["evaluation"]["passed"]:
                failed_count += 1
                failed_categories.add(r["case"].get("category", "unknown"))

    lines = [
        "# SILVIA Repair Prompt",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "You are a coding agent working on the SILVIA repository "
        "(CMD-CTR). Automated QA found failures. Your job is to repair them "
        "with the smallest safe changes. Read AGENT.md and "
        "GROUNDING_POLICY.md before touching code.",
        "",
        RULES,
        "## Where to start looking",
        "",
    ]
    if failed_categories:
        for cat in sorted(failed_categories):
            hints = CATEGORY_FILE_HINTS.get(cat, [])
            lines.append(f"- **{cat}**: " + (", ".join(f"`{h}`" for h in hints)
                                             or "inspect the chat path"))
    else:
        lines.append("- (no structured run log found — rely on the report below)")

    lines += [
        "",
        f"## Failure report ({failed_count} failing test(s))",
        "",
        "---",
        "",
        report.rstrip(),
        "",
        "---",
        "",
        "## Definition of done for this repair",
        "",
        "1. Each listed failing test passes on rerun (`python agent/run_tests.py`).",
        "2. No previously passing test now fails.",
        "3. CHANGELOG_AGENT.md updated with an entry for this repair.",
        "4. Unfixable items documented in BLOCKERS.md with a reason.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    try:
        prompt = build_prompt()
    except FileNotFoundError as e:
        print(f"[error] {e}")
        return 1
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_PATH.write_text(prompt, encoding="utf-8")
    print(f"Repair prompt written to: {PROMPT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
