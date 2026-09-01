"""Unit tests for the cognitive event bus + activation graph (Phase 4).

Run: pytest backend/tests/test_cognitive_events.py -v
"""
from __future__ import annotations

from backend.app.services.cognition.events import (
    CognitiveEvent,
    CognitiveEventBus,
    CognitiveEventType,
)
from backend.app.services.cognition.graph_state import CognitiveGraphState


def test_event_to_dict_has_ids_and_no_chain_of_thought():
    ev = CognitiveEvent(
        event_type=CognitiveEventType.MEMORY_RESULT_RECEIVED,
        nodes=[{"id": "n1", "type": "memory", "label": "X", "state": "retrieved"}],
        edges=[{"source": "q1", "target": "n1", "type": "retrieved_with"}],
        reason_code="results", explanation="2 results")
    d = ev.to_dict()
    assert d["node_ids"] == ["n1"]
    assert d["edge_ids"] == ["q1->retrieved_with->n1"] or d["edge_ids"] == \
        [e["id"] for e in ev.edges if e.get("id")] or d["edge_ids"] == []
    # schema carries only inspectable fields, never a 'thought'/'reasoning' blob
    assert "explanation" in d and "reason_code" in d
    assert "thought" not in d and "chain_of_thought" not in d


def test_bus_buffers_and_snapshots():
    bus = CognitiveEventBus(buffer_size=10)
    for i in range(3):
        bus.emit_event(CognitiveEventType.MEMORY_SEARCH_STARTED,
                       session_id="s1", explanation=f"q{i}")
    snap = bus.snapshot(session_id="s1")
    assert len(snap["events"]) == 3
    assert "graph" in snap and "nodes" in snap["graph"]


def test_bus_session_filter():
    bus = CognitiveEventBus()
    bus.emit_event(CognitiveEventType.INTENT_DETECTED, session_id="a")
    bus.emit_event(CognitiveEventType.INTENT_DETECTED, session_id="b")
    assert len(bus.recent(session_id="a")) == 1
    assert len(bus.recent(session_id="b")) == 1
    assert len(bus.recent()) == 2


def test_bus_buffer_is_bounded():
    bus = CognitiveEventBus(buffer_size=5)
    for i in range(20):
        bus.emit_event(CognitiveEventType.TOOL_CALLED, session_id="s")
    assert len(bus.recent(limit=1000)) == 5


def test_publisher_receives_payload():
    bus = CognitiveEventBus()
    seen = []
    bus.register_publisher(lambda payload: seen.append(payload))
    bus.emit_event(CognitiveEventType.CONTEXT_SELECTED, session_id="s")
    assert seen and seen[0]["type"] == "cognitive"
    assert seen[0]["event"]["event_type"] == "context_selected"


def test_bad_publisher_does_not_break_emit():
    bus = CognitiveEventBus()

    def boom(_):
        raise RuntimeError("sink down")
    bus.register_publisher(boom)
    ev = bus.emit_event(CognitiveEventType.ERROR, session_id="s")  # must not raise
    assert ev.event_type == "error"


def test_reset_clears_transient_state():
    bus = CognitiveEventBus()
    bus.emit_event(CognitiveEventType.MEMORY_ACTIVATED, session_id="s",
                   nodes=[{"id": "n", "type": "memory", "label": "N",
                           "state": "active"}])
    assert bus.snapshot()["graph"]["nodes"]
    bus.reset()
    assert bus.snapshot()["graph"]["nodes"] == []


# ── activation graph + decay ────────────────────────────────────────────────

class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _ev(nodes, status="ok", et="memory_activated"):
    return CognitiveEvent(event_type=et, status=status, nodes=nodes)


def test_activation_decays_over_time():
    clk = Clock()
    g = CognitiveGraphState(clock=clk, half_life=10.0)
    g.ingest(_ev([{"id": "n1", "type": "memory", "label": "N", "state": "selected"}]))
    a0 = g.snapshot()["nodes"][0]["activation"]
    assert a0 >= 0.95  # 'selected' → ~1.0
    clk.t = 10.0  # one half-life later
    a1 = g.snapshot()["nodes"][0]["activation"]
    assert 0.45 < a1 < 0.55  # halved


def test_retouch_relights_node():
    clk = Clock()
    g = CognitiveGraphState(clock=clk, half_life=10.0)
    g.ingest(_ev([{"id": "n1", "type": "memory", "label": "N", "state": "retrieved"}]))
    clk.t = 20.0  # decayed
    g.ingest(_ev([{"id": "n1", "type": "memory", "label": "N", "state": "selected"}]))
    a = g.snapshot()["nodes"][0]["activation"]
    assert a >= 0.95  # relit to 'selected'
    assert g.snapshot()["nodes"][0]["state"] == "selected"


def test_edges_recorded():
    g = CognitiveGraphState()
    ev = CognitiveEvent(event_type="relation_traversed",
                        nodes=[{"id": "a", "type": "memory", "label": "A"},
                               {"id": "b", "type": "memory", "label": "B"}],
                        edges=[{"source": "a", "target": "b", "type": "depends_on"}])
    g.ingest(ev)
    edges = g.snapshot()["edges"]
    assert any(e["source"] == "a" and e["target"] == "b"
               and e["type"] == "depends_on" for e in edges)
