# SILVIA Roadmap

---

## Completed Phases

### Phase 1 — Core Assistant
- FastAPI backend skeleton
- Ollama integration (gemma3:4b)
- Basic text conversation loop
- WebSocket event streaming
- React frontend scaffold

### Phase 2 — Multi-Brain Debate Engine
- Three-brain panel: SARASWATI (analysis), LAKSHMI (resources), DURGA (ethics)
- Voting/consensus mechanism
- CHAIR moderator role
- Decision recording with rationale

### Phase 3 — Tool Planning Layer
- Planner (qwen2.5:3b) dispatches tools from natural language
- 50+ tools registered: time, weather, web search, node management, hardware
- Regex fallback when Ollama is unavailable
- Few-shot examples for reliable routing

### Phase 4 — Voice Pipeline
- Wake word detection ("Hey SILVIA") — custom ONNX model
- Silero VAD integration
- Speaches (OpenAI-compatible) STT/TTS support
- Local fallback: faster-whisper STT + Piper TTS
- Voice loop with end-of-speech detection

### Phase 5A — Node Protocol Foundation
- `silvia-agent` REST protocol defined
- Node registry (SQLite)
- Node types: drone, robot, server, workstation, sbc, esp32
- Telemetry fields: CPU, RAM, disk, temperature, battery, altitude

### Phase 5C / 6A / 6B — Watch Officer, Personal Ops, Semantic Memory
- Watch Officer alert engine with rule evaluation
- Alert severity levels (info/warning/critical)
- Tasks, reminders, calendar integration
- Semantic memory: conversation embedding + search (sentence-transformers)
- Morning briefing, evening review, daily focus, weekly review

### Phase 6C / 7A / 7B / 7C — Hermes Engine + Robotics
- Hermes multi-step task execution engine
- Node command dispatch (arm, disarm, land, emergency_stop, reboot)
- Destructive command confirmation flow
- Drone/robot telemetry (mission state, altitude, battery)
- `send_node_command` and `send_bulk_command` tools

### Phase 8–9 — Proactive Intelligence Layer
- Forgotten items detection (stale projects, overdue tasks)
- Project health reports
- Daily focus ranking
- Weekly review synthesis
- Proactive alerts pushed via WebSocket

### Phase 10 — Universal Node Capability Layer
- `node_services` and `service_capabilities` tables
- Service presets: nas, media-player, robot, esp32, drone, web-server
- `execute_capability` tool — routes to node+service automatically
- Capability namespaces: media, motion, camera, system, sensor, battery, gpio, navigation, audio
- 10 new API endpoints
- Service panel in Infrastructure UI

### Phase 12A — Hardware Ops Center
- Four new SQLite tables: `hw_inventory`, `hw_projects`, `hw_project_parts`, `hw_orders`
- 21 REST API endpoints
- 18 Hardware Assistant chat tools
- Hardware Board page in frontend (inventory, projects, orders panels)
- `/hardware` route

### Phase 12B — Project Intelligence
- Build readiness calculation per project
- Missing parts analysis
- Order recommendations with urgency ranking
- Project priority ranking
- 6 intelligence API endpoints
- 6 new chat tools
- Intelligence section in Hardware Board UI

### Phase 12C — BOM Import
- CSV BOM import (KiCad and generic formats)
- Auto-column detection
- Project linking during import
- Import history tracking
- Imports panel in UI

### Phase 12D — Hardware Assistant Routing Fix
- Complete routing audit
- Fixed: "show projects" was routed to inventory search
- Fixed: "can I make X" not extracting project name correctly
- Fixed: requirements queries falling to help message
- Routing priority order documented and enforced

### Phase 12E — Procurement Engine
- `reorder_threshold` on inventory parts
- `expected_delivery` and `date_received` on orders
- `in_transit` order status
- `receive_order()` — marks delivered, credits inventory
- `get_low_stock()` — parts below threshold
- `get_after_delivery_readiness()` — forecast buildability after orders arrive
- Procurement Dashboard section in UI: active orders, deliveries, low stock, forecast
- 4 new API endpoints
- 6 new Hardware Assistant commands

### Phase 12G — Productivity Integrations
- `ProductivityProvider` ABC + `GoogleProvider` implementation (Gmail, Calendar)
- `AuthService` — OAuth token storage in `oauth_tokens` table (SQLite)
- OAuth2 PKCE loopback flow via SILVIA FastAPI backend (`/api/productivity/auth/callback`)
- 15 REST endpoints under `/api/productivity/` (auth, gmail, calendar)
- 10 planner tools: `connect_google`, `list_emails`, `search_emails`, `draft_email`, `send_email` (confirm), `list_gcal_events`, `create_gcal_event`, `delete_gcal_event` (confirm), `show_productivity_status`
- Conversation service handlers + `_pending_email` / `_pending_gcal_delete` confirmation states
- Renderers: `_render_emails()`, `_render_gcal_events()`
- ~35 planner regex patterns + few-shots covering Gmail/Calendar flows
- `ProductivitySection` in MissionPanel: Google status, today's events, unread email count/subjects
- Gmail primary-category default filter; per-category routing (promotions/social/updates)
- Security: send_email and delete_gcal_event always require explicit user confirmation

### Phase 13C+13D — Observability Ledger + Integration Hardening
- `execution_ledger.py` — append-only SQLite ledger (3 tables: execution_log, planner_log, failure_log); thread-safe singleton via `get_ledger()`
- `system_health.py` — per-capability and per-node success rates, overall health snapshot
- `observability.py` API — 6 endpoints: `/api/observability/recent`, `/failures`, `/planner`, `/health`, `/node/{node}`, `/capability/{cap}`
- Every execution path logs to ledger: CapabilityExecutor (4 paths), FleetManager (dry_run + actual)
- `_intent` propagation: user query flows from `_execute_plan` → `_current_intent` → ledger entries
- Planner tools: `show_recent_actions`, `show_failures`, `show_planner_trace`, `show_capability_health`, `explain_last_action`
- Regex patterns: "what did you do", "show failures", "why did you do that", "show actions on pi5"
- 13 observability few-shots added to planner
- Conversation renderers: `_render_execution_log`, `_render_failure_log`, `_render_planner_trace`, `_render_capability_health`
- `explain_last_action`: shows triggering intent, capability, node, status, duration, result for last ledger entry
- `RecentActivity` component in InfrastructurePanel: last 10 executions, status-colored icons, 15s refresh
- Observability API functions in `api.js`: fetchRecentActions, fetchFailures, fetchPlannerTrace, fetchCapabilityHealth

### Phase 14B — Knowledge Graph Board *(shipped 2026-06-17)*
- Fixed routing bug: "show knowledge graph" previously fell through to LLM which misrouted to `get_node_telemetry`; now caught by `_KG_GENERAL_RE`/`_KG_PROJECT_RE` BEFORE node/telemetry patterns in `_regex_fallback()`
- `show_knowledge_graph` planner tool: returns entity count, relationship count, type breakdown, most-connected nodes, and /knowledge page link; auto-rebuilds if empty
- `rebuild_from_data_sources()` function: idempotent population from hw_projects + hw_inventory + hw_project_parts + hw_orders + nodes + node_services + tasks + projects (Brain63 keys); 7 entity types; uses/requires/hosted_on/ordered_by/tracks/related_to edge types
- `GET /api/knowledge/graph` updated to return `{nodes: [{id, label, type}], edges: [{source, target, type}]}` format for canvas visualization
- New endpoints: `GET /api/knowledge/graph/project/{project}` (project-focused BFS subgraph), `POST /api/knowledge/rebuild` (populate from all data sources)
- `KnowledgeGraphPage.jsx` — full-page canvas force-directed graph with: Coulomb repulsion + Hooke spring + velocity damping physics; node type color coding (9 types); edge type colors + arrowheads; zoom (scroll wheel), pan (drag background), node drag, click to select; NodeDetail sidebar with incoming/outgoing edges; search filter; type toggle filter; project focus (loads subgraph); entity count stats
- `ForceGraph` canvas component: `requestAnimationFrame` animation loop, canvas 2D rendering, BFS-aware subgraph display, grid background, node labels (always for project/node, on hover/select for others), glow ring for selected node
- `/knowledge` route added to App.jsx; "Graph" button added to TopBar.jsx (opens in new tab)
- `fetchKnowledgeGraph()`, `fetchProjectGraph(project)`, `rebuildKnowledgeGraph()` added to api.js
- 4 KG few-shots added to planner

### Phase 14A — Engineering Knowledge Graph & Project Intelligence *(shipped 2026-06-17)*
- `knowledge_graph.py` — SQLite entity-relationship store (`kg_entities` + `kg_relationships` tables); singleton `get_graph()`; BFS subgraph traversal; entity types: project/component/node/service/task/document/order/capability/roadmap; relationship types: uses/depends_on/hosted_on/blocked_by/related_to/requires/contains/implements/ordered_by/assigned_to/tracks/supports
- `project_intelligence.py` — multi-source aggregator: HardwareService (readiness, missing parts, orders), ProjectService (brain63_key, tags), TaskService (direct SQL project filter), Brain63Service (status context), KnowledgeGraph (dependency edges); `get_briefing()`, `get_blockers()`, `get_readiness()`, `get_dependencies()`, `get_projects_using()`, `get_blocked_projects()`, `get_startable_projects()`
- `project_intelligence.py` API — 11 endpoints across two routers: `/api/projects/intelligence/{project}`, `/api/projects/blockers/{project}`, `/api/projects/readiness/{project}`, `/api/projects/dependencies/{project}`, `/api/projects/using/{component}`, `/api/projects/blocked`, `/api/projects/startable`; knowledge graph: `/api/knowledge/entities`, `/api/knowledge/relationships`, `/api/knowledge/graph`, `POST /api/knowledge/relationship`
- Planner tools: `project_briefing`, `project_blockers`, `project_readiness`, `project_dependencies`, `projects_using`, `blocked_projects`, `startable_projects`
- 7 regex patterns: briefing phrases, blockers, readiness, dependencies, cross-project component lookup, blocked/startable project sweeps
- 13 project intelligence few-shots added to planner
- Conversation handlers + 3 renderers: `_render_project_briefing` (readiness bar █/░), `_render_project_blockers`, `_render_projects_list`
- `ProjectIntelligenceSection` component in `ProjectsPanel.jsx`: readiness bar (10 segments), missing parts, blockers count, open tasks, Brain63 context (140 chars), recommended action; fetches on project select
- Blocked/Ready filter buttons in Projects panel: toggle to fetch and show `pi-quick-list` from `/api/projects/blocked` and `/api/projects/startable`
- API functions in `api.js`: `fetchProjectBriefing`, `fetchProjectBlockers`, `fetchProjectReadiness`, `fetchProjectsUsing`, `fetchBlockedProjects`, `fetchStartableProjects`, `fetchKnowledgeEntities`, `addKnowledgeRelationship`
- 20+ CSS classes for project intelligence UI: `.pi-section`, `.pi-bar-track`, `.pi-seg`, `.pi-filter-bar`, `.pi-filter-btn`, `.pi-quick-list`, `.pi-quick-row`, etc.

### Phase 13B — Fleet Management
- `fleet_manager.py` — FleetManager service: health scoring, node grouping (type/tag/service), filter engine, bulk capability execution with dry-run
- `fleet.py` API — 6 endpoints: `GET /api/fleet/status`, `/fleet/groups`, `/fleet/offline`, `/fleet/unhealthy`, `/fleet/nodes`, `POST /api/fleet/action`
- Health score: 100 − penalties for offline/critical/warning nodes; per-node health classification from Watch Officer alerts + metric thresholds
- Planner tools: `fleet_status`, `show_fleet_offline`, `show_fleet_unhealthy`, `show_fleet_groups`, `fleet_action`
- 25+ NL regex patterns + 15 few-shots: "show fleet status", "show offline nodes", "restart docker on all raspberry pis"
- Confirmation flow: fleet_action shows dry-run preview + target list before executing
- `FleetDashboard` component: health score bar, grade (A–F), online/offline/degraded/alert counters
- Fleet API functions in `api.js`: fetchFleetStatus, fetchFleetOffline, fetchFleetGroups, fleetAction, etc.

### Phase 13A — Capability Runtime 2.0
- `capability_resolver.py` — resolution layer: node lookup → service registry → best-match CapabilityMatch
- `capability_executor.py` — transport-agnostic executor: HTTP, SSH, local, MQTT adapters
- `executor` and `command` columns added to `service_capabilities` schema (idempotent migration)
- `ENABLE_CAPABILITY_EXECUTION` env var — set `false` for simulation mode (no real commands sent)
- Simulation mode resolves the capability fully and previews the command without dispatching
- `POST /api/capabilities/run` — UI-safe execution endpoint (always returns 200 with ok/summary/error)
- Regex patterns: "what can X do", "show capabilities on X", "restart docker on pi5", media/camera/motion/system namespaces
- Planner few-shots: "show capabilities on X", "what can X do", "restart docker/samba on X"
- Execute buttons per capability in InfrastructurePanel services view
- Inline result display (5s auto-clear) with success/error states

---

## Paused / Deferred

### Phase 12F — Vision-Assisted Inventory *(paused 2026-06-16)*
Reason: Open-weights vision models (LLaVA, Gemma 4) hallucinate component names and copy prompt
placeholder text into detections. The signal quality is too low for reliable inventory tracking.
BOM imports, order parsing, and readiness analysis deliver far more value.

Code is preserved behind `ENABLE_VISION_INVENTORY=false` in `config.py`.
Set it to `true` to re-enable — no UI or routing changes needed.

Possible future direction: **Workbench Awareness** — OCR-based component label reading or a
fine-tuned model trained specifically on maker component imagery, rather than general-purpose VLMs.

---

## Planned Phases

### Phase 14 — Fleet Commands
**Goal:** Command all nodes of a type simultaneously

- `send_bulk_command(type, command, payload)` in `node_tool.py`
- Concurrent dispatch via `asyncio.gather`
- Aggregate result: how many succeeded / failed / per-node status
- Planner patterns: "land all drones", "disarm all robots", "emergency stop all drones"
- Destructive bulk commands require confirmation
- Bulk command renderer in conversation_service

### Phase 15 — External Notifications
**Goal:** Alert you when critical events happen, even if you're away from the screen

- `notification_service.py` — webhook + email dispatch
- Discord embed format (color-coded by severity)
- Slack attachment block format
- SMTP email via `smtplib` (stdlib, no extra deps)
- Debounce: same rule + node → no repeat notification within 30 min
- Config: `NOTIFICATION_WEBHOOK_URL`, `NOTIFICATION_WEBHOOK_FORMAT`, `NOTIFICATION_MIN_SEVERITY`
- Triggered from Watch Officer when severity meets minimum threshold
- No frontend changes needed

### Phase 16 — Authentication
**Goal:** Secure SILVIA when exposed beyond localhost

- `AuthMiddleware` in `backend/app/core/auth_middleware.py`
- Check `X-API-Key` header or `Authorization: Bearer <key>`
- `API_KEY` env var empty → auth disabled (localhost always passes)
- Localhost bypass: `127.0.0.1` and `::1` never require auth
- WebSocket: `?api_key=<key>` query param
- Exempt: `/health`, `/docs`, `/openapi.json`
- Frontend: API key stored in `localStorage` as `silvia_api_key`
- First-run 401 → prompt modal to enter key

### Phase 17 — Scheduled Tasks (Hermes Automation)
**Goal:** SILVIA executes recurring tasks autonomously

- `scheduled_tasks` SQLite table
- `scheduled_task_service.py` CRUD + `get_due()` + `mark_ran()`
- Background loop in `application.py` — checks every 60s, runs due tasks via Hermes
- `GET/POST/PUT/DELETE /api/scheduled-tasks` REST API
- Chat commands: `schedule task: check node health every 60 minutes`, `show scheduled tasks`, `disable scheduled task X`, `delete scheduled task X`
- Mission Panel section: list, enable/disable toggle, add/edit inline form
- Emits Watch Officer alert if task result indicates a problem

### Phase 18 — Mobile Companion
**Goal:** SILVIA on your phone for monitoring and quick commands

- Progressive Web App (PWA) frontend
- Push notifications for critical Watch Officer alerts
- Voice input on mobile
- Condensed view: summary bar, alerts, quick commands

---

## Future Vision

- **SILVIA on a drone** — silvia-agent with PX4/ArduPilot integration, autonomous mission planning
- **Distributed SILVIA** — multiple SILVIA instances sharing state across locations
- **Hardware vision V2** — fine-tuned model for maker components, package label reading
- **PCB analysis** — detect component placement from PCB photos, cross-reference with BOM
- **Smart purchasing** — price comparison across Mouser, DigiKey, AliExpress for missing parts
- **Brain63 write-back** — SILVIA creates Obsidian notes from conversations (with permission)
- **LLM upgrade path** — swap any model in `config.py` as better local models are released

---

## Version History

| Date | Milestone |
|---|---|
| 2026-04-10 | Phase 1–4 shipped: core assistant, voice, multi-brain |
| 2026-06-08 | Phase 5–10 shipped: infrastructure, Watch Officer, capabilities |
| 2026-06-12 | Agency upgrade: capability map, self-reflection routing |
| 2026-06-14 | Phase 9: proactive intelligence layer |
| 2026-06-15 | Phase 10: universal node capability layer |
| 2026-06-15 | Phase 12A–12E: Hardware Board, procurement engine |
| 2026-06-16 | Phase 12F: Vision-Assisted Inventory — paused (ENABLE_VISION_INVENTORY=false) |
| 2026-06-16 | Phase 12G: Productivity Integrations — Gmail, Google Calendar, Contacts, OAuth2 |
| 2026-06-16 | Phase 13A: Capability Runtime 2.0 — execution layer, resolver, UI execute buttons |
| 2026-06-16 | Phase 13C+13D: Observability Ledger — execution_ledger, system_health, observability API, RecentActivity UI |
| 2026-06-16 | Phase 13B: Fleet Management — health scoring, groups, bulk capability execution, FleetDashboard |
| 2026-06-17 | Phase 14A: Engineering Knowledge Graph & Project Intelligence — KnowledgeGraph, ProjectIntelligence, 11 API endpoints, 7 planner tools, ProjectIntelligenceSection UI |
| 2026-06-17 | Phase 14B: Knowledge Graph Board — routing fix, rebuild endpoint, canvas force-directed graph, /knowledge page, TopBar Graph button, project subgraph focus |
