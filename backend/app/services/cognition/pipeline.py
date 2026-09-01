"""Cognition pipeline (Phase 3 orchestration).

Runs plan → search → rerank → expand → compose over the memory providers,
emitting the typed cognitive-event stream (with graph nodes/edges) that the
Cognitive Graph visualizes. Read-only and side-effect-free with respect to the
providers (no writes); it only reads memory and emits SILVIA-side activity.

Write extraction is available separately (``extract_proposals``) and produces
review-gated proposals — it never persists.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from backend.app.services.cognition.composer import ContextComposer
from backend.app.services.cognition.events import (
    CognitiveEventType as ET,
    get_cognitive_bus,
)
from backend.app.services.cognition.expansion import RelationshipExpander
from backend.app.services.cognition.extractor import MemoryWriteExtractor
from backend.app.services.cognition.query_planner import MemoryQueryPlanner
from backend.app.services.cognition.reranker import MemoryReranker

logger = logging.getLogger("silvia.cognition.pipeline")


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:8]


def _mem_node_id(entry) -> str:
    base = getattr(entry, "id", "") or _hash(getattr(entry, "title", ""))
    return f"mem:{entry.provider}:{base}"


class CognitionPipeline:
    def __init__(self, memory_manager=None, bus=None,
                 planner: Optional[MemoryQueryPlanner] = None) -> None:
        self._mm = memory_manager
        self._bus = bus
        self.planner = planner or MemoryQueryPlanner()
        self.composer = ContextComposer()

    def _mm_(self):
        if self._mm is None:
            from backend.app.services.memory_manager import get_memory_manager
            self._mm = get_memory_manager()
        return self._mm

    def _bus_(self):
        if self._bus is None:
            self._bus = get_cognitive_bus()
        return self._bus

    def run(self, task: str, session_id: str = "default", project: str = "",
            provider: str = "", per_query: int = 6) -> dict:
        mm, bus = self._mm_(), self._bus_()
        req_id = f"req:{session_id}:{_hash(task)}"
        req_node = {"id": req_id, "type": "user_request", "label": task[:80],
                    "state": "active"}
        bus.emit_event(ET.INTENT_DETECTED, session_id=session_id, task_id=req_id,
                       actor_type="user", nodes=[req_node],
                       reason_code="request_received",
                       explanation="new request entered the cognition pipeline")

        # 1) plan
        planned = self.planner.plan(task, project=project, provider=provider)
        q_nodes, q_edges = [], []
        for i, pq in enumerate(planned):
            qid = f"q:{session_id}:{i}"
            pq.meta["node_id"] = qid
            q_nodes.append({"id": qid, "type": "query", "label": pq.query[:60],
                            "state": "active", "meta": {"reason": pq.reason}})
            q_edges.append({"source": req_id, "target": qid, "type": "planned"})
        bus.emit_event(ET.MEMORY_QUERY_PLANNED, session_id=session_id,
                       task_id=req_id, parent_event_id=req_id,
                       nodes=[req_node, *q_nodes], edges=q_edges,
                       reason_code="query_plan",
                       explanation=f"planned {len(planned)} targeted queries",
                       metadata={"queries": [{"query": p.query, "reason": p.reason}
                                             for p in planned]})

        # 2) search each query
        all_entries: list = []
        for pq in planned:
            qid = pq.meta["node_id"]
            bus.emit_event(ET.MEMORY_SEARCH_STARTED, session_id=session_id,
                           task_id=req_id, reason_code=pq.reason,
                           explanation=f"searching: {pq.query}",
                           metadata={"query": pq.query})
            providers = [pq.provider] if pq.provider else None
            try:
                results = mm.search(pq.query, project=pq.project,
                                    providers=providers, limit=per_query) or []
            except Exception as e:
                logger.debug("pipeline search failed: %s", e)
                results = []
            nodes, edges = [], []
            for e in results:
                nid = _mem_node_id(e)
                nodes.append({"id": nid, "type": (e.type or "memory"),
                              "label": (e.title or "")[:60], "provider": e.provider,
                              "state": "retrieved",
                              "meta": {"source": e.source, "score": e.score}})
                edges.append({"source": qid, "target": nid,
                              "type": "retrieved_with"})
            bus.emit_event(ET.MEMORY_RESULT_RECEIVED, session_id=session_id,
                           task_id=req_id, nodes=nodes, edges=edges,
                           reason_code="results",
                           explanation=f"{len(results)} result(s) for '{pq.query}'",
                           metadata={"count": len(results), "query": pq.query})
            all_entries.extend(results)

        # 3) rerank
        reranked = MemoryReranker().rerank(all_entries, project=project)
        bus.emit_event(ET.MEMORY_RERANKED, session_id=session_id, task_id=req_id,
                       nodes=[{"id": _mem_node_id(e), "type": (e.type or "memory"),
                               "label": (e.title or "")[:60], "provider": e.provider,
                               "state": "active",
                               "meta": {"rerank": (e.metadata or {}).get("rerank")}}
                              for e in reranked[:12]],
                       reason_code="reranked",
                       explanation=f"reranked {len(reranked)} results by "
                                   "relevance/recency/reliability")

        # 4) bounded relationship expansion
        expander = RelationshipExpander(mm)
        rel_edges = expander.expand(reranked[:5])
        if rel_edges:
            nodes, edges = [], []
            for r in rel_edges:
                src = f"mem:expand:{_hash(r['source'])}"
                tgt = f"mem:expand:{_hash(r['target_label'])}"
                nodes.append({"id": tgt, "type": "memory",
                              "label": r["target_label"][:60], "state": "active"})
                edges.append({"source": src, "target": tgt,
                              "type": r["relation"]})
            bus.emit_event(ET.RELATION_TRAVERSED, session_id=session_id,
                           task_id=req_id, nodes=nodes, edges=edges,
                           reason_code="expanded",
                           explanation=f"traversed {len(rel_edges)} relationship(s)")

        # 5) compose bounded context; mark selected/rejected
        composed = self.composer.compose(reranked, task=task)
        sel_ids = {s["id"] for s in composed.selected}
        by_id = {getattr(e, "id", ""): e for e in reranked}
        sel_nodes, sel_edges = [], []
        for s in composed.selected:
            e = by_id.get(s["id"])
            if not e:
                continue
            nid = _mem_node_id(e)
            sel_nodes.append({"id": nid, "type": (e.type or "memory"),
                              "label": (e.title or "")[:60], "provider": e.provider,
                              "state": "selected"})
            sel_edges.append({"source": req_id, "target": nid,
                              "type": "selected_for_context"})
        if sel_nodes:
            bus.emit_event(ET.CONTEXT_SELECTED, session_id=session_id,
                           task_id=req_id, nodes=sel_nodes, edges=sel_edges,
                           status="ok", reason_code="context_selected",
                           explanation=f"selected {len(sel_nodes)} item(s) into "
                                       "model context")
        rej_nodes = []
        for r in composed.rejected:
            e = by_id.get(r["id"])
            if not e:
                continue
            rej_nodes.append({"id": _mem_node_id(e), "type": (e.type or "memory"),
                              "label": (e.title or "")[:60], "provider": e.provider,
                              "state": "rejected", "meta": {"reason": r["reason"]}})
        if rej_nodes:
            bus.emit_event(ET.CONTEXT_REJECTED, session_id=session_id,
                           task_id=req_id, nodes=rej_nodes, status="rejected",
                           reason_code="context_rejected",
                           explanation=f"rejected {len(rej_nodes)} item(s) "
                                       "(budget/relevance)")
        if composed.conflicts:
            bus.emit_event(ET.CONTRADICTION_DETECTED, session_id=session_id,
                           task_id=req_id, status="ok",
                           reason_code="conflict",
                           explanation=f"{len(composed.conflicts)} conflicting "
                                       "memory version(s) flagged — not merged",
                           metadata={"conflicts": composed.conflicts})

        return {
            "session_id": session_id,
            "task": task,
            "queries": [{"query": p.query, "reason": p.reason} for p in planned],
            "result_count": len(all_entries),
            "context": composed.text,
            "selected": composed.selected,
            "rejected": composed.rejected,
            "conflicts": composed.conflicts,
            "used_chars": composed.used_chars,
            "char_budget": composed.char_budget,
        }

    def extract_proposals(self, user_text: str = "", assistant_text: str = "",
                          workflow_outcomes: list[dict] | None = None,
                          session_id: str = "default") -> list[dict]:
        """Produce review-gated write proposals from an interaction (no writes).

        Emits ``memory_write_proposed`` events; the caller can route each proposal
        to ``provider.propose_write`` to create an approval workflow.
        """
        bus = self._bus_()
        proposals = MemoryWriteExtractor().extract(
            user_text=user_text, assistant_text=assistant_text,
            workflow_outcomes=workflow_outcomes,
            source_event=f"session:{session_id}")
        out = []
        for p in proposals:
            pid = f"proposal:{p.idempotency_key}"
            bus.emit_event(ET.MEMORY_WRITE_PROPOSED, session_id=session_id,
                           status="proposed", provider="kosine",
                           confidence=p.confidence,
                           nodes=[{"id": pid, "type": "decision"
                                   if p.object_type == "Decision" else "memory",
                                   "label": p.content.get("title", "")[:60],
                                   "state": "proposed"}],
                           reason_code=p.provenance.get("category", "proposal"),
                           explanation=f"proposed {p.operation} "
                                       f"({p.object_type}) — requires review")
            out.append({
                "operation": p.operation, "object_type": p.object_type,
                "content": p.content, "confidence": p.confidence,
                "requires_review": p.requires_review,
                "idempotency_key": p.idempotency_key, "provenance": p.provenance,
            })
        return out


_pipeline: Optional[CognitionPipeline] = None


def get_cognition_pipeline() -> CognitionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = CognitionPipeline()
    return _pipeline
