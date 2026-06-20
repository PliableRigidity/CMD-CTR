# SILVIA — Personal AI Operating System

> **S**trategic **I**ntelligence, **L**ogistics, **V**oice & **I**ntegrated **A**ssistant

SILVIA is a locally-hosted, voice-enabled AI operating system for engineers, makers, and power users. All inference runs on your machine via Ollama. No cloud required. No data leaves your network.

---

## What is SILVIA?

SILVIA is not a chatbot. It is a personal command center that integrates your entire digital and physical environment:

- **Talk to your infrastructure** — check CPU load, SSH into nodes, send commands to drones and robots
- **Control your desktop** — launch apps, close processes, search files, open KiCad projects
- **Manage hardware projects** — track inventory, check build readiness, log orders, import BOMs
- **Stay organized** — tasks, reminders, calendar events, project health reports
- **Monitor proactively** — Watch Officer alerts on telemetry spikes and node outages
- **Use your voice** — full wake word → STT → LLM → TTS pipeline, everything local

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     BROWSER / UI                         │
│  React SPA (Vite) — Command Center · Hardware Board      │
│  Infrastructure · Mission Panel · Voice Interface        │
└─────────────────────┬────────────────────────────────────┘
                      │  HTTP REST + WebSocket
┌─────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend :8000                   │
│                                                          │
│  ┌────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│  │  Planner   │  │ HW Assistant    │  │ Node/Service │  │
│  │ qwen2.5:3b │  │ (regex router)  │  │  Registry   │  │
│  └─────┬──────┘  └────────┬────────┘  └──────┬───────┘  │
│        │                  │                  │           │
│  ┌─────▼──────────────────▼──────────────────▼────────┐  │
│  │                  Tool Layer                        │  │
│  │  Desktop · Node · Watch · Tasks · Hardware · Voice │  │
│  └─────────────────────────────┬──────────────────────┘  │
│                                │                         │
│  ┌─────────────────────────────▼──────────────────────┐  │
│  │              SQLite Databases                      │  │
│  │   nodes.db  ·  hardware.db  ·  missions.db         │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                      │  Ollama HTTP API
┌─────────────────────▼────────────────────────────────────┐
│                   Local LLMs (Ollama)                    │
│   gemma3:4b · phi4-mini-reasoning · qwen2.5:3b           │
└──────────────────────────────────────────────────────────┘
```

---

## Feature Matrix

| System | Status | Description |
|---|---|---|
| Voice Pipeline | ✅ | Wake word → STT → LLM → TTS, fully local |
| Desktop Awareness | ✅ | App discovery, file indexing, launch preferences |
| Node Registry | ✅ | Register, monitor, and command remote machines |
| Service Registry | ✅ | Map services (NAS, media, robot) to nodes |
| Capability Registry | ✅ | Execute named capabilities (media.play, motion.forward) |
| Watch Officer | ✅ | Telemetry alert rules with info/warning/critical severity |
| SSH Terminal Launch | ✅ | Opens Windows Terminal tab for any registered node |
| Hardware Inventory | ✅ | Parts registry with auto-categorization |
| Hardware Projects | ✅ | Project-part links with 10-status model |
| Build Readiness | ✅ | Check if current stock covers all project requirements |
| Procurement Engine | ✅ | Low-stock alerts, reorder thresholds, delivery tracking |
| BOM Import | ✅ | CSV and KiCad BOM import |
| Vision Inventory | ✅ | Image → component detection → inventory update |
| Tasks & Calendar | ✅ | Tasks, reminders, calendar events |
| Project Registry | ✅ | Maker project tracking with health reports |
| Semantic Memory | ✅ | Search past conversation history by meaning |
| Brain63 Integration | ✅ | Read-only Obsidian vault access |
| Hermes Engine | ✅ | Multi-step autonomous task execution |
| Scheduled Tasks | ✅ | Recurring background tasks |
| Morning Briefing | ✅ | Daily status from live data — no hallucination |
| Multi-Brain Debate | ✅ | SARASWATI + LAKSHMI + DURGA consensus decisions |
| External Notifications | 🔜 | Discord/email for Watch Officer alerts |
| Telemetry History | 🔜 | Historical charts per node |
| Fleet Commands | 🔜 | "Land all drones" — multi-node simultaneous |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com/) installed and running
- Windows 10/11 (macOS/Linux: core features work, desktop control is Windows-only)

### 1. Clone and install

```bash
git clone https://github.com/PliableRigidity/CMD-CTR.git
cd CMD-CTR

# Backend dependencies
pip install -r backend/requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Pull Ollama models

```bash
ollama pull gemma3:4b           # Main conversation model
ollama pull phi4-mini-reasoning # Multi-brain reasoning
ollama pull qwen2.5:3b          # Tool planning

# Optional — for local vision analysis
ollama pull llava
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your settings (see Configuration section)
```

### 4. Run

```bash
# Terminal 1 — Backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (dev)
cd frontend && npm run dev
```

Open `http://localhost:5173` in your browser.

For production frontend: `cd frontend && npm run build` → serves from `dist/` on port 8001.

---

## Configuration

Create `.env` in the project root:

```env
# ── Required ──────────────────────────────────────────
OPENWEATHER_API_KEY=your_key_here
TIMEZONE=Asia/Kolkata

# ── Brain63 (Obsidian vault — READ-ONLY) ──────────────
BRAIN63_VAULT_PATH=C:\Users\YourName\Documents\GitHub\Brain63

# ── Voice: Speaches (optional, recommended) ───────────
# Speaches must be on a different port than SILVIA (8000 conflicts)
SPEACHES_URL=http://localhost:9000
SPEACHES_STT_MODEL=rtlingo/mobiuslabsgmbh-faster-whisper-large-v3-turbo
SPEACHES_TTS_MODEL=speaches-ai/Kokoro-82M-v1.0-ONNX
SPEACHES_TTS_VOICE=af_aoede

# ── Vision (Phase 12F) ────────────────────────────────
# Option A: Anthropic Claude Vision (best accuracy)
ANTHROPIC_API_KEY=sk-ant-...
VISION_PROVIDER=auto             # auto | anthropic | ollama
VISION_MODEL_ANTHROPIC=claude-haiku-4-5-20251001
# Option B: Ollama (no key needed, pull llava first)
VISION_MODEL_OLLAMA=llava
VISION_CONFIDENCE_THRESHOLD=0.65

# ── Notifications (optional) ──────────────────────────
NOTIFICATION_WEBHOOK_URL=https://discord.com/api/webhooks/...
NOTIFICATION_WEBHOOK_FORMAT=discord   # discord | slack | json
NOTIFICATION_MIN_SEVERITY=critical    # warning | critical

# ── Authentication (optional) ─────────────────────────
# Leave empty for localhost-only use (no auth required)
API_KEY=

# ── Web search (optional) ─────────────────────────────
SEARXNG_URL=http://localhost:8080
```

---

## Directory Structure

```
CMD-CTR/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   │   ├── hardware.py   # Hardware Board API (40+ endpoints)
│   │   │   ├── nodes.py      # Node registry API
│   │   │   └── ...
│   │   ├── core/             # App startup, auth middleware, WebSocket
│   │   ├── models/           # Pydantic request/response schemas
│   │   ├── orchestration/    # Assistant router and mode dispatch
│   │   ├── services/         # All business logic
│   │   │   ├── hardware_service.py         # Inventory/project/order DB
│   │   │   ├── hardware_assistant_service.py # Chat-based HW control
│   │   │   ├── hardware_vision_service.py  # Image analysis (Phase 12F)
│   │   │   ├── node_service.py             # Node registry DB
│   │   │   ├── watch_service.py            # Watch Officer alerts
│   │   │   ├── mission_service.py          # Tasks, reminders, calendar
│   │   │   ├── hermes_service.py           # Multi-step task execution
│   │   │   ├── conversation_service.py     # LLM conversation loop
│   │   │   └── semantic_memory_service.py  # Conversation search
│   │   ├── tools/
│   │   │   ├── planner.py    # Tool dispatch (all SILVIA commands)
│   │   │   ├── node_tool.py  # Node operations
│   │   │   └── time_tool.py  # Time utilities
│   │   └── world/            # RSS, world model
│   ├── voice/                # STT, TTS, VAD, wake word detector
│   ├── config.py             # All configuration constants
│   ├── main.py               # FastAPI entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # UI panels and widgets
│   │   ├── lib/api.js        # All backend API calls (single source of truth)
│   │   └── pages/            # Top-level page components
│   └── package.json
├── docs/                     # All documentation
├── prompts/                  # LLM system prompts (SARASWATI, LAKSHMI, DURGA)
└── .env                      # Local config — never commit this file
```

---

## Documentation Index

| Document | What it covers |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | System diagrams, data flow, LLM routing |
| [Features](docs/Features.md) | Every feature with components and examples |
| [Commands](docs/Commands.md) | Complete command reference by category |
| [Hardware Board](docs/HARDWARE_BOARD.md) | Inventory, projects, orders, BOM, Vision |
| [Hardware Assistant](docs/HardwareAssistant.md) | Chat routing, all HW commands |
| [Infrastructure](docs/Infrastructure.md) | Nodes, telemetry, Watch Officer, SSH |
| [Node Registry](docs/NodeRegistry.md) | Node schema, types, agent protocol |
| [Service Registry](docs/ServiceRegistry.md) | Services mapped to nodes |
| [Capability Registry](docs/CapabilityRegistry.md) | Executable capabilities |
| [Voice System](docs/VoiceSystem.md) | Wake word, STT, TTS, VAD |
| [Desktop Awareness](docs/DESKTOP_AWARENESS.md) | App control, file search |
| [Project Registry](docs/ProjectRegistry.md) | Maker project tracking |
| [Inventory Registry](docs/InventoryRegistry.md) | Hardware inventory system |
| [Roadmap](docs/Roadmap.md) | Completed phases and future plans |
| [Developer Guide](docs/DeveloperGuide.md) | How to add tools, services, endpoints |
| [Troubleshooting](docs/Troubleshooting.md) | Common issues and fixes |

---

## Known Limitations

- **Windows-primary** — app discovery and SSH terminal launch use Win32 APIs
- **Voice requires microphone** — wake word detection uses the default audio input device
- **Vision requires setup** — needs either `ANTHROPIC_API_KEY` + `pip install anthropic` or `ollama pull llava`
- **Brain63 is read-only** — SILVIA cannot create or edit Obsidian notes
- **No cloud backup** — all data lives in local SQLite files (`backend/*.db`)
- **Ollama must be running** — all LLM inference fails gracefully if Ollama is offline

---

## Roadmap Summary

| Phase | Status | Description |
|---|---|---|
| 1–4 | ✅ Done | Core assistant, multi-brain debate, voice pipeline |
| 5–7 | ✅ Done | Nodes, Watch Officer, Hermes engine, robotics protocol |
| 8–9 | ✅ Done | Proactive intelligence, morning briefing |
| 10 | ✅ Done | Universal node capability layer |
| 12A–12F | ✅ Done | Hardware Board — inventory through vision analysis |
| 13 | 🔜 Planned | Historical telemetry charts |
| 14 | 🔜 Planned | Fleet commands (multi-node simultaneous) |
| 15 | 🔜 Planned | External notifications (Discord/email) |
| 16 | 🔜 Planned | Full API authentication |

---

## License

MIT — see [LICENSE](LICENSE)

*Built by PliableRigidity. SILVIA is a personal project.*
