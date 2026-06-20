# SILVIA — System Documentation

**Strategic Intelligence, Logistics, Voice & Integrated Assistant**

Local-first AI operating system. All inference runs on your machine via Ollama. No cloud required.

---

## Table of Contents

1. [What SILVIA Is](#1-what-silvia-is)
2. [Prerequisites](#2-prerequisites)
3. [Setup & Installation](#3-setup--installation)
4. [Starting the System](#4-starting-the-system)
5. [The Interface](#5-the-interface)
6. [Chat Commands — Full Reference](#6-chat-commands--full-reference)
7. [Node Registry](#7-node-registry)
8. [silvia-agent — Node Protocol](#8-silvia-agent--node-protocol)
9. [Robotics & Edge Nodes](#9-robotics--edge-nodes)
10. [Multi-Step Execution (Hermes)](#10-multi-step-execution-hermes)
11. [Semantic Memory](#11-semantic-memory)
12. [Voice Interface](#12-voice-interface)
13. [Watch Officer — Alerts](#13-watch-officer--alerts)
14. [World Intelligence Board](#14-world-intelligence-board)
15. [Decision Mode (MAGI Council)](#15-decision-mode-magi-council)
16. [Personal Operations](#16-personal-operations)
17. [Configuration Reference](#17-configuration-reference)
18. [Troubleshooting](#18-troubleshooting)
19. [Telemetry History Charts](#19-telemetry-history-charts)
20. [Scheduled Autonomous Tasks](#20-scheduled-autonomous-tasks)
21. [API Key Authentication](#21-api-key-authentication)
22. [Mission Control — Proactive Intelligence](#22-mission-control--proactive-intelligence)
23. [Project Registry](#23-project-registry)
24. [Phase History & Roadmap](#24-phase-history--roadmap)
25. [Telegram Chat Bridge](#25-telegram-chat-bridge)
26. [Capability Verification Layer](#26-capability-verification-layer)
27. [Workflow Execution Verification](#27-workflow-execution-verification)
28. [Stability Controls](#28-stability-controls)

---

## 1. What SILVIA Is

SILVIA is a local AI command center with four main capabilities:

| Capability | What it does |
|---|---|
| **Conversation** | Natural language interface to tools, node registry, and LLM reasoning |
| **Infrastructure** | Node registry, live telemetry polling, Watch Officer alerting |
| **Intelligence** | World events feed, RSS ingestion, MAGI multi-agent decision system |
| **Personal Ops** | Tasks, reminders, calendar, semantic memory across all sessions |

Everything is local. The backend is FastAPI on port **8000**, frontend is React on port **5173**. All LLMs run through Ollama.

SILVIA's conversational identity — personality, tone system, humor and serious-mode rules, follow-through guarantees, and the prompt architecture behind them — is specified in [docs/PERSONALITY.md](PERSONALITY.md) and implemented in `backend/app/services/persona.py`.

---

## 2. Prerequisites

### Required

| Dependency | Purpose | Install |
|---|---|---|
| Python 3.11+ | Backend runtime | python.org |
| Node.js 18+ | Frontend build | nodejs.org |
| Ollama | Local LLM inference | ollama.com |

### Required Ollama Models

Pull these before starting:

```bash
ollama pull gemma3:4b          # Main conversation model (SILVIA's voice)
ollama pull qwen2.5:3b         # Tool planner + action generator
ollama pull hermes3            # Multi-step execution engine (~4.7GB)
ollama pull nomic-embed-text   # Semantic memory embeddings
```

Additional models used in Decision Mode:

```bash
ollama pull phi4-mini-reasoning:latest   # World model + SARASWATI
ollama pull gemma2:2b                    # LAKSHMI agent
ollama pull phi3:mini                    # VIVEKA agent
```

> **Minimum viable setup**: `gemma3:4b` + `qwen2.5:3b` + `nomic-embed-text`. Everything else degrades gracefully if missing.

### Optional

- **OpenWeather API key** — enables weather queries (free tier sufficient). Get one at openweathermap.org.
- **SearXNG instance** — enables web search. Can run locally via Docker.
- **Speaches server** — higher-quality STT/TTS than the local Whisper/Piper fallback.
- **sqlite-vec** — required for semantic memory. Installed via `pip install sqlite-vec`.

---

## 3. Setup & Installation

### Backend

```bash
cd backend
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Environment Variables

Create `.env` in the project root (next to `backend/`):

```env
# Weather (optional but recommended)
OPENWEATHER_API_KEY=your_key_here

# Web search via SearXNG (optional)
SEARXNG_URL=http://localhost:8080

# Your local timezone
TIMEZONE=Asia/Kolkata

# Voice — Speaches server (optional, see Voice section)
SPEACHES_URL=http://localhost:9000

# Backend port (default: 8000)
APP_PORT=8000
```

> **Never commit `.env`** — it contains API keys. It is already in `.gitignore`.

---

## 4. Starting the System

### Terminal 1 — Ollama

```bash
ollama serve
```

### Terminal 2 — Backend

```bash
# From project root
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Or via the shortcut entry point:

```bash
python backend/main.py
```

### Terminal 3 — Frontend

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

### Health Check

```bash
curl http://localhost:8000/health
# → {"status": "ok", "service": "silvia", "version": "4.0.0"}
```

---

## 5. The Interface

The UI is a split-panel command center:

```
┌──────────────────────────────────────────────────────────┐
│  TOPBAR: SILVIA branding · mode indicators · time        │
├──────────┬───────────────────────────────┬───────────────┤
│  LEFT    │        CENTER                 │   RIGHT       │
│  RAIL    │    CONVERSATION               │   RAIL        │
│          │    (main chat panel)          │               │
│ Missions │                               │ Infrastructure│
│ Watch    │                               │ Launcher      │
│ Officer  │                               │ Event Log     │
│ Intel    │                               │               │
│ Board    │                               │               │
└──────────┴───────────────────────────────┴───────────────┘
```

**Left rail:**
- **Projects** — registered projects, health status, quick status/priority editing
- **Missions** — task and reminder management, scheduled tasks
- **Watch Officer** — active alerts from infrastructure thresholds
- **Intel Board** — world events feed

**Center:** The main SILVIA conversation panel. All commands go here.

**Right rail:**
- **Infrastructure** — registered nodes, live status/telemetry
- **Launcher** — quick-launch actions and app shortcuts
- **Event Log** — real-time stream of what SILVIA is doing internally (tool calls, agent polls, alerts)

---

## 6. Chat Commands — Full Reference

SILVIA uses a two-layer routing system. A regex planner handles common commands instantly (no LLM call). An LLM planner (qwen2.5:3b) handles ambiguous queries when web search is enabled. Multi-step queries route to the Hermes execution engine.

### 6.1 Time

| Say | What happens |
|---|---|
| `what time is it` | Local system time |
| `time in Tokyo` | Time in any city/timezone |
| `what's the time in New York` | Same with different phrasing |

### 6.2 Weather

Requires `OPENWEATHER_API_KEY` in `.env`.

| Say | What happens |
|---|---|
| `weather in London` | Current conditions, temp, wind |
| `is it raining in Paris` | Same |
| `temperature in Berlin` | Same |

Without an API key, SILVIA will say weather is unavailable.

### 6.3 Stock Prices

| Say | What happens |
|---|---|
| `price of Apple` | Live quote via Yahoo Finance |
| `AAPL stock price` | Ticker lookup |
| `how much is Tesla` | Company name lookup |
| `NVDA quote` | Any valid ticker |

No API key required — uses Yahoo Finance directly.

### 6.4 Web Search

Requires `SEARXNG_URL` in `.env` or `use_web: true` metadata. SILVIA auto-triggers web search for queries containing: `latest`, `recent`, `breaking`, `news`, `who is`, `what happened`, `today's`, `right now`.

| Say | What happens |
|---|---|
| `latest news on NVIDIA` | Web search + grounded answer |
| `who is Sam Altman` | Web search + summary |
| `search for quantum computing` | Explicit search trigger |

To disable web search for a specific query, phrase it as a direct question without news-trigger words.

### 6.5 System Specs

| Say | What happens |
|---|---|
| `what are my system specs` | CPU, RAM, GPU, disk, OS |
| `how much RAM do I have` | Same |
| `what GPU do I have` | Same |
| `cpu usage` | Same |
| `show running processes` | Top processes by CPU |
| `what's my local IP address` | Network interfaces |
| `run ipconfig` | Run any shell command |
| `execute netstat -an` | Same |

### 6.6 Node Registry Commands

See [Section 7](#7-node-registry) for full node management documentation.

| Say | What happens |
|---|---|
| `list my devices` | All registered nodes and status |
| `what nodes are online` | Same |
| `add laptop at 192.168.1.50` | Register new node |
| `add pi5` | Register without hostname (SILVIA asks) |
| `delete nighthawk` | Remove from registry (asks confirmation) |
| `update nighthawk IP to 100.64.1.5` | Update hostname/IP |

### 6.7 Node Telemetry

> **Important:** For a newly registered node, **ping it first** (`ping nighthawk`) to establish its status in the registry, then request telemetry. Nodes without a silvia-agent configured will only show metrics after a successful probe.

| Say | What happens |
|---|---|
| `show nighthawk telemetry` | CPU, RAM, disk, temp, uptime |
| `nighthawk cpu` | Same |
| `workstation ram` | Same for any node |
| `show all node telemetry` | Full infrastructure view |
| `show hottest node` | All nodes sorted by temperature |
| `node health` | Infrastructure overview |
| `show drone-01 telemetry` | Includes battery, altitude, mission state for robotics nodes |

### 6.8 Node Probing & Verification

| Say | What happens |
|---|---|
| `ping nighthawk` | Live ICMP probe right now |
| `is nighthawk online` | Same (live probe) |
| `status of nighthawk` | Cached registry status (no live probe) |
| `verify nighthawk` | Full verification chain: silvia-agent → Tailscale → DNS → ping |
| `verify all nodes` | Verify every registered node |
| `refresh nodes` | Same |

**Probe vs. Registry Status:** `ping` always does a live ICMP probe and updates the registry. `status of` reads the cached value from the last probe or agent poll. A node can show `online` in the registry but fail a live ping if ICMP is blocked (common for VPS/cloud nodes).

### 6.9 SSH

| Say | What happens |
|---|---|
| `ssh into nighthawk` | Opens SSH terminal (asks for username) |
| `ssh nighthawk as admin` | Opens immediately with username |
| `connect to server1` | Same |
| `open terminal on nighthawk` | Same |

After SILVIA asks for a username, reply with just the username (e.g., `ubuntu`). Say `cancel` to abort.

### 6.10 Alerts & Watch Officer

| Say | What happens |
|---|---|
| `show alerts` | All active Watch Officer alerts |
| `active alerts` | Same |
| `watch officer status` | Same |
| `any alerts` | Same |

### 6.11 Robotics Commands

See [Section 9](#9-robotics--edge-nodes) for full robotics documentation.

| Say | What happens |
|---|---|
| `list drones` | All drone-type nodes |
| `show all robots` | All robot-type nodes |
| `arm drone-01` | Arm command (asks confirmation) |
| `disarm drone-01` | Disarm (asks confirmation) |
| `land drone-01` | Land command (immediate) |
| `send drone-01 home` | Return to home (immediate) |
| `emergency stop drone-01` | Emergency stop (asks confirmation) |
| `reboot pi5` | Reboot node (asks confirmation) |

### 6.12 Brief

| Say | What happens |
|---|---|
| `brief me` | SILVIA status summary + time |
| `world brief` | Top world events with SILVIA assessment |
| `intel brief` | Same |
| `what's happening globally` | Same |

### 6.13 Multi-Node Bulk Commands

Send a single command to **all nodes of a given type** at once. Destructive bulk commands (arm, disarm, reboot, emergency stop) ask for confirmation first.

| Say | What happens |
|---|---|
| `land all drones` | Land command to every drone-type node with an agent URL |
| `disarm all robots` | Disarm command to every robot-type node (asks confirmation) |
| `arm all drones` | Arm all drone nodes (asks confirmation) |
| `emergency stop all drones` | Emergency stop across all drones (asks confirmation) |
| `reboot all vps` | Reboot every VPS-type node (asks confirmation) |
| `send all robots home` | Return-to-home across all robot nodes |

Nodes without an `agent_url` configured are counted as failed automatically — the command requires an agent to be running on each node.

SILVIA reports the outcome for every node:
```
Bulk 'land' → 3 nodes of type 'drone'
  ✓ drone-01  landed
  ✓ drone-02  landed
  ✗ drone-03  no agent configured
```

### 6.14 Scheduled Tasks

Create tasks that SILVIA runs automatically on a repeating schedule. Execution goes through the Hermes multi-step engine.

| Say | What happens |
|---|---|
| `schedule task: check node health every 60 minutes` | Create a recurring task |
| `schedule a task: world brief every 120 minutes` | Same, alternate phrasing |
| `show scheduled tasks` | List all tasks with status |
| `list scheduled tasks` | Same |
| `disable scheduled task node health` | Pause a task by partial name |
| `delete scheduled task node health` | Remove permanently |

Tasks can also be managed in the **Scheduled Tasks** section in the Mission panel (left rail).

### 6.15 Mission Control & Proactive Intelligence

All Mission Control commands are grounded in real system data. SILVIA never fabricates priorities, deadlines, or status.

| Say | What happens |
|---|---|
| `morning briefing` | Full operational picture: projects, tasks, reminders, alerts, calendar, offline nodes |
| `good morning` | Same |
| `daily briefing` | Same |
| `what's happening today` | Same |
| `sitrep` | Same |
| `what should I focus on today` | Priority-ranked work recommendation built from tasks, reminders, alerts, and project activity |
| `what should I work on` | Same |
| `daily focus` | Same |
| `evening review` | End-of-day summary: completed tasks, projects touched, alerts generated, outstanding work |
| `end of day` | Same |
| `what did I accomplish today` | Same |
| `how did today go` | Same |
| `weekly review` | 7-day summary: completed tasks, active projects, upcoming calendar, alert history |
| `how was my week` | Same |
| `what am I forgetting` | Stale projects (14+ days idle), overdue reminders, long-pending tasks (7+ days) |
| `stale projects` | Same — lists projects with no recorded activity in 14+ days |
| `what's falling behind` | Same |
| `what's overdue` | Same |
| `project health` | Per-project health: status, idle days, task count, active alerts |
| `show project health` | Same |
| `show projects` | List all registered projects |
| `active projects` | Projects with status = active |
| `create project [name]` | Register a new project |
| `mark project [name] as complete` | Update project status |
| `set project [name] to paused` | Same |

### 6.16 Project Registry Commands

| Say | What happens |
|---|---|
| `create project Cyberdeck` | New project with default status (active) and priority (normal) |
| `create project DroneHive priority high` | New project with explicit priority |
| `list projects` | All projects |
| `show paused projects` | Filter by status |
| `mark project KOI as complete` | Update status |
| `set project University to paused` | Same |
| `project health` | Full health report across all projects |

Projects are also managed in the **Projects** panel in the left rail. Click any project to expand it, change status/priority, or delete it.

---

## 7. Node Registry

The node registry is a SQLite table (`data/cmdctr.db`) that tracks every machine in your infrastructure.

### Node Types

| Type | Use for |
|---|---|
| `workstation` | Primary local machine (auto-created, protected) |
| `server` | Home/rack servers |
| `raspberry-pi` | Raspberry Pi devices |
| `vps` | Cloud VPS instances |
| `nas` | Network attached storage |
| `router` | Network routers |
| `vm` | Virtual machines |
| `container` | Docker/LXC containers |
| `cyberdeck` | Custom builds |
| `edge-device` | Generic IoT/edge |
| `drone` | Aerial drone platforms |
| `robot` | Ground robots |
| `esp32` | ESP32 microcontrollers |
| `sensor-network` | Sensor arrays |
| `custom` | Anything else |

### Adding a Node

Via chat:
```
add nighthawk at 100.64.1.23
add pi5 at 192.168.1.10
register server1 at 10.0.0.5
```

Via the Infrastructure panel: click **+ Add Node**, fill in name, type, hostname/IP, and optionally the silvia-agent URL.

After adding, SILVIA immediately probes the node via ICMP ping and stores the result.

### The Workstation Node

The `Workstation` node is auto-created on first start and represents the local machine running SILVIA. It cannot be deleted. It is always probed locally via psutil (CPU, RAM, disk) without needing a hostname.

### How Status is Updated

Three background loops run continuously:

| Loop | Interval | What it does |
|---|---|---|
| **Node Probe** | 60s | ICMP ping all nodes, update status/latency |
| **Agent Poll** | 30s | HTTP poll all nodes with `agent_url` set, update telemetry |
| **Watch Officer** | 30s | Check telemetry against thresholds, raise/resolve alerts |

A node's status (`online`/`offline`/`unknown`) reflects the last result from whichever loop ran most recently. If a node has a silvia-agent configured, the agent poll takes precedence and updates status to `online` even if ICMP is blocked.

### Configure Panel

Click the gear icon on any node card in the Infrastructure panel to open Configure. From here you can set:
- Node name and type
- Hostname / IP
- Tailscale IP
- silvia-agent URL
- Tags and notes

---

## 8. silvia-agent — Node Protocol

silvia-agent is a small FastAPI server you deploy on any node you want to give SILVIA live telemetry access and remote command execution.

### Requirements

```bash
pip install fastapi uvicorn psutil httpx
```

### Deployment

```bash
cd silvia-agent

# Basic deployment
AGENT_NODE_NAME=pi5 AGENT_NODE_TYPE=raspberry-pi python main.py

# With custom port
AGENT_NODE_NAME=pi5 AGENT_NODE_TYPE=raspberry-pi AGENT_PORT=8765 python main.py

# Runs on port 8765 by default (change with AGENT_PORT)
```

Then in SILVIA's node Configure panel, set **Agent URL** to `http://<node-ip>:<port>` (e.g., `http://192.168.1.10:8765`).

### Agent Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AGENT_NODE_NAME` | hostname | Name shown to SILVIA |
| `AGENT_NODE_TYPE` | `server` | Node type (see types above) |
| `AGENT_NODE_ROLE` | _(empty)_ | Optional role description |
| `AGENT_HOST` | `0.0.0.0` | Interface to bind to |
| `AGENT_PORT` | `8765` | Port to listen on |
| `AGENT_ALLOWED_COMMANDS` | `reboot,restart_service,emergency_stop` | Comma-separated allowed commands |

### Agent Endpoints

| Endpoint | Method | Returns |
|---|---|---|
| `/status` | GET | Identity, health summary, allowed commands |
| `/telemetry` | GET | CPU, RAM, disk, temp, uptime + robotics fields |
| `/services` | GET | Detected running services |
| `/capabilities` | GET | Hardware capabilities |
| `/command` | POST | Execute a command (see Section 9) |

### Services Auto-Detection

The agent detects common services automatically: `nginx`, `apache`, `postgresql`, `mysql`, `redis`, `docker`, `ssh`, `ollama`, `homeassistant`, `mosquitto`, and others. Detected services appear in the node's card in the Infrastructure panel.

### Running as a Service (Linux)

```ini
# /etc/systemd/system/silvia-agent.service
[Unit]
Description=SILVIA Node Agent
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/silvia-agent/main.py
Environment=AGENT_NODE_NAME=pi5
Environment=AGENT_NODE_TYPE=raspberry-pi
Environment=AGENT_PORT=8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable silvia-agent
sudo systemctl start silvia-agent
```

---

## 9. Robotics & Edge Nodes

Drone, robot, ESP32, and sensor-network nodes get extended telemetry and command-and-control support.

### Robotics Telemetry Fields

These fields appear in telemetry when set. They are `null` for non-robotics nodes.

| Field | Type | Description |
|---|---|---|
| `battery_pct` | float | Battery level 0–100 |
| `position_lat` | float | GPS latitude |
| `position_lon` | float | GPS longitude |
| `altitude` | float | Altitude in metres |
| `heading` | float | Compass heading 0–359 |
| `mission_state` | string | Current mission state |
| `imu_data` | object | IMU readings (accel/gyro x/y/z) |

### Setting Robotics Telemetry on silvia-agent

The agent reads telemetry from environment variables. Set them from your flight controller, hardware driver, or simulator:

```bash
# Static simulation
AGENT_BATTERY_PCT=78 \
AGENT_ALTITUDE=42.5 \
AGENT_HEADING=270 \
AGENT_MISSION_STATE=armed \
AGENT_POSITION_LAT=37.774929 \
AGENT_POSITION_LON=-122.419418 \
AGENT_NODE_TYPE=drone \
python main.py
```

From a real hardware driver, write to the env before starting the agent or use a wrapper that updates `os.environ` at runtime.

**IMU fields:**
```bash
AGENT_IMU_ACCEL_X=0.02
AGENT_IMU_ACCEL_Y=-0.01
AGENT_IMU_ACCEL_Z=9.81
AGENT_IMU_GYRO_X=0.001
AGENT_IMU_GYRO_Y=0.002
AGENT_IMU_GYRO_Z=-0.001
```

### Commands via Chat

Robotics nodes support remote command execution. Some commands require confirmation before executing.

| Command | Confirmation? | Agent sets |
|---|---|---|
| `arm drone-01` | Yes | `AGENT_MISSION_STATE=armed` |
| `disarm drone-01` | Yes | `AGENT_MISSION_STATE=idle` |
| `land drone-01` | No | `AGENT_MISSION_STATE=landing` |
| `send drone-01 home` | No | `AGENT_MISSION_STATE=returning_home` |
| `emergency stop drone-01` | Yes | `AGENT_MISSION_STATE=emergency_stop` |
| `reboot pi5` | Yes | initiates system reboot |
| `reboot pi5` restart_service [svc] | No | restarts named service |

**Confirmation flow:**

When a destructive command is requested, SILVIA will ask:
```
Send 'arm' to drone-01? Reply 'yes' to confirm, or 'cancel' to abort.
```

Reply `yes` to execute, `cancel` to abort. Any other message is ignored until resolved.

### Enabling Commands on a Node

By default, nodes allow: `reboot`, `restart_service`, `emergency_stop`.

For robotics nodes (`drone`, `robot`, `esp32`, `sensor-network`), these are automatically added: `arm`, `disarm`, `land`, `home`, `emergency_stop`.

To customise the allow-list:
```bash
AGENT_ALLOWED_COMMANDS=reboot,restart_service,arm,disarm,land,home,emergency_stop
```

To disable all commands: set `AGENT_ALLOWED_COMMANDS=` (empty string). The `/command` endpoint will reject everything.

---

## 10. Multi-Step Execution (Hermes)

SILVIA detects queries that require multiple tools in sequence and routes them to the Hermes execution engine instead of the single-tool planner.

### What Triggers Hermes

A query is treated as multi-step if it contains any of these signals **and** has more than 8 words:

- ` then `, ` after that`, ` and then `
- `if it's online`, `if it is online`
- `check if`, `first check`
- `and show me`, `and tell me`
- `give me both`, ` also `

Examples that trigger Hermes:
```
show nighthawk status and if online show me its telemetry
check what tasks I have and also show my reminders
first check the watch alerts then show node health
```

### How It Works

1. SILVIA detects the multi-step signal and sends the query to the Hermes execution engine
2. Hermes (the hermes3 model) receives the query + a list of available tools
3. Hermes calls tools in sequence, receiving each result before deciding the next step
4. After all tool calls are complete, Hermes synthesises a single natural-language answer
5. The result is returned to SILVIA's conversation panel

### Fallback Chain

If `hermes3` is not installed, the engine tries:
1. `hermes3` — preferred, fine-tuned for tool-calling
2. `qwen2.5:7b` — good tool-calling support
3. `qwen2.5:3b` — basic tool-calling support, less reliable
4. If none available — falls through to the standard single-tool planner

Check which model was used in the agent badge in the conversation response (`Hermes (hermes3)` etc.).

### Node Queries via Hermes

For node-related conditional queries via Hermes, SILVIA always calls `get_node_telemetry` directly rather than checking status first. This avoids false "offline" results caused by ICMP being blocked on remote nodes.

> **Workflow for new nodes:** Before querying a new node via Hermes, probe it first:
> ```
> ping nighthawk
> ```
> This establishes its registry status. Then multi-step queries that depend on "is it online" will work correctly.

---

## 11. Semantic Memory

SILVIA embeds every conversation turn into a vector store (`data/cmdctr.db` via sqlite-vec) using the `nomic-embed-text` model. This allows searching past conversations by meaning, not just keywords.

### Requirements

```bash
pip install sqlite-vec
ollama pull nomic-embed-text
```

If either is missing, semantic memory silently disables. Conversation still works normally.

### Searching Memory

| Say | What it finds |
|---|---|
| `what did I say about DroneHive` | Conversations mentioning DroneHive |
| `find conversations about the pi5` | Past discussions about pi5 |
| `did we discuss networking` | Networking-related turns |
| `show previous discussions about nodes` | Node-related history |
| `search memory for battery issues` | Battery-related past queries |

Results show: timestamp, similarity percentage, your original message, and SILVIA's reply.

### How It Works

- After every conversation turn, SILVIA queues a background task to embed and store the exchange
- On startup, SILVIA retroactively indexes up to 200 existing turns from conversation history
- Search uses cosine similarity with a 0.55 minimum threshold
- The top 3 most relevant past turns are also silently injected into SILVIA's context before each response, helping her "remember" prior conversations naturally

### Disabling Semantic Memory

Remove `nomic-embed-text` from Ollama or remove the `sqlite-vec` package. The system detects the failure and falls back gracefully. No configuration flag needed.

---

## 12. Voice Interface

SILVIA supports push-to-talk voice input and spoken responses. The voice pipeline uses a wake-word detector (optional) and Silero VAD for speech segmentation.

### Provider Options

**Option A — Speaches (recommended)**

Speaches is a local OpenAI-compatible STT/TTS server. Faster and higher quality than local Whisper/Piper.

```bash
# Run Speaches on port 9000 (SILVIA uses 8000)
# In your Speaches docker-compose.yml:
ports:
  - "9000:8000"
```

Then in `.env`:
```env
SPEACHES_URL=http://localhost:9000
SPEACHES_STT_MODEL=rtlingo/mobiuslabsgmbh-faster-whisper-large-v3-turbo
SPEACHES_TTS_MODEL=speaches-ai/Kokoro-82M-v1.0-ONNX
SPEACHES_TTS_VOICE=af_aoede
```

**Option B — Local Whisper + Piper (fallback)**

No extra server needed. Slower, but works offline.

```env
WHISPER_MODEL_SIZE=base    # Options: tiny, base, small, medium, large
PIPER_MODEL_PATH=C:\Piper\models\en-us-ryan-high.onnx
PIPER_USE_CUDA=false       # Set true if you have a CUDA GPU
```

If neither Speaches nor Piper/Whisper is configured, voice input is disabled and text-only mode operates normally.

### Checking Voice Status

```bash
curl http://localhost:8000/api/voice/status
curl http://localhost:8000/api/voice/diagnostics
```

### Using Voice in the UI

Click the microphone button in the conversation panel. Speak while holding, release to transcribe. SILVIA's response is spoken aloud via the configured TTS provider.

---

## 13. Watch Officer — Alerts

The Watch Officer runs every 30 seconds and evaluates node telemetry against thresholds. Alerts appear in the left-rail Watch Officer panel and are surfaced via WebSocket in real-time.

### Alert Thresholds

| Metric | Warning | Critical |
|---|---|---|
| CPU | 85% | 95% |
| RAM | 85% | 95% |
| Disk | 88% | 95% |
| Temperature | 75°C | 85°C |
| Node offline | — | 30 minutes |

Thresholds are defined in `backend/app/core/application.py`. To change them, edit the constants near the top of `_watch_officer_loop`:

```python
_CPU_WARN = 85.0
_CPU_CRIT = 95.0
_OFFLINE_ALERT_MINUTES = 30
```

### Alert Categories

| Category | Colour | Used for |
|---|---|---|
| `infra` | OPS | Node offline, metric thresholds |
| `system` | SYS | Reminders, SILVIA internal |
| `intel` | INTEL | World events |
| `security` | SEC | (reserved) |

### Alerts Auto-Resolve

When a metric drops below its warning threshold, the alert is automatically resolved and removed from the Watch Officer panel.

### Reminders via Watch Officer

When a reminder fires, it appears as a Watch Officer alert with category `system`. One-time reminders auto-complete. Recurring reminders auto-advance to the next occurrence.

### Reminder Escalation

If a reminder alert is not dismissed by the operator, SILVIA escalates it automatically:

| Time since trigger | Action | Alert severity |
|---|---|---|
| 0–24 hours | Original alert fires | `info` |
| 24+ hours | Escalation alert created: `[ESCALATED] Reminder: ... — unacknowledged for Xh` | `warning` |
| 72+ hours | Elevation alert created: `[ELEVATED] Reminder: ... — ignored for Xh` | `critical` |

Escalation alerts use separate `rule_key` suffixes (`:escalated`, `:elevated`) so they appear as distinct alerts in the Watch Officer panel. Dismiss the original alert to stop escalation.

### Offline Duration Intelligence

Instead of the static message "Nighthawk offline for 30+ min", the Watch Officer tracks the actual elapsed time and includes it in the alert message:

```
Nighthawk offline for 2.3h
```

The message updates on each Watch Officer loop (every 30 seconds) with the current duration.

### Multi-Alert Pattern Detection

If 3 or more active alerts are present simultaneously for the same node (e.g., offline + CPU + RAM), the Watch Officer raises a synthesis alert:

```
[CRITICAL] Nighthawk: 3 active issues detected simultaneously
```

This `rule_key` is `node:{id}:cluster` and auto-resolves when the node drops below 3 simultaneous issues.

### External Notifications

SILVIA can push Watch Officer alerts to external channels (Discord, Slack, or email) so you receive alerts even when away from the UI.

Configure in `.env`:

```env
# Webhook (Discord, Slack, or generic JSON)
NOTIFICATION_WEBHOOK_URL=https://discord.com/api/webhooks/...
NOTIFICATION_WEBHOOK_FORMAT=discord   # discord | slack | json

# Email via SMTP
NOTIFICATION_EMAIL_HOST=smtp.gmail.com
NOTIFICATION_EMAIL_PORT=587
NOTIFICATION_EMAIL_USER=you@gmail.com
NOTIFICATION_EMAIL_PASS=your-app-password
NOTIFICATION_EMAIL_TO=alerts@yourmail.com

# Minimum severity to notify (warning = both warning+critical; critical = critical only)
NOTIFICATION_MIN_SEVERITY=critical
```

Leave `NOTIFICATION_WEBHOOK_URL` and `NOTIFICATION_EMAIL_HOST` empty to disable external notifications entirely (default). The UI Watch Officer panel always shows alerts regardless.

**Debounce:** The same alert rule will not fire again to external channels within 30 minutes, even if it re-triggers. This prevents alert floods on flapping nodes.

**Discord format:** Embeds with colour-coded severity (red = critical, orange = warning).
**Slack format:** Attachment blocks.
**Generic JSON:** Raw `POST` with the full alert object.

---

## 14. World Intelligence Board

The Intel Board (left rail) ingests RSS feeds and applies LLM analysis to world events.

### How It Works

- RSS feeds are ingested at startup and on a background schedule
- Events are categorised by country, priority (`critical`/`high`/`medium`/`low`), and type
- The world model (`phi4-mini-reasoning`) optionally generates assessment, prediction, and recommendation for high-priority events
- Events appear in the Intel Board panel sorted by board priority

### World Brief via Chat

```
world brief
brief me on the world
what's happening globally
intel brief
```

This pulls the top 5 events and reads them as a spoken/text brief with any attached assessments.

---

## 15. Decision Mode (MAGI Council)

The MAGI system is a multi-agent deliberation engine for complex decisions. It uses four specialised agents:

| Agent | Model | Role |
|---|---|---|
| **SARASWATI** | phi4-mini-reasoning | Logic and analytical reasoning |
| **LAKSHMI** | gemma2:2b | Values, intuition, emotional considerations |
| **DURGA** | qwen2.5:3b | Action orientation, risk assessment |
| **VIVEKA** | phi3:mini | Synthesis and final recommendation (Chair) |

### When Decision Mode Activates

Decision mode is triggered by the `/api/decide` endpoint or when the mode router detects decision-intent keywords. From the UI, use the mode toggle to switch explicitly.

### Decision Process

```
User query + goal + constraints
     ↓
World model normalises the problem
     ↓
Action generator creates 3–5 options
     ↓
Round 1: SARASWATI, LAKSHMI, DURGA evaluate each option
     ↓
Debate round: agents respond to each other
     ↓
Voting: majority position identified
     ↓
VIVEKA (Chair) synthesises final recommendation
```

Takes 10–60 seconds depending on model speed.

---

## 16. Personal Operations

### Reminders

| Say | Example |
|---|---|
| `remind me in 10 minutes to check pi5` | One-time reminder |
| `remind me tomorrow at 9am to review the logs` | Specific time |
| `remind me every Friday to backup Brain63` | Weekly recurring |
| `remind me every Monday at 9am to check metrics` | Weekly at time |
| `show reminders` | List all active reminders |
| `delete reminder check pi5` | Delete by partial text |
| `complete reminder backup` | Mark done |

### Tasks

| Say | Example |
|---|---|
| `add task: finish DroneHive PCB` | Add a task |
| `add task review motor controller code` | Same without colon |
| `show my tasks` | Pending tasks |
| `show all tasks` | All tasks |
| `show completed tasks` | Done tasks |
| `complete task DroneHive PCB` | Mark done by partial title |
| `delete task review code` | Remove by partial title |

### Calendar

| Say | Example |
|---|---|
| `what's on my calendar today` | Today's events |
| `today's schedule` | Same |
| `upcoming events` | Next 7 days |
| `what's coming up this week` | Same |
| `create an event Robotics Meeting tomorrow at 3pm` | Create event |
| `schedule team sync Monday at 10am` | Same |
| `delete event Robotics Meeting` | Delete by partial title |

---

## 17. Configuration Reference

### Backend — `.env` File

| Variable | Default | Description |
|---|---|---|
| `OPENWEATHER_API_KEY` | _(empty)_ | Weather queries. Get free key at openweathermap.org |
| `SEARXNG_URL` | _(empty)_ | SearXNG instance URL. Empty = web search disabled |
| `TIMEZONE` | `Asia/Kolkata` | Your local timezone (IANA format) |
| `APP_HOST` | `0.0.0.0` | Backend bind address |
| `APP_PORT` | `8000` | Backend port |
| `SPEACHES_URL` | _(empty)_ | Speaches STT/TTS server. Empty = use local Whisper/Piper |
| `SPEACHES_API_KEY` | `speaches` | API key for Speaches |
| `SPEACHES_STT_MODEL` | faster-whisper-large-v3-turbo | STT model for Speaches |
| `SPEACHES_TTS_MODEL` | Kokoro-82M | TTS model for Speaches |
| `SPEACHES_TTS_VOICE` | `af_aoede` | Voice ID for Kokoro TTS |
| `WHISPER_MODEL_SIZE` | `base` | Local Whisper model size (tiny/base/small/medium/large) |
| `PIPER_MODEL_PATH` | `C:\Piper\models\...` | Path to local Piper TTS model file |
| `PIPER_USE_CUDA` | `false` | Enable CUDA for Piper TTS |
| `CORS_ALLOW_ORIGINS` | localhost:5173,... | Allowed CORS origins, comma-separated |
| `DECISION_TIMEOUT_SECONDS` | `180` | Timeout for MAGI decision mode (council deliberation takes 1–3 min) |
| `API_KEY` | _(empty)_ | Enable API authentication. Empty = auth disabled. See [Section 21](#21-api-key-authentication) |
| `NOTIFICATION_WEBHOOK_URL` | _(empty)_ | Webhook URL for external alerts (Discord/Slack/JSON). Empty = disabled |
| `NOTIFICATION_WEBHOOK_FORMAT` | `discord` | Webhook payload format: `discord`, `slack`, or `json` |
| `NOTIFICATION_EMAIL_HOST` | _(empty)_ | SMTP hostname for email alerts. Empty = email disabled |
| `NOTIFICATION_EMAIL_PORT` | `587` | SMTP port (587 for STARTTLS, 465 for SSL) |
| `NOTIFICATION_EMAIL_USER` | _(empty)_ | SMTP login username |
| `NOTIFICATION_EMAIL_PASS` | _(empty)_ | SMTP login password (use app password for Gmail) |
| `NOTIFICATION_EMAIL_TO` | _(empty)_ | Recipient email address for alerts |
| `NOTIFICATION_MIN_SEVERITY` | `critical` | Minimum alert severity to notify externally: `warning` or `critical` |

### silvia-agent — Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AGENT_NODE_NAME` | system hostname | Name to register with |
| `AGENT_NODE_TYPE` | `server` | Node type |
| `AGENT_NODE_ROLE` | _(empty)_ | Optional role description |
| `AGENT_HOST` | `0.0.0.0` | Bind address |
| `AGENT_PORT` | `8765` | Port |
| `AGENT_ALLOWED_COMMANDS` | `reboot,restart_service,emergency_stop` | Allowed commands |
| `AGENT_BATTERY_PCT` | _(empty)_ | Battery percentage (robotics) |
| `AGENT_POSITION_LAT` | _(empty)_ | GPS latitude (robotics) |
| `AGENT_POSITION_LON` | _(empty)_ | GPS longitude (robotics) |
| `AGENT_ALTITUDE` | _(empty)_ | Altitude in metres (robotics) |
| `AGENT_HEADING` | _(empty)_ | Compass heading (robotics) |
| `AGENT_MISSION_STATE` | _(empty)_ | Current mission state (robotics) |
| `AGENT_IMU_ACCEL_X/Y/Z` | _(empty)_ | Accelerometer data (robotics) |
| `AGENT_IMU_GYRO_X/Y/Z` | _(empty)_ | Gyroscope data (robotics) |

### Models — `backend/config.py`

These are hardcoded defaults. Change in `config.py` to use different models:

| Constant | Default | Used for |
|---|---|---|
| `CONVERSATION_MODEL` | `gemma3:4b` | Main SILVIA conversation |
| `ACTION_GENERATOR_MODEL` | `qwen2.5:3b` | Tool planner |
| `WORLD_MODEL_NAME` | `phi4-mini-reasoning:latest` | World events analysis |
| `SARASWATI_MODEL` | `phi4-mini-reasoning:latest` | MAGI — Logic agent |
| `LAKSHMI_MODEL` | `gemma2:2b` | MAGI — Values agent |
| `DURGA_MODEL` | `qwen2.5:3b` | MAGI — Action agent |
| `VIVEKA_MODEL` | `phi3:mini` | MAGI — Chair/synthesis |

Hermes execution engine models are hardcoded in `backend/app/services/hermes_service.py`:
```python
_EXECUTION_MODELS = ["hermes3", "qwen2.5:7b", "qwen2.5:3b"]
```

---

## 18. Troubleshooting

### Backend won't start

```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check Python deps
pip install -r backend/requirements.txt

# Check port isn't in use
netstat -ano | findstr :8000
```

### "Model not found" errors

```bash
ollama list                         # See what's installed
ollama pull gemma3:4b               # Pull missing model
```

### Telemetry shows "No telemetry received yet"

1. The node has no silvia-agent configured — set an agent URL in the Configure panel.
2. The agent poll hasn't run yet — wait up to 30 seconds.
3. The agent is unreachable — check the agent is running and the URL is correct.

For nodes without an agent, only ICMP probe data is available (no CPU/RAM/disk — just online/offline status).

### Node shows offline but is reachable

The node is likely not reachable via ICMP (ping blocked). Set up silvia-agent on it — the agent poll uses HTTP which bypasses ICMP restrictions. Once the agent responds, the registry updates to `online`.

### Multi-step queries not working

1. Check that `hermes3` (or a fallback model) is installed: `ollama list`
2. Verify the query has more than 8 words and contains a multi-step signal word
3. Check the Event Log panel for `[HERMES]` entries — if absent, the engine isn't being triggered
4. For node queries: ping the node first to establish its registry status

### Weather unavailable

Set `OPENWEATHER_API_KEY` in `.env`. Get a free key at openweathermap.org (free tier allows 1000 calls/day).

### Web search not working

Set `SEARXNG_URL` in `.env` pointing to a running SearXNG instance. Run one locally:
```bash
docker run -d -p 8080:8080 searxng/searxng
```
Then set `SEARXNG_URL=http://localhost:8080`.

### Semantic memory not working

```bash
# Check sqlite-vec is installed
python -c "import sqlite_vec; print('ok')"

# Check nomic-embed-text is available
curl http://localhost:11434/api/tags | python -m json.tool | grep nomic
```

If sqlite-vec import fails: `pip install sqlite-vec`
If nomic-embed-text is missing: `ollama pull nomic-embed-text`

### Voice not working

```bash
# Check voice status
curl http://localhost:8000/api/voice/status
curl http://localhost:8000/api/voice/diagnostics
```

For Speaches: verify it's running on the correct port (not 8000, which SILVIA uses).
For local Whisper: verify `WHISPER_MODEL_SIZE` is set and the model can be downloaded.

### Logs

```
logs/app.log       # Full application log
logs/errors.log    # Errors only
```

Enable debug logging by setting `LOG_LEVEL=DEBUG` before starting the backend.

---

## 19. Telemetry History Charts

SILVIA stores every telemetry reading to a time-series table (`node_telemetry_history`) and displays it as a canvas chart in the expanded node detail view.

### What is Stored

Every poll from the agent poll loop (every 30 seconds) writes a row to `node_telemetry_history`:

| Field | Type | Notes |
|---|---|---|
| `cpu` | float | CPU % |
| `ram` | float | RAM % |
| `disk` | float | Disk % |
| `temperature` | float | °C |
| `battery_pct` | float | Robotics only |
| `altitude` | float | Robotics only |

Data is kept for **7 days** and pruned automatically on each agent poll cycle.

### Viewing the Chart

Expand any node in the Infrastructure panel (click the node card). If the node has CPU, RAM, or battery data, a **History (6h)** sparkline chart appears automatically. No action required.

- Standard nodes: CPU (cyan), RAM (gold), Disk (orange) lines
- Robotics nodes (drone, robot, ESP32, sensor-network): Battery (green), Altitude (purple) lines
- Time labels show the first and last data point timestamps
- Legend shows the most recent value for each metric

### API Access

```bash
# Last 6 hours of telemetry for a node
GET /api/nodes/{node_id}/telemetry/history?hours=6

# Up to 7 days
GET /api/nodes/{node_id}/telemetry/history?hours=168
```

Returns a JSON array, oldest-first:
```json
[
  {"timestamp": "2026-06-11T14:30:00", "cpu": 42.1, "ram": 67.3, "disk": 55.0, ...},
  ...
]
```

---

## 20. Scheduled Autonomous Tasks

SILVIA can run any prompt automatically on a repeating schedule. Tasks execute through the Hermes multi-step engine, exactly like a manually typed command.

### Creating Tasks

**Via chat:**
```
schedule task: check node health every 60 minutes
schedule a task: world brief every 120 minutes
schedule task: show all alerts every 30 minutes
```

**Via the Mission panel (left rail):**
Click **+ New Task**, enter a name, the prompt SILVIA should run, and the interval in minutes.

**Via the API:**
```bash
POST /api/scheduled-tasks
{
  "name": "Node Health Check",
  "prompt": "show all node telemetry",
  "interval_minutes": 60
}
```

### Managing Tasks

**Via chat:**
```
show scheduled tasks        # List all tasks
disable scheduled task node health check
delete scheduled task world brief
```

**Via the Mission panel:** Toggle the green/red dot to pause/resume. Click × to delete.

**Via the API:**
```bash
GET    /api/scheduled-tasks              # List all
PUT    /api/scheduled-tasks/{id}        # Update (name, prompt, interval_minutes, enabled)
DELETE /api/scheduled-tasks/{id}        # Delete
```

### How Execution Works

- A background loop checks for due tasks every **60 seconds**
- When a task is due (`next_run ≤ now`), it runs via the Hermes execution engine with `session_id="scheduled-task"`
- The result is saved as `last_result` on the task
- `next_run` advances by `interval_minutes` after each run
- Results appear in the Event Log panel

### Persistence

Scheduled tasks are stored in SQLite (`data/cmdctr.db`) and survive backend restarts. Tasks that were due during a downtime window run at the next check after startup.

---

## 21. API Key Authentication

SILVIA's backend API can be protected with an API key. When enabled, all requests must supply the key or be rejected with `401 Unauthorized`.

### Enabling Auth

Add to `.env`:
```env
API_KEY=your-secret-key-here
```

Restart the backend. Auth is now active.

### Bypasses (always allowed without a key)

- Requests from **localhost** (`127.0.0.1` / `::1`) always bypass auth — local SILVIA use is unaffected
- Paths: `/health`, `/docs`, `/openapi.json`, `/redoc`

### Providing the Key

**HTTP requests — header:**
```bash
curl -H "X-API-Key: your-secret-key-here" http://your-host:8000/api/nodes
# or
curl -H "Authorization: Bearer your-secret-key-here" http://your-host:8000/api/nodes
```

**WebSocket — query parameter:**
```
ws://your-host:8000/api/ws/events?api_key=your-secret-key-here
```

### Disabling Auth

Remove `API_KEY` from `.env` (or set it to empty string). All requests will pass without a key. This is the default and is backwards-compatible with any existing scripts or integrations.

### Security Notes

- Auth is transport-level only. Use HTTPS (reverse proxy with TLS) if exposing SILVIA over the internet.
- The localhost bypass means you don't need to update local scripts or the frontend when auth is enabled — the frontend connects from the same machine.
- Never commit your `.env` file — `.gitignore` already excludes it.


---

## 22. Mission Control — Proactive Intelligence

Phase 9 added a proactive intelligence layer. SILVIA no longer only responds to questions — it aggregates real data and surfaces actionable information.

### Design Principle

Every recommendation must trace to a real data source:
- **Brain63** — personal knowledge vault
- **Projects** — project registry
- **Tasks** — pending/completed task list
- **Calendar** — scheduled events
- **Reminders** — timed notifications with escalation tracking
- **Watch Officer** — active infrastructure alerts
- **Nodes** — live telemetry from registered machines

**Unknown > Hallucinated. Always.** If data does not exist, SILVIA says so. It never invents project status, node state, or deadlines.

### Morning Briefing

Command:  /  / 

Data sources polled:
1. Active + blocked projects (sorted by priority)
2. High-priority pending tasks
3. Due reminders
4. Today Calendar events
5. Active Watch Officer alerts (critical + warning)
6. Offline nodes

The LLM synthesizes the structured data into a natural-language briefing. If the LLM is unavailable, the raw structured data is returned instead.

API: 

### Evening Review

Command:  /  / 

Data sources polled:
1. Tasks completed today
2. Projects with activity today
3. Watch Officer alerts created today
4. Outstanding: pending tasks, overdue reminders, offline nodes

API: 

### Daily Focus

Command:  /  / 

Priority-ranked using 6 tiers:
1. Critical Watch Officer alerts (tier 0)
2. Overdue reminders (tier 1)
3. High-priority pending tasks (tier 2)
4. Active critical/high projects idle 3+ days (tier 3-4)
5. Offline nodes (tier 5)
6. Normal-priority tasks (tier 6)

Up to 10 items returned. The LLM writes the final recommendation with reasoning.

API: 

### Weekly Review

Command:  /  / 

Covers tasks completed, projects active, upcoming calendar and reminders, and alert history from the past 7 days.

API: 

### Forgotten Items Scan

Command:  /  / 

Scans for:
- **Stale projects**: active/blocked with no activity in 14+ days
- **Forgotten tasks**: pending tasks created 7+ days ago
- **Overdue reminders**: trigger_at in the past
- **Old unresolved alerts**: critical/warning active for 1+ days

API: 

### Project Health

Command:  / 

Per-project health report: health tier, idle days, task count, related reminders and alerts.

API: 

---

## 23. Project Registry

Phase 8 added a first-class Project entity.

### Default Projects (seeded on first run)

| Project | Priority | Status |
|---|---|---|
| CMD-CTR | critical | active |
| DroneHive | high | active |
| University | high | active |
| Cyberdeck | normal | active |
| Brain63 | normal | active |
| KOI | normal | paused |

### Project Fields

| Field | Description |
|---|---|
|  | Display name |
|  | active / paused / blocked / complete |
|  | critical / high / normal / low |
|  | Optional search key for Brain63 vault lookup |
|  | Free-text notes |
|  | Timestamp of most recent recorded activity |

### API



---

## 24. Phase History and Roadmap

### Completed Phases

| Phase | Feature | Status |
|---|---|---|
| 1 | Voice pipeline (wake word, VAD, STT, TTS, hands-free loop) | complete |
| 2 | Brain63 vault integration (read-only), semantic memory | complete |
| 3 | Node registry, live telemetry probing | complete |
| 4 | Watch Officer, external notifications, telemetry history charts | complete |
| 5A | silvia-agent node protocol | complete |
| 5B | Personal Ops: Tasks, Reminders, Calendar | complete |
| 5C | Watch Officer rules engine | complete |
| 6A-B | World Intelligence, Hermes multi-step execution | complete |
| 7A-C | Robotics C2, bulk commands, notifications | complete |
| 8 | Mission Control, Project Registry, Scheduled Tasks, API auth | complete |
| 9 | Proactive intelligence, Evening Review, Reminder escalation, WO intelligence | complete |
| 10 | Service Registry and capability execution | complete |
| 11 | Desktop Control and Local File Awareness | complete |

### Background Loop Architecture



### Data Storage (data/cmdctr.db)

| Table | Contents |
|---|---|
| nodes | Node registry |
| node_telemetry_history | 7-day rolling telemetry |
| watch_alerts | Watch Officer alerts |
| reminders | Timed reminders |
| tasks | Task list |
| calendar_events | Calendar |
| projects | Project registry |
| scheduled_tasks | Autonomous scheduled tasks |
| conversation_history | Per-session chat |
| facts | Key-value facts |
| semantic_index | sqlite-vec vector index |
| trusted_locations | Registered folders and project paths |
| app_registry | Registered launchable applications |
| file_index | Indexed files from trusted locations |

All tables created automatically on first start via CREATE TABLE IF NOT EXISTS. New columns added via runtime migrations.

---

## 22. Mission Control — Proactive Intelligence

Phase 9 added a proactive intelligence layer. SILVIA no longer only responds to questions — it aggregates real data and surfaces actionable information.

### Design Principle

Every recommendation must trace to a real data source:
- **Brain63** — personal knowledge vault
- **Projects** — project registry
- **Tasks** — pending/completed task list
- **Calendar** — scheduled events
- **Reminders** — timed notifications with escalation tracking
- **Watch Officer** — active infrastructure alerts
- **Nodes** — live telemetry from registered machines

**Unknown > Hallucinated. Always.** If data does not exist, SILVIA says so. It never invents project status, node state, or deadlines.

### Morning Briefing

Command: `morning briefing` / `good morning` / `daily briefing`

Data sources polled:
1. Active + blocked projects (sorted by priority)
2. High-priority pending tasks
3. Due reminders
4. Today's calendar events
5. Active Watch Officer alerts (critical + warning)
6. Offline nodes

The LLM synthesizes the structured data into a natural-language briefing. If the LLM is unavailable, the raw structured data is returned instead.

API: `GET /api/mission/briefing`

### Evening Review

Command: `evening review` / `end of day` / `what did I accomplish today`

Data sources polled:
1. Tasks completed today
2. Projects with activity today
3. Watch Officer alerts created today
4. Outstanding: pending tasks, overdue reminders, offline nodes

API: `GET /api/mission/evening`

### Daily Focus

Command: `what should I focus on today` / `daily focus` / `what should I work on`

Priority-ranked using 6 tiers:
1. Critical Watch Officer alerts (tier 0)
2. Overdue reminders (tier 1)
3. High-priority pending tasks (tier 2)
4. Active critical/high projects idle 3+ days (tier 3-4)
5. Offline nodes (tier 5)
6. Normal-priority tasks (tier 6)

Up to 10 items returned. The LLM writes the final recommendation with reasoning.

API: `GET /api/mission/focus`

### Weekly Review

Command: `weekly review` / `how was my week` / `week in review`

Covers tasks completed, projects active, upcoming calendar and reminders, and alert history from the past 7 days.

API: `GET /api/mission/weekly`

### Forgotten Items Scan

Command: `what am I forgetting` / `stale projects` / `what's falling behind`

Scans for:
- **Stale projects**: active/blocked with no activity in 14+ days
- **Forgotten tasks**: pending tasks created 7+ days ago
- **Overdue reminders**: trigger_at in the past
- **Old unresolved alerts**: critical/warning active for 1+ days

API: `GET /api/mission/forgotten`

### Project Health

Command: `project health` / `how are my projects`

Per-project health report: health tier, idle days, task count, related reminders and alerts.

API: `GET /api/mission/health`

---

## 23. Project Registry

Phase 8 added a first-class Project entity.

### Default Projects (seeded on first run)

| Project | Priority | Status |
|---|---|---|
| CMD-CTR | critical | active |
| DroneHive | high | active |
| University | high | active |
| Cyberdeck | normal | active |
| Brain63 | normal | active |
| KOI | normal | paused |

### Project Fields

| Field | Description |
|---|---|
| `name` | Display name |
| `status` | active / paused / blocked / complete |
| `priority` | critical / high / normal / low |
| `brain63_key` | Optional search key for Brain63 vault lookup |
| `notes` | Free-text notes |
| `last_activity` | Timestamp of most recent recorded activity |

### API

```
GET    /api/projects              # List all projects
POST   /api/projects              # Create project
GET    /api/projects/{id}         # Get project
PUT    /api/projects/{id}         # Update project
DELETE /api/projects/{id}         # Delete project
POST   /api/projects/{id}/touch   # Update last_activity to now
```

---

## 24. Desktop Control & Local File Awareness

Phase 11 adds workstation awareness while keeping the control boundary narrow and safe.

### Trusted Locations

Trusted locations map project and folder names to real paths. Each entry stores a name, path, aliases, tags, description, and an `exists` flag.

Seeded locations include CMD-CTR, Brain63, DroneHive, Cyberdeck, Downloads, Documents, Desktop, GitHub, University, and Internship.

Commands:

- `open CMD-CTR folder`
- `where is Brain63`
- `show trusted locations`
- `list CMD-CTR files`

### File Awareness

The `file_index` table stores indexed files from trusted locations. It refreshes automatically when search or recent-file commands run and the location index is stale.

Commands:

- `find STL files`
- `find PCB files`
- `find python files in CMD-CTR`
- `find files related to nighthawk`
- `show recent files`

### Application Registry

Registered applications store name, executable, aliases, category, and description. SILVIA checks availability before showing launch buttons or launching from chat.

Commands:

- `open VS Code`
- `launch KiCad`
- `start Fusion 360`
- `open browser`
- `show installed apps`

### Safety Boundary

Allowed actions are folder open, file search, recent-file display, app launch, and registry listing. Delete, rename, move, overwrite, autonomous clicking, and autonomous typing are intentionally out of scope.

### API

```
GET  /api/desktop/locations
POST /api/desktop/locations
GET  /api/desktop/files
GET  /api/desktop/recent-files
POST /api/desktop/open/location
GET  /api/desktop/apps
POST /api/desktop/apps
POST /api/desktop/open/app
```

---

## 24. Phase History and Roadmap

### Completed Phases

| Phase | Feature | Status |
|---|---|---|
| 1 | Voice pipeline (wake word, VAD, STT, TTS, hands-free loop) | complete |
| 2 | Brain63 vault integration (read-only), semantic memory | complete |
| 3 | Node registry, live telemetry probing | complete |
| 4 | Watch Officer, external notifications, telemetry history charts | complete |
| 5A | silvia-agent node protocol | complete |
| 5B | Personal Ops: Tasks, Reminders, Calendar | complete |
| 5C | Watch Officer rules engine | complete |
| 6A-B | World Intelligence, Hermes multi-step execution | complete |
| 7A-C | Robotics C2, bulk commands, notifications | complete |
| 8 | Mission Control, Project Registry, Scheduled Tasks, API auth | complete |
| 9 | Proactive intelligence, Evening Review, Reminder escalation, WO intelligence | complete |
| 10 | Service Registry and capability execution | complete |
| 11 | Desktop Control and Local File Awareness | complete |

### Background Loop Architecture

```
lifespan startup (application.py)
  node_probe_loop          60s  - ICMP ping all nodes
  agent_poll_loop          30s  - HTTP poll agent nodes
  watch_officer_loop       30s  - threshold alerts, duration, pattern detection
  reminder_loop            60s  - fire due reminders as Watch Officer alerts
  reminder_escalation_loop 300s - 24h warning, 72h critical escalation
  scheduled_task_loop      60s  - run due tasks via Hermes
```

### Data Storage (data/cmdctr.db)

| Table | Contents |
|---|---|
| nodes | Node registry |
| node_telemetry_history | 7-day rolling telemetry |
| watch_alerts | Watch Officer alerts |
| reminders | Timed reminders |
| tasks | Task list |
| calendar_events | Calendar |
| projects | Project registry |
| scheduled_tasks | Autonomous scheduled tasks |
| conversation_history | Per-session chat |
| facts | Key-value facts |
| semantic_index | sqlite-vec vector index |
| trusted_locations | Registered folders and project paths |
| app_registry | Registered launchable applications |
| file_index | Indexed files from trusted locations |

All tables created automatically on first start via CREATE TABLE IF NOT EXISTS. New columns are added via runtime ALTER TABLE migrations with no manual migration scripts required.

---

## 25. Telegram Chat Bridge

SILVIA can receive and reply to messages via a Telegram bot, using the same chat pipeline as the web UI.

### How it works

```
Telegram message
  → Telegram Bot API (polling)
  → telegram_bridge.py
  → SILVIA conversation pipeline (same as /api/assistant/chat)
  → Telegram reply
```

Every Telegram message is forwarded as a normal SILVIA chat request with `source=telegram`. All commands that work in the web UI work in Telegram.

### Setup

**Step 1 — Create a Telegram bot**

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCDEFabcdef...`)

**Step 2 — Find your Telegram user ID**

1. Search for **@userinfobot** on Telegram
2. Send it any message — it replies with your user ID (a number like `987654321`)

**Step 3 — Configure .env**

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456789:ABCDEFabcdef...
TELEGRAM_ALLOWED_USER_IDS=987654321
```

Multiple allowed users (comma-separated):
```env
TELEGRAM_ALLOWED_USER_IDS=987654321,112233445
```

**Step 4 — Install dependency**

```bash
pip install 'python-telegram-bot>=21'
```

Or reinstall all requirements:
```bash
pip install -r backend/requirements.txt
```

**Step 5 — Restart SILVIA**

The bridge starts automatically when `TELEGRAM_ENABLED=true`. You'll see in the logs:
```
Telegram bridge started — polling active, 1 allowed user(s)
```

### Security

> **WARNING:** Only add your own Telegram user ID to `TELEGRAM_ALLOWED_USER_IDS`. Anyone whose ID is not in this list gets `Unauthorized.` and their messages are discarded. Never share your bot token publicly.

- `TELEGRAM_ALLOWED_USER_IDS` is checked on every message before any processing
- Unknown users receive only the string `Unauthorized.` — no other information is returned
- Your bot token must never be committed to git (it's in `.env` which is in `.gitignore`)

### Confirmation flow

Commands that normally require confirmation in the web UI (destructive actions, commands that execute on nodes) behave the same way in Telegram. SILVIA will reply with the confirmation prompt, and you can respond:

```
you: reboot nighthawk
SILVIA: ⚠️ Are you sure you want to reboot Nighthawk? Reply yes to confirm or cancel to abort.
you: yes
SILVIA: Sending reboot command to Nighthawk...
```

### Singleton Guard

Only **one process** may poll a given Telegram bot token at a time. Starting a second poller produces a `409 Conflict` from the Telegram API. SILVIA enforces this with three layers:

1. **PID lock file** (`.runtime/telegram.lock`) — before starting the poller, SILVIA writes its PID and timestamp to the lock file. If a lock already exists and the PID is still alive, startup is skipped.
2. **Uvicorn reload detection** — when running with `uvicorn --reload`, the parent supervisor process skips polling so only the child worker polls.
3. **Graceful Conflict handling** — if a `409 Conflict` occurs during polling (e.g., another instance took over), the bridge logs once, stops polling, releases the lock, and does **not** retry.

Stale locks from force-killed processes are automatically detected using `GetExitCodeProcess` on Windows (or `os.kill(pid, 0)` on Unix).

### Status endpoint

```
GET /api/telegram/status
```

Returns:
```json
{
  "enabled": true,
  "configured": true,
  "running": true,
  "pid": 12345,
  "started_at": "2026-06-19T15:30:00Z",
  "allowed_users_count": 1,
  "lock_held": true,
  "lock_pid": 12345
}
```

### Startup behavior

| Condition | Result |
|---|---|
| `TELEGRAM_ENABLED=false` | Bridge does not start. SILVIA continues normally. |
| `TELEGRAM_ENABLED=true`, `TELEGRAM_BOT_TOKEN` missing | Error logged, bridge skipped, SILVIA continues. |
| `TELEGRAM_ALLOWED_USER_IDS` empty | Error logged, bridge refuses to start (open bot safety). |
| Lock file exists, PID alive | Skipped — another instance is already polling. |
| Lock file exists, PID dead | Stale lock cleared, bridge starts. |
| Uvicorn reload parent process | Skipped — only the worker process polls. |
| All configured correctly | Bridge starts, polling begins, log confirms. |

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_ENABLED` | `false` | Set `true` to enable the bridge |
| `TELEGRAM_BOT_TOKEN` | — | Bot token from BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | — | Comma-separated Telegram user IDs to whitelist |
| `TELEGRAM_SESSION_ID` | `telegram` | Base session ID prefix (each user gets `telegram_{user_id}`) |

---

## 26. Capability Verification Layer

Anti-hallucination guard that prevents SILVIA from fabricating infrastructure state. Every response about system state must come from verified tool output — never from LLM inference.

### Problem it solves

Without this layer, SILVIA could respond to a bare `hostname` command by generating a plausible-sounding hostname from LLM inference — a fabrication indistinguishable from real data. After opening an SSH terminal to a node, she could fabricate answers about that node's state even though she has no command channel to the SSH window.

### How it works

```
User query
  ↓
Verification Interceptor (before social engine)
  ├─ Bare infra command (hostname, uptime, docker ps)? → Refuse, suggest "run X"
  ├─ SSH context exists? → Explain SSH terminal limitation
  └─ Pass → continue normal routing
  ↓
Normal routing (fast-paths, social, tools, planner)
  ↓
LLM Fallback Guard (before free-text LLM)
  ├─ Infra state query about a node? → Refuse
  └─ Pass → LLM generates response
```

### Intercepted commands

Bare system commands that require actual execution output:

`hostname`, `uptime`, `whoami`, `uname`, `df`, `free`, `top`, `htop`, `ps`, `docker ps`, `docker images`, `systemctl status`, `journalctl`, `ip addr`, `ifconfig`, `netstat`, `ss`, `lsblk`, `mount`, `lscpu`

### SSH terminal awareness

When SILVIA opens an SSH terminal (e.g., via `ssh nighthawk`), she records that a terminal window was opened but acknowledges she has **no command channel** to it. Subsequent infrastructure queries return:

> I opened an SSH terminal to **nighthawk**, but I don't have a command channel to run `hostname` on it remotely. Run the command in the SSH terminal window.
>
> To run `hostname` on **this machine**, say: **run hostname**

### Source attribution

All verified command output includes source attribution:

```
Node: local | Source: run_command | Tool: run_command | Executed: yes | Timestamp: 2026-06-19T15:30:00Z
```

### Key files

| File | Purpose |
|---|---|
| `backend/app/services/capability_verification.py` | `CapabilityVerificationService`, `CapabilityExecutionResult`, infrastructure query regex, SSH terminal tracking, LLM fallback guard |
| `backend/app/services/conversation_state.py` | Infrastructure terms in `_EXEC_NOUN_VETO` to prevent social routing |
| `backend/app/services/conversation_service.py` | Verification interceptor, LLM guard, SSH terminal recording |

---

## 27. Workflow Execution Verification

Ensures that workflow approval always triggers actual tool execution — never a generic LLM-generated response.

### Problem it solves

Previously, approving a workflow like `approve WF-019` (for `ssh nighthawk`) would update the workflow status to "approved" but not execute anything. The response was generated by the LLM ("Okay, approved. Let's see what nighthawk is up to.") — pure fabrication with no real action taken. The tool's try/except block silently swallowed exceptions and returned `None`, which was treated as "no response" rather than "execution failure".

### How it works

All three workflow approval paths now share a single verified execution method:

```python
_execute_approved_workflow(code, tool_name, tool_args)
```

This method:

1. Marks the workflow as **executing** before the tool runs
2. Calls `_run_tool_bypassing_safety()` (safety was already checked during workflow creation)
3. If the tool returns `None` (swallowed exception) → marks **failed** with "Tool returned no result"
4. If `_last_tool_ok` is `False` or the response title contains "Failed" → marks **failed**
5. Only if both checks pass → marks **completed**
6. Stores a structured execution result in the workflow DB

### Three approval paths

| Path | Trigger | Example |
|---|---|---|
| Explicit approve | `approve WF-XXX` | `approve WF-028` |
| Yes on pending | `yes`, `yeah`, `sure`, `ok` | `yes` after seeing WF prompt |
| Approve all | `approve all workflows` | Bulk approval |

All three paths call `_execute_approved_workflow()` — no path can skip verification.

### Workflow states

```
draft → pending_review → approved → executing → completed
                      → rejected              → failed
                      → cancelled
```

### Execution result format

Stored in the `execution_result` column of the `workflows` table:

```json
{
  "executed": true,
  "success": true,
  "executor": "ssh_node",
  "raw_output": "SSH terminal opened — Nighthawk as ishaan.",
  "error": null
}
```

For failures:

```json
{
  "executed": true,
  "success": false,
  "executor": "ssh_node",
  "raw_output": "Node 'fakenode' not found in registry.",
  "error": "Tool reported failure"
}
```

### SSH failure handling

SSH handler failure paths now explicitly set `_last_tool_ok = False` for:
- Node name not provided
- Node not found in registry
- Node has no address configured
- Node has no SSH username configured

### Key files

| File | Purpose |
|---|---|
| `backend/app/services/conversation_service.py` | `_execute_approved_workflow()`, all three approval paths, SSH failure flags |
| `backend/app/services/workflow_engine.py` | `mark_executing()`, `mark_completed()`, `mark_failed()`, fixed `_audit()` |
| `backend/app/services/capability_verification.py` | `CapabilityExecutionResult` dataclass |

---

## 28. Stability Controls

Configuration and commands for stabilizing SILVIA and diagnosing issues.

### SSH Approval Control

By default, SSH opens terminals **directly** without requiring workflow approval.

```env
SSH_REQUIRES_APPROVAL=false   # default — SSH opens directly
SSH_REQUIRES_APPROVAL=true    # require approval workflow for SSH
```

Commands that work directly when approval is disabled:
- `ssh nighthawk` / `connect nighthawk` / `open ssh to nighthawk`
- If terminal launch fails, SILVIA shows the exact error (never fabricates success)

### Safe Mode

Disables all proactive/background features while keeping read-only functionality working.

```env
SILVIA_SAFE_MODE=true
```

When active:
- Reminder notifications paused
- Reminder escalation paused
- Scheduled autonomous tasks paused
- Read-only features (boards, queries, status) still work
- Workflow data-deletion protection still active

### System Diagnostics

```
deep system check
system diagnostics
health check
```

Checks every subsystem and reports OK / Warning / Failed / Disabled / Not Configured:
Database, Ollama, Node Registry, Service Registry, Capability Registry, Hardware Inventory, Hardware Projects, Project Registry, Gmail, Calendar, Telegram, Reminders, Tasks, Workflow Engine, Approval Engine, Observability Ledger, Knowledge Graph, Project Memory, Digital Twin, Engineering Planner, Brain63, Memory Manager, Brain Steward, Workspace Awareness, Workspace Restore, SSH Profiles, Voice Pipeline, Watch Officer, Fleet Manager.

### Reminder Management

```
show reminder diagnostics    — active, due, stuck, recurring counts
dismiss reminder <query>     — complete + silence Watch Officer alert
clear stuck reminders        — clear all one-time reminders past due
pause reminders              — temporarily stop all reminder notifications
resume reminders             — re-enable reminder notifications
```

### Startup Health Summary

On every backend startup, SILVIA prints a health summary to the log:

```
SILVIA Startup Health
========================================
  Database:     OK (44 tables)
  Ollama:       OK (18 models)
  Gmail:        Not configured
  Telegram:     OK (polling)
  Reminders:    OK (0 active)
  SSH:          OK (approval=disabled)
  Nodes:        OK (6 registered, 3 online)
========================================
```

### Troubleshooting

| Problem | Command | Fix |
|---|---|---|
| SSH stuck behind approval | Check `.env` | Set `SSH_REQUIRES_APPROVAL=false` |
| Reminders stuck/repeating | `clear stuck reminders` | Clears all past-due one-time reminders |
| Reminder won't stop | `dismiss reminder <text>` | Completes reminder + resolves all alerts |
| System unstable | `SILVIA_SAFE_MODE=true` | Disables proactive features |
| Unknown subsystem failure | `deep system check` | Full diagnostic report |
| Telegram 409 Conflict | Restart backend | Singleton lock auto-clears stale PIDs |
| SSH shows "Username Required" | `set ssh username for <node> to <user>` | Persists SSH profile |
