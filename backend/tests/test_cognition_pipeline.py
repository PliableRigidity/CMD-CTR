"""Unit tests for the cognition services + pipeline (Phase 3).

Deterministic, no network. Verifies query planning, reranking breakdown,
bounded relationship expansion, budgeted context composition, write extraction,
and that the pipeline emits the cognitive-event stream + builds the graph.

Run: pytest backend/tests/test_cognition_pipeline.py -v
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.app.memory.provider import MemoryEntry
from backend.app.services.cognition.composer import ContextComposer
from backend.app.services.cognition.events import CognitiveEventBus
from backend.app.services.cognition.expansion import RelationshipExpander
from backend.app.services.cognition.extractor import MemoryWriteExtractor
from backend.app.services.cognition.pipeline import CognitionPipeline
from backend.app.services.cognition.query_planner import MemoryQueryPlanner
from backend.app.services.cognition.reranker import MemoryReranker


def entry(pid="kosine", title="Silvia", content="an ai os", score=0.8,
          type="project", date="", meta=None):
    return MemoryEntry(id=f"{pid}-{title}", provider=pid, type=type, title=title,
                       content=content, project=title if type == "project" else "",
                       date=date, source=f"{pid}://{title}", score=score,
                       metadata=meta or {})


class FakeMM:
    def __init__(self, entries, rels=None):
        self._entries = entries
        self._rels = rels if rels is not None else [
            {"relation": "depends_on", "object_id": "T1", "title": "Target One"}]

    def search(self, query, project="", providers=None, limit=20):
        return list(self._entries)[:limit]

    def relationships(self, entity="", limit=20):
        return list(self._rels)[:limit]


# ── planner ──────────────────────────────────────────────────────────────────

def test_planner_primary_plus_status_expansion():
    qs = MemoryQueryPlanner().plan("What is the status of Project Nebula?")
    reasons = [q.reason for q in qs]
    assert reasons[0] == "primary_intent"
    assert "status_lookup" in reasons
    assert len(qs) <= 4


def test_planner_bounded_and_deduped():
    qs = MemoryQueryPlanner(max_queries=3).plan("status decision deadline task risk")
    assert len(qs) <= 3


def test_planner_empty_task():
    assert MemoryQueryPlanner().plan("") == []


# ── reranker ─────────────────────────────────────────────────────────────────

def test_reranker_breakdown_and_order():
    fresh = entry(title="Fresh", score=0.7,
                  date=datetime.now(timezone.utc).isoformat(),
                  meta={"status": "active"})
    stale = entry(title="Stale", score=0.7, date="2000-01-01T00:00:00+00:00")
    out = MemoryReranker().rerank([stale, fresh], project="Fresh")
    assert out[0].title == "Fresh"  # recency + project + confirmed win
    assert "rerank" in out[0].metadata
    assert set(out[0].metadata["rerank"]) >= {"final", "relevance", "recency",
                                              "reliability"}


def test_reranker_contradiction_penalised():
    clean = entry(title="A", score=0.6)
    conflicted = entry(title="B", score=0.6, meta={"conflict": True})
    out = MemoryReranker().rerank([conflicted, clean])
    assert out[0].title == "A"


# ── expansion (bounds) ──────────────────────────────────────────────────────

def test_expansion_is_bounded():
    rels = [{"relation": "related_to", "object_id": f"O{i}", "title": f"O{i}"}
            for i in range(50)]
    exp = RelationshipExpander(FakeMM([], rels=rels), max_nodes=10)
    edges = exp.expand([entry(title="Seed")])
    assert len(edges) <= 10


def test_expansion_relation_filter():
    rels = [{"relation": "depends_on", "object_id": "A", "title": "A"},
            {"relation": "unrelated", "object_id": "B", "title": "B"}]
    exp = RelationshipExpander(FakeMM([], rels=rels),
                              allowed_relations={"depends_on"})
    edges = exp.expand([entry(title="Seed")])
    assert all(e["relation"] == "depends_on" for e in edges)


# ── composer (budget) ────────────────────────────────────────────────────────

def test_composer_respects_char_budget():
    big = [entry(title=f"T{i}", content="x" * 500, score=0.9) for i in range(20)]
    comp = ContextComposer(char_budget=600, max_items=8).compose(big)
    assert comp.used_chars <= 600
    assert comp.rejected  # some rejected for budget


def test_composer_marks_conflict():
    e = entry(title="Nebula", score=0.9,
              meta={"conflict": True,
                    "conflicting_versions": [{"provider": "brain63"}]})
    comp = ContextComposer().compose([e])
    assert comp.conflicts
    assert "CONFLICT" in comp.text.upper()


def test_composer_empty_says_insufficient():
    comp = ContextComposer().compose([])
    assert "don't have enough" in comp.text.lower()


# ── extractor ────────────────────────────────────────────────────────────────

def test_extractor_explicit_fact_and_decision():
    props = MemoryWriteExtractor().extract(
        user_text="Remember that the lab key is in drawer 3. "
                  "I decided to pause Project X.")
    ops = {p.object_type for p in props}
    assert "Observation" in ops and "Decision" in ops
    assert all(p.requires_review for p in props)      # nothing auto-applies
    assert all(p.idempotency_key for p in props)


def test_extractor_dedupes_idempotent():
    props = MemoryWriteExtractor().extract(
        user_text="Remember that X. Remember that X.")
    assert len(props) == 1


# ── pipeline end-to-end (with fakes) ─────────────────────────────────────────

def test_pipeline_runs_and_emits_events_and_graph():
    bus = CognitiveEventBus()
    mm = FakeMM([entry(title="Silvia", score=0.9),
                 entry(pid="brain63", title="DroneHive", score=0.6, type="project")])
    pipe = CognitionPipeline(memory_manager=mm, bus=bus)
    result = pipe.run("What is the status of Silvia?", session_id="s1")

    assert result["queries"][0]["reason"] == "primary_intent"
    assert result["context"]  # composed context produced
    types = {e["event_type"] for e in bus.recent(limit=100)}
    assert {"intent_detected", "memory_query_planned", "memory_result_received",
            "memory_reranked", "context_selected"} <= types
    graph = bus.snapshot(session_id="s1")["graph"]
    assert graph["nodes"] and graph["edges"]
    # request node present and lit
    assert any(n["type"] == "user_request" for n in graph["nodes"])


def test_pipeline_extract_proposals_emits_and_returns():
    bus = CognitiveEventBus()
    pipe = CognitionPipeline(memory_manager=FakeMM([]), bus=bus)
    props = pipe.extract_proposals(user_text="I decided to ship on Friday.",
                                   session_id="s1")
    assert props and props[0]["object_type"] == "Decision"
    assert any(e["event_type"] == "memory_write_proposed"
               for e in bus.recent(limit=50))
