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
- **Missions** — task and reminder management
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
| `DECISION_TIMEOUT_SECONDS` | `45` | Timeout for MAGI decision mode |

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
