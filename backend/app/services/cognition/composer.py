"""Context Composer (Phase 3).

Turns the selected memories into a concise, budgeted context block for the
model — NOT a raw JSON dump. Keeps established facts, active projects, decisions,
uncertainties, conflicts, and provenance references, within a character budget.
Reports which entries were selected vs rejected (and why) so the decision is
inspectable and drives the Cognitive Graph's selected/rejected states.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ComposedContext:
    text: str = ""
    selected: list[dict] = field(default_factory=list)   # {id, provider, reason}
    rejected: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    char_budget: int = 0
    used_chars: int = 0


class ContextComposer:
    def __init__(self, char_budget: int = 1800, max_items: int = 8,
                 min_score: float = 0.15) -> None:
        self.char_budget = char_budget
        self.max_items = max_items
        self.min_score = min_score

    def compose(self, entries: list, task: str = "") -> ComposedContext:
        ctx = ComposedContext(char_budget=self.char_budget)
        lines: list[str] = []
        used = 0
        for e in entries:
            reason = None
            if e.score < self.min_score:
                reason = "below_relevance_threshold"
            elif len(ctx.selected) >= self.max_items:
                reason = "over_item_budget"
            snippet = f"- [{e.provider}] {e.title}: {(e.content or '')[:180]}"
            prov = e.source or e.provider
            if reason is None and used + len(snippet) > self.char_budget:
                reason = "over_char_budget"
            if reason:
                ctx.rejected.append({"id": e.id, "provider": e.provider,
                                     "reason": reason})
                continue
            lines.append(snippet + (f"  (source: {prov})" if prov else ""))
            used += len(snippet)
            ctx.selected.append({"id": e.id, "provider": e.provider,
                                 "reason": "selected", "source": prov})
            if (e.metadata or {}).get("conflict"):
                ctx.conflicts.append({
                    "id": e.id, "title": e.title,
                    "versions": e.metadata.get("conflicting_versions", []),
                })

        header = "ESTABLISHED CONTEXT (grounded; cite provenance, do not invent):"
        parts = [header, *lines]
        if ctx.conflicts:
            parts.append("CONFLICTS (do not resolve silently — flag to the user):")
            for c in ctx.conflicts:
                parts.append(f"- {c['title']}: conflicting versions across providers")
        if not lines:
            parts = ["No grounded context retrieved — say you don't have enough "
                     "information rather than guessing."]
        ctx.text = "\n".join(parts)
        ctx.used_chars = used
        return ctx
