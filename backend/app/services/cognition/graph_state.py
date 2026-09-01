"""Cognitive activation graph — the SILVIA-side visual/working state (Phase 4/5).

Maintains the nodes and edges the Cognitive Graph renders, each with an
*activation* level that DECAYS over time. This is purely SILVIA-side, transient
visual/working state — it is NEVER written back to KOSINE. Three layers stay
separate (per the spec):

    persistent KOSINE knowledge  ≠  SILVIA working context  ≠  this visual activation

Activation is simple and inspectable: a node's activation is a per-state boost
that decays with a fixed half-life since it was last touched. No hidden model
state, no chain-of-thought.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

# Boost applied when a node enters a given state (0..1).
STATE_ACTIVATION = {
    "dormant": 0.10,
    "retrieved": 0.50,
    "active": 0.85,
    "selected": 1.00,
    "rejected": 0.20,
    "running": 0.90,
    "completed": 0.70,
    "blocked": 0.60,
    "error": 0.60,
    "simulated": 0.50,
    "proposed": 0.50,
    "confirmed": 0.80,
}

_HALF_LIFE_SECONDS = 45.0   # activation halves every ~45s of inactivity
_MAX_NODES = 300            # bounded — evict least-activated beyond this
_MAX_EDGES = 600


class CognitiveGraphState:
    def __init__(self, clock: Optional[Callable[[], float]] = None,
                 half_life: float = _HALF_LIFE_SECONDS) -> None:
        self._clock = clock or time.monotonic
        self._half_life = half_life
        self._nodes: dict[str, dict] = {}
        self._edges: dict[str, dict] = {}

    # ── ingest ────────────────────────────────────────────────────────────

    def ingest(self, event) -> None:
        now = self._clock()
        for spec in getattr(event, "nodes", []) or []:
            self._upsert_node(spec, now, event)
        for spec in getattr(event, "edges", []) or []:
            self._upsert_edge(spec, now)
        self._evict()

    def _upsert_node(self, spec: dict, now: float, event) -> None:
        nid = spec.get("id")
        if not nid:
            return
        state = spec.get("state") or _default_state(event)
        boost = STATE_ACTIVATION.get(state, 0.3)
        existing = self._nodes.get(nid)
        # New activation is the max of the fresh boost and the decayed prior —
        # re-touching a node keeps it lit rather than resetting it downward.
        prior = self._current_activation(existing, now) if existing else 0.0
        node = existing or {
            "id": nid, "type": spec.get("type", "memory"),
            "label": spec.get("label", nid), "provider": spec.get("provider", ""),
            "meta": {},
        }
        node["type"] = spec.get("type", node.get("type", "memory"))
        node["label"] = spec.get("label", node.get("label", nid))
        node["provider"] = spec.get("provider", node.get("provider", ""))
        node["state"] = state
        node["base_activation"] = max(boost, prior)
        node["last_ts"] = now
        if spec.get("meta"):
            node["meta"] = {**node.get("meta", {}), **spec["meta"]}
        self._nodes[nid] = node

    def _upsert_edge(self, spec: dict, now: float) -> None:
        src, tgt = spec.get("source"), spec.get("target")
        if not src or not tgt:
            return
        eid = spec.get("id") or f"{src}->{spec.get('type','related')}->{tgt}"
        self._edges[eid] = {
            "id": eid, "source": src, "target": tgt,
            "type": spec.get("type", "related_to"), "last_ts": now,
        }

    # ── decay + snapshot ──────────────────────────────────────────────────

    def _current_activation(self, node: Optional[dict], now: float) -> float:
        if not node:
            return 0.0
        elapsed = max(0.0, now - node.get("last_ts", now))
        decay = 0.5 ** (elapsed / self._half_life)
        return round(node.get("base_activation", 0.0) * decay, 4)

    def snapshot(self) -> dict:
        now = self._clock()
        nodes = []
        for n in self._nodes.values():
            nodes.append({
                "id": n["id"], "type": n["type"], "label": n["label"],
                "provider": n.get("provider", ""), "state": n.get("state", "dormant"),
                "activation": self._current_activation(n, now),
                "meta": n.get("meta", {}),
            })
        edges = [
            {"id": e["id"], "source": e["source"], "target": e["target"],
             "type": e["type"]}
            for e in self._edges.values()
        ]
        return {"nodes": nodes, "edges": edges}

    def _evict(self) -> None:
        if len(self._nodes) > _MAX_NODES:
            now = self._clock()
            ranked = sorted(self._nodes.values(),
                            key=lambda n: self._current_activation(n, now))
            for n in ranked[: len(self._nodes) - _MAX_NODES]:
                self._nodes.pop(n["id"], None)
            live = set(self._nodes)
            self._edges = {k: e for k, e in self._edges.items()
                           if e["source"] in live and e["target"] in live}
        if len(self._edges) > _MAX_EDGES:
            ranked = sorted(self._edges.values(), key=lambda e: e["last_ts"])
            for e in ranked[: len(self._edges) - _MAX_EDGES]:
                self._edges.pop(e["id"], None)


def _default_state(event) -> str:
    """Fallback node state when an event's node spec doesn't set one."""
    et = getattr(event, "event_type", "")
    status = getattr(event, "status", "ok")
    if status in ("rejected", "blocked", "error", "simulated", "proposed",
                  "confirmed", "completed"):
        return {"completed": "completed"}.get(status, status)
    mapping = {
        "memory_result_received": "retrieved",
        "memory_activated": "active",
        "context_selected": "selected",
        "context_rejected": "rejected",
        "agent_started": "running",
        "tool_called": "running",
        "workflow_step_started": "running",
        "decision_confirmed": "confirmed",
        "decision_proposed": "proposed",
        "simulation_node_created": "simulated",
    }
    return mapping.get(et, "active")
