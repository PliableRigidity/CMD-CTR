# The Cognitive Graph

An interactive visualization of SILVIA's **observable system activity** while it
answers: memory queries, retrieved objects, relationship traversal, reranking,
context selection, agent/workflow/tool execution, decisions, proposed writes,
provider health, and simulations.

> **This is NOT the model's hidden chain-of-thought.** It shows system-level
> events (what was retrieved, activated, selected, executed) with short,
> inspectable reason codes — never the language model's private reasoning. The
> UI states this explicitly.

Backend: `backend/app/services/cognition/` + `/api/cognitive/*`.
Frontend: `frontend/src/pages/CognitiveGraphPage.jsx` (`/cognitive`).

## Event types

`session_started, intent_detected, memory_query_planned, memory_search_started,
memory_result_received, memory_activated, relation_traversed, memory_reranked,
context_selected, context_rejected, agent_started, agent_delegated,
workflow_started, workflow_step_started, workflow_step_completed,
workflow_blocked, tool_called, tool_completed, external_observation,
decision_proposed, decision_confirmed, contradiction_detected,
simulation_started, simulation_node_created, simulation_completed,
memory_write_proposed, memory_write_approved, memory_write_applied,
provider_degraded, provider_recovered, error.`

### Event schema (`CognitiveEvent.to_dict()`)

`event_id, event_type, timestamp, session_id, task_id, parent_event_id,
actor_type, actor_id, provider, status, activation, confidence, reason_code,
explanation (short, safe), duration_ms, error, nodes[], edges[], node_ids[],
edge_ids[], metadata`.

`reason_code`/`explanation` are compact and safe (e.g. `matched_current_project`,
"selected due to deadline relevance", "rejected because stale") — never a
free-text reasoning dump.

## Node & edge semantics

**Node types:** user_request, project, task, goal, decision, person, document,
memory, agent, workflow, tool, service, observation, error, query, simulation.

**Node states:** dormant, retrieved, active, selected, rejected, running,
completed, blocked, error, simulated, proposed, confirmed. State sets the ring
colour and the activation boost.

**Edge types:** retrieved_with, related_to, depends_on, contains, caused,
delegated_to, executed_by, produced, contradicted_by, derived_from,
simulated_from, selected_for_context, planned.

Each event carries a graph delta (`nodes`, `edges`) that the activation graph
upserts.

## Activation

Simple and inspectable, kept entirely SILVIA-side (three separate layers:
persistent KOSINE knowledge ≠ SILVIA working context ≠ this visual activation).

- A node's activation is a per-**state** boost (dormant 0.1 … selected 1.0) that
  **decays** with a ~45s half-life since it was last touched.
- Re-touching a node relights it (max of fresh boost and decayed prior).
- The frontend mirrors the same decay so nodes pulse then fade; brighter/larger
  = more active. Inactive nodes visibly decay; selected context stays lit.
- Activation is never written back to KOSINE.

## Simulation mode

Simulation nodes/edges are marked (`state="simulated"`, dashed ring, distinct
colour), carry a simulation context, and are **temporary** — they do not persist
to KOSINE and vanish on "clear view". Saving a simulated conclusion would require
an explicit user action routed through the normal write-review policy. What-if
graphs are explicitly not facts.

## Provenance & trust

Every memory-derived node preserves: provider, object id, source (`source_path`),
timestamps, retrieval score + rerank breakdown, activation, why it was retrieved
/ selected / rejected, and whether it entered model context. Confirmed vs
inferred vs simulated is shown in the inspector. Missing provenance is shown as
"—" — never fabricated.

## Failure display

`provider_degraded` shows a banner and the graph omits the unreachable provider
rather than inventing results; `provider_recovered` clears it.

## Limitations

- The graph reflects the SILVIA-side event stream; it is bounded (rolling buffer,
  ≤300 nodes) — old transient activity is evicted, not persisted.
- Reason codes are heuristic system tags, not a complete audit of every internal
  step.
- The on-demand `/api/cognitive/query` drives the retrieval pipeline; wiring the
  live conversation path to emit is incremental (flag-gated) and additive.
- **No model chain-of-thought is exposed or claimed to be exposed.**
