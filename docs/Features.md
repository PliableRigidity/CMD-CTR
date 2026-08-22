# SILVIA Feature Catalog

Complete catalog of all major SILVIA features. Each entry covers purpose, implementation, usage, and limitations.

## Table of Contents

1. [Multi-Brain Conversation (MAGI)](#1-multi-brain-conversation-magi)
2. [Voice Pipeline](#2-voice-pipeline)
3. [Semantic Memory](#3-semantic-memory)
4. [Node Registry & Telemetry](#4-node-registry--telemetry)
5. [Watch Officer](#5-watch-officer)
6. [silvia-agent Protocol](#6-silvia-agent-protocol)
7. [Hermes Multi-Step Execution Engine](#7-hermes-multi-step-execution-engine)
8. [Mission Control — Project Registry](#8-mission-control--project-registry)
9. [Personal Ops — Tasks, Reminders, Calendar](#9-personal-ops--tasks-reminders-calendar)
10. [Proactive Intelligence Layer](#10-proactive-intelligence-layer)
11. [Desktop Awareness — App Registry](#11-desktop-awareness--app-registry)
12. [Desktop Awareness — File Indexing](#12-desktop-awareness--file-indexing)
13. [Node Service Registry](#13-node-service-registry)
14. [Capability Registry](#14-capability-registry)
15. [Hardware Inventory Registry](#15-hardware-inventory-registry)
16. [Hardware Project Registry](#16-hardware-project-registry)
17. [Build Readiness Engine](#17-build-readiness-engine)
18. [BOM Import Pipeline](#18-bom-import-pipeline)
19. [Hardware Assistant](#19-hardware-assistant)
20. [Procurement Engine](#20-procurement-engine)
21. [Vision-Assisted Inventory](#21-vision-assisted-inventory)
22. [World Intelligence](#22-world-intelligence)
23. [Scheduled Autonomous Tasks](#23-scheduled-autonomous-tasks)
24. [External Notifications](#24-external-notifications)
25. [API Key Authentication](#25-api-key-authentication)
26. [Telegram Chat Bridge](#26-telegram-chat-bridge)
27. [Capability Verification Layer](#27-capability-verification-layer)
28. [Workflow Execution Verification](#28-workflow-execution-verification)

---

## 1. Multi-Brain Conversation (MAGI)

**Purpose:** Provide grounded, reasoned answers by routing queries through the right LLM for the task.

**How It Works:**
- The Tool Planner (`qwen2.5:3b`) reads the user query and outputs a JSON tool dispatch instruction
- Tools execute deterministically (no LLM guessing for data lookups)
- The Conversation model (`gemma3:4b`) synthesizes the tool result into a natural language response
- For decisions requiring deliberation, the MAGI Council runs three independent brains (SARASWATI, LAKSHMI, DURGA) in parallel and a Chair synthesizes consensus

**Backend:** `backend/app/tools/planner.py`, `backend/app/services/conversation_service.py`

**Frontend:** `CommandCenterPage.jsx` — chat input + conversation history panel

**Dependencies:** Ollama (gemma3:4b, qwen2.5:3b, phi4-mini-reasoning, gemma2:2b)

**Example Usage:**
```
User: what's the weather in Tokyo and what time is it there?
→ Planner: call_tools [get_weather(tokyo), get_time_in(tokyo)]
→ Both tools execute in parallel
→ Conversation: synthesizes both results into one answer
```

**Known Limitations:** Response quality depends on local Ollama model quality. gemma3:4b may occasionally hallucinate for factual questions — use `search_web` routing for facts.

**Future Improvements:** Plugin-based tool modules, streaming responses.

---

## 2. Voice Pipeline

**Purpose:** Hands-free voice interaction with SILVIA via wake word detection, speech-to-text, and text-to-speech.

**How It Works:**
1. Silero VAD continuously monitors the microphone for speech activity
2. The wake word detector ("Hey SILVIA") listens on the speech-detected audio
3. On wake word match, SILVIA begins recording the user's utterance
4. Silero VAD detects the end of speech (silence threshold)
5. Audio is sent to STT provider (Speaches preferred, local Whisper fallback)
6. Transcribed text is processed as a regular chat message
7. Response text is sent to TTS provider (Speaches/Kokoro preferred, Piper fallback)
8. Audio plays through the system speaker

**Backend:** `backend/voice/`, `backend/app/api/voice.py`, `backend/app/services/voice_service.py`

**Frontend:** `VoiceDiagnosticsPage.jsx`, microphone button in `CommandCenterPage.jsx`

**Dependencies:**
- Speaches (recommended): OpenAI-compatible STT/TTS server, run on port 9000
- Local fallback: `faster-whisper`, Piper TTS binary, `onnxruntime` (Silero VAD)

**Configuration:**
```env
SPEACHES_URL=http://localhost:9000
SPEACHES_STT_MODEL=rtlingo/mobiuslabsgmbh-faster-whisper-large-v3-turbo
SPEACHES_TTS_MODEL=speaches-ai/Kokoro-82M-v1.0-ONNX
SPEACHES_TTS_VOICE=af_aoede
WHISPER_MODEL_SIZE=base       # local fallback
PIPER_MODEL_PATH=C:\Piper\models\en-us-ryan-high.onnx
```

**Related Commands:** `Hey SILVIA` (wake word), voice diagnostics page at `/voice`

**Known Limitations:** Wake word detection accuracy depends on background noise. Speaches port conflicts with SILVIA's port 8000 — set Speaches to 9000 in its docker-compose.

---

## 3. Semantic Memory

**Purpose:** Search past conversation history by meaning, not just keywords.

**How It Works:**
- Every conversation turn is embedded using `nomic-embed-text` via Ollama
- Embeddings stored in `conversation_memory` table using `sqlite-vec`
- On `semantic_search` queries, the user's query is embedded and compared against stored embeddings using cosine similarity
- Returns the most semantically similar past turns

**Backend:** `backend/app/services/semantic_memory_service.py`

**Dependencies:** `sqlite-vec`, Ollama `nomic-embed-text`

**Example Usage:**
```
what did I say about DroneHive
find conversations about the pi5
did we discuss networking setup
```

**Known Limitations:** Embeddings are retroactively created on startup for any turns that don't have them. Large conversation histories may take time to index on first startup.

---

## 4. Node Registry & Telemetry

**Purpose:** Track all machines on your network — servers, Raspberry Pis, drones, robots, VMs — with live telemetry.

**How It Works:**
- Nodes registered with name, type, hostname/IP, optional Tailscale IP, optional agent URL
- **Agent nodes** (with `agent_url`): polled every 30s for live CPU/RAM/disk/temp/battery/altitude
- **Passive nodes** (hostname only): probed every 5 min via DNS → Tailscale → ping chain
- All telemetry stored in the `nodes` table and emitted via WebSocket
- Infrastructure Panel shows live cards with color-coded status indicators

**Backend:** `backend/app/services/node_service.py`, `backend/app/api/nodes.py`

**Frontend:** Infrastructure Panel in `CommandCenterPage.jsx`

**Supported Node Types:** workstation, server, raspberry-pi, vps, nas, router, vm, drone, robot, esp32, sensor-network, cyberdeck, edge-device, custom

**Example Usage:**
```
show workstation telemetry
pi5 telemetry
show all node telemetry
show hottest node
list drones
verify storage-node
verify all nodes
```

**Known Limitations:** Passive node probing detects online/offline but not detailed metrics. Agent nodes require `silvia-agent` to be running on the target machine.

---

## 5. Watch Officer

**Purpose:** Proactive infrastructure monitoring with threshold alerts and pattern detection.

**How It Works:**
- Background loop evaluates all active nodes every 30s
- Raises alerts when: CPU/RAM/disk/temperature exceeds threshold, node goes offline, node stays offline (with duration tracking)
- Alerts classified by severity: `info`, `warning`, `critical`
- Alerts deduplicated with `rule_key` — same condition doesn't spam
- All alerts stored in `watch_alerts` table
- Active alerts pushed via WebSocket to the Watch Officer panel
- Pattern detection: 3+ alerts from same node triggers a "repeated alerts" warning

**Backend:** `backend/app/services/watch_service.py`, `backend/app/core/application.py`

**Frontend:** Watch Officer panel in `CommandCenterPage.jsx`

**Example Usage:**
```
show alerts
active alerts
watch officer status
show watch alerts
```

**Thresholds (default):** CPU > 90%, RAM > 90%, disk > 90%, temperature > 80°C

**Known Limitations:** Alert thresholds are currently hardcoded. Per-node configurable thresholds are planned.

---

## 6. silvia-agent Protocol

**Purpose:** Bidirectional command and telemetry protocol for nodes that can run a silvia-agent server.

**How It Works:**
- `silvia-agent` is a lightweight Python/FastAPI server that runs on a target node
- SILVIA polls `agent_url/metrics` every 30s for live telemetry
- SILVIA sends commands to `agent_url/command` for arm/disarm/land/home/emergency_stop/reboot
- Robotics nodes (drones, robots) report additional fields: battery, altitude, position, heading, mission_state, imu_data
- Destructive commands (arm, disarm, reboot, emergency_stop) require user confirmation before sending

**Backend:** `backend/app/tools/node_tool.py`, `backend/app/services/node_service.py`

**Example Usage:**
```
arm drone-01
disarm drone-01
land drone-01
send drone-01 home
emergency stop drone-01
reboot pi5
land all drones          # bulk command to all drone-type nodes
```

**Known Limitations:** silvia-agent binary must be deployed separately to each target node. No automatic retry for failed commands.

---

## 7. Hermes Multi-Step Execution Engine

**Purpose:** Execute complex multi-step tasks that require planning, tool use, and verification.

**How It Works:**
- Hermes uses `phi4-mini-reasoning` with structured chain-of-thought prompting
- Given a high-level task ("check all nodes and report any issues"), Hermes breaks it into steps
- Each step either calls a SILVIA tool or evaluates previous results
- Results are aggregated into a final summary
- Also used for scheduled autonomous tasks

**Backend:** `backend/app/services/hermes_service.py`

**Example Usage:**
```
schedule task: check node health every 60 minutes
schedule a task to list all nodes every 30 minutes
show scheduled tasks
disable scheduled task node health
delete scheduled task node health
```

**Known Limitations:** Complex multi-step tasks may take 30–120 seconds depending on local LLM speed.

---

## 8. Mission Control — Project Registry

**Purpose:** Track personal projects with status, health, and proactive reminders when they go stale.

**How It Works:**
- Projects registered with name, status, priority, and optional Brain63 vault key
- Statuses: active, paused, blocked, complete
- Priorities: critical, high, normal, low
- `project_health` tool evaluates each project for: stale time, task count, outstanding reminders, active alerts
- Projects with no activity in 14+ days flagged as stale in `forgotten_items`

**Backend:** `backend/app/services/mission_service.py`

**Frontend:** Project panel (left rail) in `CommandCenterPage.jsx`

**Example Usage:**
```
show projects
active projects
create project DroneHive priority high
mark project DroneHive complete
project health
```

**Known Limitations:** Project "activity" is tracked by task/reminder/event dates, not commit history. No git integration.

---

## 9. Personal Ops — Tasks, Reminders, Calendar

**Purpose:** Natural language task, reminder, and calendar management integrated into SILVIA's proactive intelligence.

**How It Works:**
- Tasks: title + optional project + status (pending/done)
- Reminders: message + trigger time + optional recurrence + escalation
  - Escalation: after 24h undismissed → severity `warning`; after 72h → severity `critical`
  - Recurring reminders (daily, weekly, every Friday) re-fire after dismissal
- Calendar: events with start/end times, used by morning briefing and proactive tools

**Backend:** `backend/app/services/mission_service.py`

**Example Usage:**
```
add task: finish DroneHive PCB
show my tasks
complete task DroneHive PCB
remind me in 10 minutes to check the pi5
remind me every Friday to backup Brain63
show reminders
what's on my calendar today
create an event Robotics Meeting tomorrow at 3pm
upcoming events
```

**Known Limitations:** No external calendar sync (Google Calendar, Outlook). Calendar is SILVIA-internal only.

---

## 10. Proactive Intelligence Layer

**Purpose:** Generate grounded, actionable briefings from real system data — not LLM guesses.

**How It Works:**
- `morning_briefing`: Aggregates active projects, pending tasks, due reminders, today's calendar events, active Watch Officer alerts, offline nodes
- `evening_review`: Tallies tasks completed today, alerts generated, outstanding work
- `daily_focus`: Ranks today's priorities from tasks, reminders, project status, and alerts
- `weekly_review`: 7-day retrospective and upcoming-week preview
- `forgotten_items`: Finds stale projects (14+ day idle), overdue reminders, long-pending tasks, old unresolved alerts
- All content is sourced exclusively from system databases — LLM only formats the output

**Backend:** `backend/app/services/mission_service.py`

**Example Usage:**
```
morning briefing
good morning
daily briefing
what should I focus on today
what's my priority today
evening review
end of day
weekly review
what am I forgetting
what's overdue
project health
```

**Known Limitations:** Briefings reflect data at the moment of the query. No push scheduling (e.g., auto-brief at 8am) without using scheduled tasks.

---

## 11. Desktop Awareness — App Registry

**Purpose:** Discover, register, and intelligently open any application installed on the Windows machine.

**How It Works:**
- `scan_apps` scans: Windows Start Menu shortcuts, Desktop shortcuts, Windows Uninstall registry, common install paths (Program Files, AppData, Steam, etc.)
- Each discovered app assigned a display name, executable path, and aliases (e.g. "vs code", "vscode", "code")
- `open_app` resolves the app by name/alias and launches it
- `open_target` is preference-aware: checks user's stored preference (web/app/folder) before deciding what to open
- `set_launch_preference` lets you specify: "prefer spotify desktop" or "prefer github web"
- Runtime tracking: `list_running_apps` shows which registered apps are currently running, with PIDs and launch times
- `close_app` sends WM_CLOSE to gracefully terminate an app

**Backend:** `backend/app/services/action_service.py`

**Example Usage:**
```
scan installed apps
open VS Code
open obs
open spotify
open spotify web
open spotify desktop
close Chrome
is Fusion 360 running
show running apps
show app obs
prefer spotify desktop
show launch preferences
add Blender app at C:\Program Files\Blender Foundation\Blender 4.2\blender.exe
```

**Known Limitations:** App discovery is Windows-only. Closing apps with `WM_CLOSE` may not work for apps that don't handle Windows messages (some games, some electron apps).

---

## 12. Desktop Awareness — File Indexing

**Purpose:** Search and open files across trusted filesystem locations without knowing exact paths.

**How It Works:**
- Trusted locations registered with name, path, aliases, and tags (e.g. "CMD-CTR" → `C:\Users\...\GitHub\CMD-CTR`)
- `find_files` searches indexed locations for files by name, extension, or description
- `recent_files` shows newest files from a location
- `open_kicad_project` resolves `.kicad_pro` files and opens them in KiCad
- `open_location` opens a trusted folder in Windows File Explorer
- Brain63 Obsidian vault is a special read-only trusted location for personal knowledge

**Backend:** `backend/app/services/action_service.py`

**Example Usage:**
```
find STL files
find PCB files
find python files in CMD-CTR
find latest PDF
show recent files
recent DroneHive files
open CMD-CTR folder
open DroneHive
open latest KiCad project
add Cyberdeck folder at C:\Users\user\Documents\GitHub\Cyberdeck
list locations
```

**Known Limitations:** File indexing is on-demand (at query time), not background-crawling. Very large directories may be slow.

---

## 13. Node Service Registry

**Purpose:** Track what software services are running on each node.

**How It Works:**
- Services registered per node: name + type + description
- Preset bundles available: `nas`, `media-player`, `robot`, `esp32`, `web-server`, `drone`
- Services are a prerequisite for capabilities
- Listed via `list_services`

**Backend:** `backend/app/services/node_service.py`

**Example Usage:**
```
show services on storage-node
what services does pi5 have
list all services
register storage-node as NAS
add samba service to storage-node
rename service samba to file-sharing on storage-node
remove samba service from storage-node
```

---

## 14. Capability Registry

**Purpose:** Execute named actions on nodes through a standardized capability namespace.

**How It Works:**
- Capabilities are attached to services: `media.play`, `motion.forward`, `system.restart`, etc.
- `execute_capability` resolves the right node+service and sends the command via silvia-agent
- Risk levels: `low` (execute immediately), `high`/`critical` (require user confirmation)
- Capability namespaces: media, motion, camera, system, sensor, battery, gpio, navigation, audio

**Backend:** `backend/app/tools/node_tool.py`, `backend/app/services/node_service.py`

**Example Usage:**
```
play music on storage-node
pause music
set volume to 50 on storage-node
move drone-01 forward
stop rover
take a photo on pi5
start camera stream on pi5
restart nginx on remote-server
read sensor on esp32-01
battery status on drone-01
```

---

## 15. Hardware Inventory Registry

**Purpose:** Track all physical electronic components — MCUs, sensors, displays, motors, and more.

**How It Works:**
- Parts stored in `hw_inventory` with name, category, quantity, status, location, manufacturer, part number
- Auto-classification: the category classifier (`hardware_category_classifier.py`) assigns categories using keyword rules + confidence scores
- Fuzzy matching via `find_part_smart()`: finds parts by normalized name, aliases, or substring
- Status auto-set from quantity: 0 = `out-of-stock`, 1–4 = `low-stock`, 5+ = `in-stock`
- Reorder thresholds: when `quantity ≤ reorder_threshold`, part appears in low-stock alerts

**Backend:** `backend/app/services/hardware_service.py`, `backend/app/services/hardware_category_classifier.py`

**Frontend:** Inventory panel in `HardwareBoardPage.jsx`

**Categories:** microcontroller, sbc, sensor, display, radio, motor, power, audio, storage, pcb, module, gps_gnss, misc

**Example Usage (Hardware Assistant):**
```
I bought: 5 ESP32-S3
add 3 MPU6050
remove 2 VL53L0X
show inventory
show microcontrollers
show sensors
how many ESP32 do I have
recategorize inventory
set reorder threshold for ESP32-S3 to 5
```

---

## 16. Hardware Project Registry

**Purpose:** Track hardware build projects and their component requirements (BOM).

**How It Works:**
- Projects in `hw_projects`: name, status (10-state model), priority
- Bill of Materials (BOM) stored in `hw_project_parts`: which parts the project needs, how many, acceptable substitutes
- Project status: planned → researching → designing → ordering → waiting_for_parts → building → testing → blocked → completed → archived
- `get_project_with_parts()` returns project + all linked parts with current stock quantities

**Backend:** `backend/app/services/hardware_service.py`

**Frontend:** Projects panel in `HardwareBoardPage.jsx`

**Example Usage (Hardware Assistant):**
```
show projects
show project rover
create project Rover
show planned projects
hardware requirements for rover
what parts does rover need
Rover requires: 3 ESP32-S3, 2 MPU6050
assign ESP32-S3 to Rover
```

---

## 17. Build Readiness Engine

**Purpose:** Determine whether a hardware project can be built with current inventory, and what's missing.

**How It Works:**
- `get_build_readiness(project_id)`: queries all project-part links and compares `quantity_required` against current `quantity` in inventory
- Returns: `ready` (all parts sufficient), `partial` (some parts missing), `no_required_parts` (no BOM set)
- Missing parts include `shortfall` = quantity_required − available
- Acceptable substitutes checked: if primary part is missing but substitute is available, project can still be built
- `get_all_readiness()`: runs readiness for all active projects
- `get_order_recommendations()`: analyzes missing parts across all projects and ranks by urgency

**Backend:** `backend/app/services/hardware_service.py`

**Frontend:** Intelligence Section in `HardwareBoardPage.jsx` (Build Readiness, Missing Parts, Recommendations, Priority panels)

**Example Usage (Hardware Assistant):**
```
can I build Rover
can I make Rover
what can I build right now
which projects are blocked
show missing parts for Rover
what parts am I missing for Drone
what should I order
what will be buildable after delivery
```

---

## 18. BOM Import Pipeline

**Purpose:** Import Bills of Materials from CSV or KiCad BOM files to automatically populate project parts.

**How It Works:**
- `HardwareImportService` parses CSV files (auto-detect headers) and KiCad BOM format
- Parts are matched against existing inventory using fuzzy matching
- New parts are created if not found
- Project is created if named project doesn't exist
- Import log stored in `hw_imports` for auditability
- `show BOMs` lists recent import history

**Backend:** `backend/app/services/hardware_import_service.py`

**Example Usage (Hardware Assistant):**
```
import BOM /path/to/Widget_BOM.csv
import inventory /path/to/stock.csv
show BOMs
show imported BOMs
```

**Supported formats:**
- CSV with columns: reference, value, quantity (KiCad default export)
- Generic CSV with name/qty columns (auto-detected)
- KiCad `.xml` BOM format

---

## 19. Hardware Assistant

**Purpose:** Natural-language chat interface for all hardware inventory operations with a preview-before-commit safety model.

**How It Works:**
- Separate from the main SILVIA assistant — dedicated to hardware operations only
- All mutating operations (add, remove, create, order) show a **preview** first
- User types `confirm` to commit or `cancel` to abort
- Routing is regex-based (deterministic) — no LLM for intent classification
- Supports: inventory management, project management, build readiness, orders, procurement, BOM import, vision redirect

**Backend:** `backend/app/services/hardware_assistant_service.py`

**Frontend:** Hardware Assistant Panel in `HardwareBoardPage.jsx`

**Safety model:**
```
User: I bought: 5 ESP32-S3
→ SILVIA: "Preview: ESP32-S3 3 → 8. Confirm or cancel."
User: confirm
→ SILVIA: "Inventory updated: ESP32-S3 3 → 8"
```

---

## 20. Procurement Engine

**Purpose:** Manage the full procurement lifecycle: order creation, delivery tracking, reorder alerts, and post-delivery build forecast.

**How It Works:**
- Orders tracked in `hw_orders` with status: ordered → manufacturing → shipped → in_transit → delivered → cancelled
- `receive_order()`: marks order delivered, credits quantity to inventory part
- `reorder_threshold` per part: when `quantity ≤ threshold`, part appears in `get_low_stock()`
- `get_after_delivery_readiness()`: simulates adding all active order quantities to inventory, then re-runs build readiness for all projects
- `get_order_recommendations()`: finds parts with shortfalls across active projects, ranks by urgency

**Backend:** `backend/app/services/hardware_service.py`

**Frontend:** Procurement Section in `HardwareBoardPage.jsx` (Active Orders, Low Stock, After-Delivery forecast panels)

**Example Usage (Hardware Assistant):**
```
order 5 ESP32-S3 from Mouser
order ESP32-S3 x5 from AliExpress
show active orders
show orders
mark order delivered
mark order [ID] delivered
show low stock
set reorder threshold for ESP32-S3 to 5
what will be buildable after delivery
what should I order
```

---

## 21. Vision-Assisted Inventory

**Purpose:** Upload a photo of components on a workbench and automatically detect and add them to inventory.

**How It Works:**
1. User uploads image via the Vision Analysis panel (drag-and-drop or click)
2. Image sent to `POST /api/hardware/vision/analyze`
3. Vision service calls either Anthropic Vision (Claude Haiku) or Ollama llava model
4. Model returns JSON with component name, quantity, category, confidence score, and visual evidence
5. Results split into `high_confidence` (≥ 0.65) and `low_confidence` (< 0.65)
6. High-confidence items pre-approved; all items shown with current inventory context
7. User toggles which items to accept, clicks Confirm
8. `POST /api/hardware/vision/apply` updates inventory

**Backend:** `backend/app/services/hardware_vision_service.py`

**Frontend:** Vision Analysis section in `HardwareBoardPage.jsx`

**Provider selection:**
```
VISION_PROVIDER=auto (default):
  ANTHROPIC_API_KEY set AND anthropic SDK installed → Anthropic (better accuracy)
  Otherwise → Ollama llava (fully local)
```

**Setup — Anthropic:**
```bash
pip install anthropic>=0.50.0
# Add to .env:
ANTHROPIC_API_KEY=sk-ant-...
```

**Setup — Ollama:**
```bash
ollama pull llava
# No other config needed
```

**Related Commands (Hardware Assistant):**
```
vision status
analyze this image     # redirects to Vision Panel
can you analyze images
```

**Known Limitations:** Low-confidence items are never auto-approved. The confidence threshold (0.65) is configurable via `VISION_CONFIDENCE_THRESHOLD`. Ollama llava is significantly less accurate than Claude Vision for component identification.

---

## 22. World Intelligence

**Purpose:** Real-time data from the external world — weather, stock prices, web search, time zones.

**How It Works:**
- Weather: OpenWeatherMap API (free tier, requires `OPENWEATHER_API_KEY`)
- Time zones: `timezonefinder` + `pytz` — no API key needed
- Web search: SearxNG instance (self-hosted, private) or DuckDuckGo fallback
- Stock prices: real-time quotes via web
- RSS feeds: configured feeds pulled every 15 min for world intelligence context

**Backend:** `backend/app/tools/planner.py`, `backend/app/services/web_service.py`, `backend/app/world/rss_ingestor.py`

**Example Usage:**
```
weather in London
is it raining in Paris
what time is it in Singapore
AAPL stock price
what is Microsoft trading at
search for latest news on Raspberry Pi
who is Elon Musk
```

**Known Limitations:** Web search quality depends on SearxNG configuration. Stock prices are fetched from public web data, not a financial API.

---

## 23. Scheduled Autonomous Tasks

**Purpose:** Run recurring Hermes tasks on a cron schedule — health checks, briefings, monitoring.

**How It Works:**
- Tasks defined with: name, prompt (what SILVIA will do), interval_minutes
- Background loop checks every 60s for tasks where `next_run ≤ now` and `enabled = true`
- Due tasks run through the Hermes execution engine
- Results saved to `last_result`, `next_run` advances by interval
- Results emit Watch Officer alerts if they indicate problems

**Backend:** `backend/app/services/scheduled_task_service.py`

**Example Usage:**
```
schedule task: check node health every 60 minutes
schedule a task to list all nodes every 30 minutes
show scheduled tasks
disable scheduled task node health
delete scheduled task node health
```

---

## 24. External Notifications

**Purpose:** Push Watch Officer alerts to Discord, Slack, or email when SILVIA detects problems.

**How It Works:**
- When Watch Officer raises an alert meeting `NOTIFICATION_MIN_SEVERITY`, the notification service fires
- Debounced: same `rule_key` won't re-notify for 30 minutes
- Discord: rich embed with color-coded severity (red=critical, orange=warning)
- Slack: attachment block format
- Email: SMTP via stdlib `smtplib`
- Generic JSON: raw POST to any webhook

**Backend:** `backend/app/services/notification_service.py`

**Configuration:**
```env
NOTIFICATION_WEBHOOK_URL=https://discord.com/api/webhooks/...
NOTIFICATION_WEBHOOK_FORMAT=discord     # discord | slack | json
NOTIFICATION_MIN_SEVERITY=critical      # warning | critical
NOTIFICATION_EMAIL_HOST=smtp.gmail.com  # optional email
NOTIFICATION_EMAIL_PORT=587
NOTIFICATION_EMAIL_USER=you@gmail.com
NOTIFICATION_EMAIL_PASS=app-password
NOTIFICATION_EMAIL_TO=you@gmail.com
```

---

## 25. API Key Authentication

**Purpose:** Secure SILVIA's API when exposed on a network beyond localhost.

**How It Works:**
- Middleware checks `X-API-Key` header (or `Authorization: Bearer <key>`) on every request
- If `API_KEY` env var is empty: auth disabled — all requests pass (localhost-only safe use)
- If `API_KEY` is set: key must match or request returns 401
- Localhost bypass: `127.0.0.1` and `::1` always pass regardless of key
- WebSocket: accepts `?api_key=<key>` query parameter
- Frontend stores key in `localStorage` under `silvia_api_key`, attaches to all requests
- First-run: if backend returns 401 and no key stored, UI prompts for key entry

**Backend:** `backend/app/core/auth_middleware.py`

**Frontend:** `frontend/src/lib/api.js` — `getApiKey()`, `setApiKey()`, `on401()` handler

**Configuration:**
```env
API_KEY=your-secret-key-here
```

---

## 26. Telegram Chat Bridge

**Purpose:** Receive and reply to messages via a Telegram bot, using SILVIA's full chat pipeline.

**How It Works:**
- Polls Telegram Bot API for incoming messages
- Authorized user IDs checked on every message before processing
- Messages forwarded through the same pipeline as the web UI (`source=telegram`)
- Singleton guard: PID lock file (`.runtime/telegram.lock`) prevents multiple polling instances
- Uvicorn reload detection: parent supervisor process skips polling, only worker polls
- Graceful 409 Conflict handling: logs once, stops bridge, does not retry
- Stale lock detection: uses `GetExitCodeProcess` (Windows) / `os.kill` (Unix) to verify PID liveness

**Backend:** `backend/app/services/telegram_bridge.py`, `backend/app/api/telegram.py`

**Configuration:**
```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456789:ABCDEFabcdef...
TELEGRAM_ALLOWED_USER_IDS=987654321
```

**Status endpoint:** `GET /api/telegram/status` — returns `enabled`, `configured`, `running`, `pid`, `started_at`, `lock_held`, `lock_pid`, `allowed_users_count`.

**Known Limitations:** Only one backend instance can poll a given bot token. Long messages are auto-chunked at 4000 chars.

---

## 27. Capability Verification Layer

**Purpose:** Prevent SILVIA from hallucinating infrastructure state. Every response about system state must come from verified tool output, never LLM inference.

**How It Works:**
- **Verification Interceptor** (before social engine): intercepts bare infrastructure commands (`hostname`, `uptime`, `docker ps`, etc.) and refuses with instructions to use `run <command>`
- **SSH terminal tracking**: records when an SSH window was opened and explains the command-channel limitation on subsequent infrastructure queries
- **LLM Fallback Guard** (before free-text LLM): catches infra state queries that slipped through routing and blocks LLM fabrication
- **Source attribution**: all verified command output includes metadata (node, source, tool, executed, timestamp)
- **CapabilityExecutionResult**: structured dataclass recording every tool execution for audit

**Backend:** `backend/app/services/capability_verification.py`, `backend/app/services/conversation_service.py`, `backend/app/services/conversation_state.py`

**Example:**
```
User: hostname
SILVIA: I can't answer `hostname` from inference — infrastructure state must come from actual command output.
        To run on this machine: run hostname

User: run hostname
→ [approve workflow] → Executes locally → "AFTERSHOCK90" with source attribution

User: ssh storage-node → [approve] → SSH terminal opens
User: hostname
SILVIA: I opened an SSH terminal to storage-node, but I don't have a command channel.
        Run the command in the SSH terminal window.
```

**Known Limitations:** Only detects common Unix system commands via regex. Custom or obscure commands may slip through to the LLM.

---

## 28. Workflow Execution Verification

**Purpose:** Guarantee that workflow approval triggers actual tool execution — not generic LLM-generated text.

**How It Works:**
- All three approval paths (`approve WF-XXX`, `yes`, `approve all`) share a single method: `_execute_approved_workflow()`
- Before tool runs: workflow marked as `executing`
- After tool runs: checks `_last_tool_ok` flag AND response title for "Failed"
- `None` result (exception swallowed by try/except) treated as failure, not silent success
- Structured execution result stored in workflow DB: `{"executed": true, "success": true/false, "executor": "...", "raw_output": "...", "error": "..."}`
- SSH handler failure paths (node not found, no address, no username) set `_last_tool_ok = False`

**Backend:** `backend/app/services/conversation_service.py` (`_execute_approved_workflow`), `backend/app/services/workflow_engine.py` (`mark_executing`, `mark_completed`, `mark_failed`)

**Workflow States:**
```
draft → pending_review → approved → executing → completed
                      → rejected              → failed
                      → cancelled
```

**Example:**
```
User: ssh storage-node
SILVIA: Workflow WF-028 requires review. Reply: approve WF-028

User: approve WF-028
→ mark_executing → ssh_node tool runs → SSH terminal opens → mark_completed
→ {"executed": true, "success": true, "executor": "ssh_node"}

User: ssh fakenode → approve WF-029
→ mark_executing → ssh_node tool runs → "Node not found" → mark_failed
→ {"executed": true, "success": false, "executor": "ssh_node", "error": "Tool reported failure"}
```

**Known Limitations:** The `_run_tool` catch-all `except Exception` at the end of the method returns `None` for any unhandled exception. `_execute_approved_workflow` treats this as failure rather than masking it, but the original exception details are only in the log, not the workflow record.
