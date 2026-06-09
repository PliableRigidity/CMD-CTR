# SILVIA Phase 0 Audit

Date: 2026-06-08
Auditor: Codex
Scope: full repository audit of `frontend/`, `backend/app/`, preserved MAGI decision pipeline, SQLite persistence, voice stack, node registry, watch officer, web/news tooling, and command surfaces.

## 1. Executive Summary

SILVIA is no longer a simple MAGI decision demo. It is now a local-first assistant platform with:

- a FastAPI backend rooted at `backend/app/`
- a React command-center frontend in `frontend/`
- a preserved MAGI decision subsystem in `backend/modes/decision/`
- working local persistence in SQLite for conversation history, nodes, and watch alerts
- working live world-news ingestion and a partially working web/news summarization path
- a working backend voice loop for TTS and STT when Piper and faster-whisper are installed

The codebase is functional enough to demonstrate the concept, but it is not yet hardened. The largest gaps are:

- inconsistent product identity and architecture drift between old MAGI/CMD-CTR and current SILVIA
- a partially migrated frontend/backend split with stale docs and legacy modules still present
- conversation quality regressions on web/news requests
- a decision engine that is wired but operationally unavailable in current runtime
- broad unauthenticated local-action APIs with high security risk
- several placeholder or cosmetic systems still presented as if they are operational

Overall assessment:

- Core shell and API platform: PARTIAL but real
- Voice backend loop: WORKING with caveats
- Conversation quality: PARTIAL
- Decision subsystem: PARTIAL/BROKEN in current runtime
- Intel/news platform: PARTIAL
- Infrastructure/node registry: WORKING for CRUD, PARTIAL for real infrastructure integration
- Security posture: HIGH RISK for any non-local or semi-trusted deployment

## 2. Feature Status Matrix

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| FastAPI app bootstrap | WORKING | `/health`, `/api/*` via `TestClient` | Lifespan required for most routes |
| Route dependency wiring | PARTIAL | routes fail without app lifespan because of `app.state.router` | Fragile for tests and alternate ASGI usage |
| Conversation mode | WORKING | `POST /api/chat` returned time and weather answers | Quality varies by tool path |
| Time tool | WORKING | `POST /api/chat` with `what time is it` | Uses configured timezone, not user locale |
| Weather tool | WORKING | `POST /api/chat` with `weather in singapore` | Fresh data returned, rendering improved |
| Web search tool | PARTIAL | `POST /api/web/search` and chat with latest AI news | Search works, conversational rendering weak |
| News event feed API | WORKING | `POST /api/web/events` | Uses Google News RSS + enrichment |
| World events API, static mode | BROKEN | `GET /api/world/events` returned `[]` | Local service intentionally empty |
| World events API, live mode | WORKING | `GET /api/world/events?live=true` | Reuters intermittently fails DNS/fetch |
| News summarization quality | BROKEN | latest AI news chat answered with generic “find news by exploring…” | Does not meet SILVIA conversational requirement |
| Decision mode routing | WORKING | `/api/decision` reachable | Backend route and service wired |
| MAGI decision execution | BROKEN | `/api/decision` returned graceful unavailable response | Runtime stack times out/fails under current conditions |
| Mode switching | WORKING | `GET/POST /api/mode`, WebSocket event emitted | No auth/validation beyond freeform string |
| Event log REST | WORKING | `/api/events/logs` | In-memory only |
| Event WebSocket | WORKING | `/api/ws/events` round-trip verified | Prior logs showed 403s in some runs |
| Voice status/diagnostics | WORKING | `/api/voice/status`, `/api/voice/diagnostics` | Reflects installed local stack |
| Voice TTS endpoint | WORKING | `/api/voice/synthesize` produced WAV | Test-client text rendering failed only because binary was printed as text |
| Voice STT endpoint | WORKING | synthesized WAV re-transcribed successfully | Model download on first use increases latency |
| End-to-end voice round trip | WORKING | Piper WAV -> Whisper STT verified | Frontend/browser playback still not audited in-browser here |
| Browser auto-speech path | PARTIAL | frontend now uses backend TTS, not browser synth | Needs live UI verification |
| Voice diagnostics page | PARTIAL | API surface exists and recorder logic improved | UX path not validated in browser session |
| Action registry listing | WORKING | `/api/actions` | Static descriptors |
| Alias execution validation | WORKING | invalid alias returns structured error | Good negative-path handling |
| App launching | PARTIAL | code paths exist | Not safely executed during audit; high-risk surface |
| URL launching | PARTIAL | code paths exist | No allowlist, no auth |
| System audio read | PARTIAL | `/api/system/audio` returned keyboard fallback with null state | Can report availability without true volume visibility |
| System audio mutate | PARTIAL | implementation exists | Not executed due local side effects |
| Media key controls | PARTIAL | implementation exists | Not executed due local side effects |
| Device registry | PLACEHOLDER | `/api/devices` returns static list from code | No real discovery or persistence |
| Mission service | PLACEHOLDER | `/api/missions` returns hardcoded mission list | Product copy, not live project state |
| Node registry CRUD | WORKING | create, edit, delete verified | Persists to SQLite |
| Node metrics updates | PARTIAL | route exists | No live metrics collector feeding it |
| Tailscale integration | PLACEHOLDER | fields only; no `tailscale status --json` integration | Cosmetic today |
| Watch officer CRUD | WORKING | create + dismiss verified | Backed by SQLite |
| Watch officer intelligence | PLACEHOLDER | seeded alerts only | No monitoring engine |
| Memory history persistence | WORKING | `/api/memory/history` showed persisted messages | Real SQLite persistence |
| Memory facts persistence | WORKING | endpoints exist, schema real | Not exercised with save in this pass |
| Maps routing API | WORKING | `/api/maps/route` London -> Cambridge succeeded | Public OSM/OSRM dependency |
| Navigation in main UX | UNUSED/DEAD | main shell no longer consumes route state | Legacy component still present |
| Intel Board page | PARTIAL | renders from mock engine + live RSS | Mixed simulation and live data |
| Intel simulations | PLACEHOLDER | `mockEngine.js` synthetic threats, flights, ships, markets | Not real intelligence data |
| `magi_ui/` | UNUSED/LEGACY | present but not main app | Should be archived or removed |
| `backend/core/` legacy app/router | UNUSED/LEGACY | old FastAPI/router code still present | Confusing duplicate backend architecture |

## 3. System Inventory

### Frontend

- Entry:
  - `frontend/src/main.jsx`
  - `frontend/src/App.jsx`
- Pages:
  - `CommandCenterPage`
  - `IntelBoardPage`
  - `VoiceDiagnosticsPage`
- Main command shell:
  - `frontend/src/app/AppShell.jsx`
  - `TopBar`
  - `MissionPanel`
  - `ConversationPanel`
  - `DecisionEnginePanel`
  - `InfrastructurePanel`
  - `ActionShortcutsPanel`
  - `WatchOfficerPanel`
  - `EventsStreamPanel`
- Intel-specific components/data:
  - `GlobeComponent`
  - `mockEngine.js`
  - `maritimeRoutes.js`
  - `cameras.js`
- Voice UI:
  - `WaveformVisualizer`
  - `VoiceStatusPill` (currently not mounted in main shell)
  - `VoiceDiagnosticsPage`
- Unused or apparently unmounted frontend code:
  - `useIntelBoardData`
  - `DevicesPanel`
  - `NavigationPanel`
  - `IntelMapPanel`
  - `EventFeed`
  - legacy `magi_ui/`

### Backend app platform

- App bootstrap:
  - `backend/app/core/application.py`
  - `backend/app/main.py`
  - root launchers: `main.py`, `backend/main.py`
- Shared orchestration:
  - `AssistantPlatformRouter`
  - `EventService`
  - `ConversationService`
  - `DecisionService`
  - `ActionService`
  - `SystemControlService`
  - `VoiceService`
  - `WebIntelligenceService`
  - `WorldEventsService`
  - `MapsService`
  - `DeviceManager`
  - `MissionService`

### Preserved decision/MAGI subsystem

- `backend/modes/decision/`
  - `engine.py`
  - `orchestrator.py`
  - `models.py`
  - `world_model.py`
  - `action_generator.py`
  - `debate.py`
  - `voting.py`
  - `schemas.py`
  - prompts under `backend/modes/decision/prompts/`
- Root prompt dependency:
  - `prompts/chair.txt`

### Tools

- Planner and tools:
  - `backend/app/tools/planner.py`
  - `time_tool.py`
  - `weather.py`
  - `geo.py`
- Tool families exposed through conversation:
  - time
  - weather
  - search_web
  - local actions
  - audio controls
  - navigation refusal path
  - memory save/recall

### Voice systems

- API:
  - `/api/voice/status`
  - `/api/voice/diagnostics`
  - `/api/voice/state`
  - `/api/voice/transcribe`
  - `/api/voice/synthesize`
- Service/pipeline:
  - `VoiceService`
  - `VoicePipeline`
  - `whisper_stt.py`
  - `piper_tts.py`
  - `speech_sanitizer.py`

### Web/news/intelligence systems

- Search providers:
  - SearxNG
  - DuckDuckGo HTML
  - Bing RSS
  - Google News RSS
- Article extraction:
  - `backend/app/web/fetch/extractor.py`
  - `backend/app/web/news/extractor.py`
- Live world feed:
  - `backend/app/world/rss_ingestor.py`
  - `category_classifier.py`
  - `importance_ranker.py`
  - `text_cleaner.py`

### Infrastructure systems

- Node registry:
  - API routes in `backend/app/api/nodes.py`
  - persistence in `backend/app/services/node_service.py`
  - frontend CRUD panel in `frontend/src/components/infrastructure/InfrastructurePanel.jsx`
- Watch officer:
  - API routes in `backend/app/api/watch.py`
  - persistence in `backend/app/services/watch_service.py`
  - UI in `WatchOfficerPanel`
- Tailscale:
  - modeled as optional fields only
  - no discovery or command integration present

### Memory systems

- SQLite history/facts:
  - `backend/memory/database.py`
  - `backend/memory/memory_service.py`
- Tables:
  - `messages`
  - `sessions`
  - `facts`

### Database

- Single SQLite file:
  - `data/cmdctr.db`
- Tables observed:
  - `messages`
  - `sessions`
  - `facts`
  - `nodes`
  - `watch_alerts`
- Indexes observed:
  - `idx_messages_session`

### All API routes

- `GET /health`
- `POST /api/chat`
- `POST /api/decision`
- `GET /api/mode`
- `POST /api/mode`
- `GET /api/actions`
- `POST /api/actions/open-app`
- `POST /api/actions/open-url`
- `POST /api/actions/execute`
- `GET /api/devices`
- `GET /api/world/events`
- `POST /api/maps/route`
- `GET /api/voice/status`
- `GET /api/voice/diagnostics`
- `POST /api/voice/state`
- `POST /api/voice/transcribe`
- `POST /api/voice/synthesize`
- `POST /api/web/search`
- `POST /api/web/article`
- `POST /api/web/events`
- `GET /api/system/audio`
- `POST /api/system/audio/set`
- `POST /api/system/audio/up`
- `POST /api/system/audio/down`
- `POST /api/system/audio/mute`
- `POST /api/system/media/play-pause`
- `POST /api/system/media/next`
- `POST /api/system/media/previous`
- `GET /api/events/logs`
- `WS /api/ws/events`
- `GET /api/memory/history`
- `GET /api/memory/sessions`
- `DELETE /api/memory/history`
- `GET /api/memory/facts`
- `POST /api/memory/facts`
- `GET /api/missions`
- `GET /api/missions/score`
- `GET /api/nodes`
- `GET /api/nodes/types`
- `POST /api/nodes`
- `PUT /api/nodes/{node_id}`
- `PUT /api/nodes/{node_id}/metrics`
- `DELETE /api/nodes/{node_id}`
- `GET /api/watch`
- `POST /api/watch`
- `POST /api/watch/{alert_id}/dismiss`
- `DELETE /api/watch/{alert_id}`

### Scheduled jobs and background workers

- Backend:
  - no scheduler framework found
  - `EventService.emit_nowait()` uses `asyncio.create_task`
  - RSS ingestion uses request-time caching, not a background worker
- Frontend:
  - `IntelBoardPage` polls live events every 60s
  - `TopBar` updates time every second
  - `mockEngine.js` runs multiple simulation intervals
  - geolocation watch exists in unused `useIntelBoardData`

## 4. Critical Issues

1. Decision engine is wired but not operational in current runtime.
   - `/api/decision` returns a graceful fallback instead of a real deliberation result.
   - This is a core product promise and currently unavailable.

2. Security model is effectively nonexistent.
   - No authentication on any route.
   - CORS allows `*`.
   - Action and system-control endpoints can launch apps, open URLs, and send media/system key events.
   - This is only safe for tightly local, trusted use.

3. News/conversation quality does not meet SILVIA’s product goal.
   - “latest AI news” returned a generic redirect-style answer rather than an actual concise summary.
   - Tool success does not guarantee conversational success.

4. Product architecture has duplicate/legacy surfaces that obscure the real system.
   - `backend/core/` legacy app/router remain in repo.
   - `magi_ui/` remains as a legacy frontend.
   - migration docs are stale and incomplete.

5. Some systems are presented as product surfaces but are still placeholders.
   - devices
   - missions
   - watch intelligence
   - non-live world event mode
   - tailscale integration

## 5. Medium Issues

1. World events API has split behavior.
   - `live=false` returns empty because `WorldEventsService.list_events()` is intentionally blank.
   - `live=true` works, but the default path is effectively broken.

2. Route wiring relies on `app.state.router`.
   - Most endpoints only function after lifespan startup.
   - This is fine in production ASGI startup, but brittle for tests and alternate entrypoints.

3. MissionPanel bypasses shared API client.
   - It fetches `http://127.0.0.1:8000/api/missions` directly instead of using `frontend/src/lib/api.js`.
   - This breaks environment portability and central error handling.

4. Intel Board mixes live and synthetic data.
   - world events are live
   - threats, flights, ships, weather, radiation, markets are simulated
   - users can easily misread the board as fully real-time

5. Voice cold start is slow.
   - faster-whisper loads on first transcription and reached out to Hugging Face metadata during first run.
   - This weakens the “instant local OS” feel.

6. System audio status is weak on fallback backend.
   - endpoint returns `available=true` even when actual volume and mute are `null`
   - this is semantically misleading

7. Logs and persistence are partially in-memory.
   - event history is not durable
   - restarts lose operational logs

## 6. Low Priority Issues

1. Frontend text and comments still contain mixed identities: MAGI, CMD-CTR, SILVIA, Palantir.
2. Several files contain encoding artifacts in strings and comments.
3. SQLite schema lacks explicit migration/versioning infrastructure.
4. Search providers and news fetchers have no visible backoff or circuit-breaker layer.
5. Build output remains committed in `frontend/dist`, increasing drift risk.

## 7. Technical Debt List

- Legacy backend tree in `backend/core/`
- Legacy `magi_ui/`
- stale `docs/MIGRATION_REPORT.md`
- unused or unmounted frontend modules:
  - `useIntelBoardData`
  - `DevicesPanel`
  - `NavigationPanel`
  - `IntelMapPanel`
  - `EventFeed`
  - `VoiceStatusPill`
- duplicated concepts:
  - two backend shapes (`backend/app/` and `backend/core/`)
  - old MAGI branding vs SILVIA branding
  - synthetic intel vs real intel in same screen
- no migration system for SQLite
- direct hardcoded localhost fetch in `MissionPanel`
- environment-sensitive voice/tool behavior spread across frontend and backend

## 8. Security Findings

- No authentication or authorization anywhere in API surface.
- CORS is `allow_origins=["*"]` with credentials enabled.
- App-launching endpoints can be triggered remotely if the service is exposed.
- URL opening has no allowlist.
- System media/audio control endpoints can send local keyboard events.
- Workspace paths and command targets are exposed through the action registry.
- No rate limiting, CSRF protection, or host restriction.
- Node/watch/memory endpoints allow arbitrary write operations without auth.

Risk rating: HIGH

Recommended immediate posture:

- treat SILVIA as local-only software
- bind to localhost only
- add explicit environment guardrails before any broader exposure

## 9. Reliability Findings

- Reuters feed fetch failed during audit while other feeds succeeded.
- world feed gracefully degrades across sources, which is good.
- decision engine degrades gracefully, but remains unavailable.
- voice TTS/STT endpoints worked end-to-end in controlled audit.
- weather and maps depend on public third-party APIs and network reachability.
- search depends on external providers and LLM availability.
- event WebSocket worked in audit, but historical logs show prior 403 failures.
- memory persistence is real and stable enough for basic conversation history.
- node and watch persistence are real and stable for CRUD.
- no structured monitoring, health probes for dependencies, retry metrics, or alerting system present.

## 10. Architecture Recommendations

### What SILVIA currently is

SILVIA is a local-first assistant platform with:

- one primary command shell
- one preserved but degraded decision subsystem
- one live-but-mixed intelligence surface
- several infrastructure/productivity surfaces in varying completion states

### What SILVIA should become

SILVIA should become:

- one coherent assistant platform
- one explicit live-data contract per surface
- one hardened local-control boundary
- one conversational rendering pipeline shared across tool responses and speech

### Recommended target architecture

1. Promote `backend/app/` as the only backend architecture.
   - archive or remove `backend/core/`.

2. Split systems into explicit maturity tiers.
   - production-ready
   - experimental
   - legacy
   - simulation-only

3. Consolidate response generation.
   - all tool outputs should pass through one interpretation/rendering layer before UI or TTS.

4. Separate “data source” from “presentation truth.”
   - do not mix simulated and live intel without explicit labeling.

5. Introduce a real persistence/migration layer.
   - at minimum schema versioning and migrations for SQLite.

6. Introduce a security boundary for local actions.
   - capability gating
   - auth or local-only binding
   - explicit high-risk command confirmation

7. Define a stable domain model for infrastructure.
   - node registry
   - telemetry ingestion
   - tailscale discovery
   - watch officer alerts

## 11. Stabilization Roadmap

### Phase 0A: Safety and Truthfulness

- lock the app to localhost by default
- add auth or local-session gate before enabling action/system routes
- label simulation-only intel clearly or hide it from the main product path
- remove stale migration claims and legacy naming confusion

### Phase 0B: Core Reliability

- repair MAGI decision runtime until `/api/decision` returns real decisions again
- make `/api/world/events` return a meaningful result for the default path
- harden news summarization so latest-news requests return actual summaries
- centralize all frontend API access through `frontend/src/lib/api.js`

### Phase 0C: Voice Hardening

- complete browser-level validation of mic capture -> STT -> assistant -> TTS -> playback
- preload or cache whisper model locally to reduce first-use latency
- add explicit audio error states in the UI instead of silent degradation

### Phase 0D: Infrastructure Hardening

- keep node CRUD
- add schema migration/versioning
- implement real telemetry ingestion before showing metrics as a live system
- integrate Tailscale discovery only after defining trust and execution boundaries

### Phase 0E: Codebase Cleanup

- archive/remove `magi_ui/`
- archive/remove unused frontend modules
- archive/remove legacy `backend/core/`
- remove dead navigation remnants
- normalize branding, encoding, and documentation

## BespokeToMe Migration Audit Notes

Evidence of migration remains in `docs/MIGRATION_REPORT.md` and `backend/app/tools/planner.py`, which explicitly says it mirrors the BespokeToMe dispatcher/planner pattern.

What can be concluded from this repo alone:

- the planner/tool-dispatch idea was migrated
- the MAGI decision pipeline was preserved
- the backend/frontend architecture was re-platformed
- several new product surfaces were added around the core

What cannot be fully concluded from this repo alone:

- exact BespokeToMe-to-SILVIA regressions for each tool and prompt
- exact prompt or routing diffs
- exact functionality losses during migration

Reason:

- the BespokeToMe source tree is not present in this workspace

Migration audit status:

- PARTIAL only

Recommended next step:

- place the BespokeToMe repo or a tagged export beside this repo and run a direct diff of:
  - tool planner
  - prompts
  - routing
  - service abstractions
  - web/news integrations

