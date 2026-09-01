"""Memory Query Planner (Phase 3).

Turns a single user request / agent task into a small, bounded set of TARGETED
memory queries instead of firing the raw message at the store. Deterministic and
inspectable: every generated query keeps the reason it was generated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_STOPWORDS = {
    "what", "whats", "what's", "is", "the", "a", "an", "of", "for", "my", "me",
    "do", "i", "have", "are", "how", "give", "tell", "about", "on", "in", "to",
    "current", "status", "update", "please", "can", "you", "and", "with", "any",
}

# (trigger keywords, query suffix, reason code)
_EXPANSIONS = [
    (("status", "update", "progress", "where"), "current status", "status_lookup"),
    (("decision", "decided", "decide", "chose"), "key decisions", "decision_lookup"),
    (("deadline", "due", "when", "date"), "deadlines", "deadline_lookup"),
    (("task", "todo", "todos", "next", "open"), "open tasks", "task_lookup"),
    (("who", "people", "owner", "team"), "people involved", "people_lookup"),
    (("risk", "blocker", "blocked", "issue"), "risks and blockers", "risk_lookup"),
]


@dataclass
class PlannedQuery:
    query: str
    reason: str                 # machine reason code (why this query exists)
    provider: str = ""          # optional provider filter ("" = all)
    project: str = ""
    limit: int = 8
    meta: dict = field(default_factory=dict)


class MemoryQueryPlanner:
    def __init__(self, max_queries: int = 4) -> None:
        self.max_queries = max_queries

    @staticmethod
    def _subject(task: str) -> str:
        tokens = [t for t in re.findall(r"[A-Za-z0-9_]+", task)
                  if t.lower() not in _STOPWORDS and len(t) > 2]
        # Prefer capitalised terms (project/entity names) if present.
        caps = [t for t in tokens if t[:1].isupper()]
        chosen = caps or tokens
        return " ".join(chosen[:4]).strip()

    def plan(self, task: str, project: str = "", provider: str = "") -> list[PlannedQuery]:
        task = (task or "").strip()
        queries: list[PlannedQuery] = []
        if not task:
            return queries
        # 1) the primary intent, verbatim
        queries.append(PlannedQuery(query=task, reason="primary_intent",
                                    provider=provider, project=project))
        subject = self._subject(task)
        low = task.lower()
        # 2) targeted expansions the task hints at
        for triggers, suffix, reason in _EXPANSIONS:
            if any(t in low for t in triggers) and subject:
                queries.append(PlannedQuery(
                    query=f"{subject} {suffix}".strip(), reason=reason,
                    provider=provider, project=project))
            if len(queries) >= self.max_queries:
                break
        # de-dupe identical queries while preserving order/reasons
        seen, out = set(), []
        for q in queries:
            key = q.query.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(q)
        return out[: self.max_queries]
