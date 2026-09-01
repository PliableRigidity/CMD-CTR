"""Memory Write Extractor + write policy (Phase 3 / Phase 6 bridge).

After an interaction, identify candidate information that MAY deserve
persistence — separated by category — and classify each against the write
policy. It NEVER persists anything: it produces review-gated
``MemoryWriteProposal`` objects that flow into the existing approval workflow
(``KosineProvider.propose_write`` → ``kosine_suggestion`` → audited apply).

Nothing here auto-persists every message. Conservative, pattern-based, and
deterministic.
"""
from __future__ import annotations

import hashlib
import re

from backend.app.memory.provider import MemoryWriteProposal

# category -> (kosine object_type, requires_review, policy_class)
# policy_class: "safe" (could auto-apply if enabled), "review" (always human),
# "forbidden" is handled by the apply allowlist, not here.
_POLICY = {
    "explicit_fact": ("Observation", True, "safe"),
    "confirmed_decision": ("Decision", True, "safe"),
    "workflow_outcome": ("Status", True, "safe"),
    "observation": ("Observation", True, "safe"),
    "inferred_preference": ("Preference", True, "review"),
    "summary": ("Observation", True, "review"),
}

_PATTERNS = [
    (re.compile(r"\bremember that\b (.+)", re.I), "explicit_fact"),
    (re.compile(r"\bnote that\b (.+)", re.I), "explicit_fact"),
    (re.compile(r"\b(?:i|we) decided (?:to |that )?(.+)", re.I), "confirmed_decision"),
    (re.compile(r"\b(?:i|we) chose (?:to )?(.+)", re.I), "confirmed_decision"),
    (re.compile(r"\bi prefer (.+)", re.I), "inferred_preference"),
]


class MemoryWriteExtractor:
    def __init__(self, provider: str = "kosine") -> None:
        self.provider = provider

    @staticmethod
    def _idem(category: str, content: str) -> str:
        return hashlib.sha256(f"{category}:{content.strip().lower()}"
                              .encode("utf-8")).hexdigest()[:16]

    def extract(self, user_text: str = "", assistant_text: str = "",
                workflow_outcomes: list[dict] | None = None,
                source_event: str = "") -> list[MemoryWriteProposal]:
        proposals: list[MemoryWriteProposal] = []
        seen: set[str] = set()

        def add(category: str, title: str, description: str, confidence: float):
            obj_type, requires_review, _cls = _POLICY[category]
            idem = self._idem(category, title + description)
            if idem in seen:
                return
            seen.add(idem)
            proposals.append(MemoryWriteProposal(
                operation="create",
                object_type=obj_type,
                content={"type": obj_type, "title": title[:120],
                         "description": description[:1000]},
                source_event=source_event or category,
                confidence=confidence,
                requires_review=requires_review,
                idempotency_key=idem,
                provenance={"origin": "silvia_cognition", "category": category,
                            "provider": self.provider},
            ))

        text = (user_text or "").strip()
        for rx, category in _PATTERNS:
            for m in rx.finditer(text):
                captured = m.group(1).strip().rstrip(".")
                if len(captured) < 4:
                    continue
                title = captured[:60]
                add(category, title, captured, confidence=0.6)

        for wf in workflow_outcomes or []:
            status = str(wf.get("status", "")).lower()
            if status in ("completed", "failed"):
                add("workflow_outcome",
                    f"{wf.get('title', 'workflow')} {status}",
                    f"Workflow {wf.get('code', '')} {status}.", confidence=0.8)

        return proposals
