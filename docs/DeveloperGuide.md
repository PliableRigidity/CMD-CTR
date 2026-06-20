# Developer Guide

Everything a developer needs to understand SILVIA's architecture, add new features, and extend existing systems.

---

## Table of Contents

1. [Directory Structure](#directory-structure)
2. [Running Locally](#running-locally)
3. [Backend Architecture](#backend-architecture)
4. [Frontend Architecture](#frontend-architecture)
5. [Adding a New SILVIA Tool](#adding-a-new-silvia-tool)
6. [Adding a Hardware Assistant Command](#adding-a-hardware-assistant-command)
7. [Adding a New API Endpoint](#adding-a-new-api-endpoint)
8. [Database Migrations](#database-migrations)
9. [Design System](#design-system)
10. [Environment Variables Reference](#environment-variables-reference)

---

## Directory Structure

```
CMD-CTR/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── hardware.py          # 40+ hardware endpoints
│   │   │   ├── nodes.py             # Node registry endpoints
│   │   │   ├── assistant.py         # Main chat endpoint
│   │   │   ├── voice.py             # Voice STT/TTS endpoints
│   │   │   └── world.py             # World model endpoints
│   │   │
│   │   ├── core/
│   │   │   ├── application.py       # App startup, background loops
│   │   │   ├── auth_middleware.py   # API key auth
│   │   │   └── __init__.py
│   │   │
│   │   ├── models/
│   │   │   ├── nodes.py             # Node Pydantic models
│   │   │   ├── voice.py             # Voice request models
│   │   │   └── world.py             # World model schemas
│   │   │
│   │   ├── orchestration/
│   │   │   └── assistant_router.py  # Routes requests to conversation/hermes
│   │   │
│   │   ├── services/
│   │   │   ├── conversation_service.py     # Main LLM conversation loop
│   │   │   ├── decision_service.py         # Multi-brain debate
│   │   │   ├── hardware_service.py         # Inventory/project/order DB
│   │   │   ├── hardware_assistant_service.py # Regex-routed HW assistant
│   │   │   ├── hardware_category_classifier.py # Auto-classify parts
│   │   │   ├── hardware_import_service.py  # BOM/CSV import
│   │   │   ├── hardware_vision_service.py  # Image → component detection
│   │   │   ├── hermes_service.py           # Multi-step execution engine
│   │   │   ├── mission_service.py          # Tasks, reminders, calendar
│   │   │   ├── node_service.py             # Node registry DB + telemetry
│   │   │   ├── semantic_memory_service.py  # Conversation embedding + search
│   │   │   ├── voice_service.py            # STT/TTS orchestration
│   │   │   ├── watch_service.py            # Watch Officer alerts
│   │   │   └── web_service.py              # SearXNG web search
│   │   │
│   │   ├── tools/
│   │   │   ├── planner.py           # Tool dispatch + all SYSTEM_RULES
│   │   │   ├── node_tool.py         # Node operations implementation
│   │   │   └── time_tool.py         # Time zone utilities
│   │   │
│   │   └── world/
│   │       └── rss_ingestor.py      # RSS feed processing
│   │
│   ├── voice/
│   │   ├── implementations/
│   │   │   ├── whisper_stt.py       # Local faster-whisper
│   │   │   ├── speaches_stt.py      # Speaches STT client
│   │   │   ├── piper_tts.py         # Local Piper TTS
│   │   │   └── speaches_tts.py      # Speaches TTS client
│   │   ├── wakeword/
│   │   │   └── detector.py          # Wake word detection (Silero + ONNX)
│   │   └── vad/
│   │       └── silero_vad.py        # Voice activity detection
│   │
│   ├── config.py                    # ALL configuration constants
│   ├── main.py                      # FastAPI app + router registration
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── command/             # Mission, Task, Reminder panels
│   │   │   ├── infrastructure/      # Node, telemetry, alert panels
│   │   │   └── shared/              # Reusable UI atoms
│   │   │
│   │   ├── hooks/
│   │   │   └── useCommandCenterData.js  # Main data hook + WebSocket
│   │   │
│   │   ├── lib/
│   │   │   └── api.js               # ALL backend API calls (single file)
│   │   │
│   │   └── pages/
│   │       ├── CommandCenterPage.jsx     # Main SILVIA interface
│   │       ├── HardwareBoardPage.jsx     # Hardware Board
│   │       └── InfrastructurePage.jsx    # Node/service/telemetry view
│   │
│   ├── index.html
│   └── package.json
│
├── docs/                            # All documentation
├── prompts/                         # LLM system prompts
│   ├── saraswati.txt                # Analysis brain
│   ├── lakshmi.txt                  # Resource brain
│   └── durga.txt                    # Ethics brain
└── .env                             # Local config (never commit)
```

---

## Running Locally

```bash
# 1. Start Ollama (ensure models are pulled)
ollama serve

# 2. Start backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 3. Start frontend (dev)
cd frontend && npm run dev
# → http://localhost:5173

# 4. Optional: Start Speaches for voice
# (configure docker-compose to expose port 9000)
```

**Backend reloads automatically** when Python files change (`--reload` flag).

**Frontend hot-reloads** via Vite HMR.

---

## Backend Architecture

### Request Flow

```
HTTP Request → FastAPI router → API handler
                                      │
                    service layer (business logic)
                                      │
                             SQLite via raw SQL
                                      │
                               Response dict
```

### LLM Routing

SILVIA uses three Ollama models for different roles:

| Model | Role | Temperature |
|---|---|---|
| `gemma3:4b` | Main conversation | 0.7 (configurable) |
| `qwen2.5:3b` | Tool planning (planner.py) | 0.7 |
| `phi4-mini-reasoning` | Multi-brain debate (SARASWATI) | 0.2 |
| `gemma2:2b` | LAKSHMI brain | 0.4 |
| `qwen2.5:3b` | DURGA brain | 0.8 |

All LLM calls go through `httpx.post(OLLAMA_CHAT_URL, ...)` — no SDK, just REST.

### Background Tasks

`application.py` starts several background coroutines at startup:

- `_agent_poll_loop` — polls silvia-agent nodes every 30s for telemetry
- `_probe_loop` — probes passive nodes periodically for reachability
- `_watch_officer_loop` — evaluates alert rules after every telemetry update
- `_wake_word_loop` — listens for wake word via microphone
- `_voice_loop` — handles STT/TTS pipeline after wake word

### Database Files

All SQLite databases live in `backend/`:

| File | Tables | Purpose |
|---|---|---|
| `nodes.db` | nodes, node_services, service_capabilities, node_telemetry_history | Infrastructure |
| `hardware.db` | hw_inventory, hw_projects, hw_project_parts, hw_orders | Hardware Board |
| `missions.db` | projects, tasks, reminders, calendar_events, watch_alerts | Personal operations |
| `conversations.db` | conversation_turns, semantic_index | Conversation history |

---

## Frontend Architecture

### Key Files

- **`api.js`** — single source of truth for ALL backend calls. Every API function lives here.
- **`HardwareBoardPage.jsx`** — Hardware Board (2100+ lines, self-contained)
- **`CommandCenterPage.jsx`** — Main SILVIA interface
- **`useCommandCenterData.js`** — Data hook with WebSocket listener

### Design Tokens

All colors, fonts, and spacing come from the `T` object in each page:

```javascript
const T = {
  bg:        "#060b14",        // Main background
  surface:   "#0d1623",        // Card/panel background
  border:    "rgba(201,148,58,0.18)",   // Border (gold, low opacity)
  borderHi:  "rgba(201,148,58,0.45)",   // Active/hovered border
  gold:      "#c9943a",        // Primary accent — warm gold
  goldDim:   "#8a6422",        // Muted gold
  text:      "#ddd5c5",        // Primary text
  textMuted: "#6b7280",        // Secondary text
  green:     "#4ade80",        // Success
  orange:    "#fb923c",        // Warning
  red:       "#f87171",        // Error / critical
  blue:      "#60a5fa",        // Info
  purple:    "#a78bfa",        // In-progress / active
};
```

Fonts:
- **`Inter`** (body, UI labels)
- **`JetBrains Mono`** (code, IDs, commands, part names)

**Do not use:** Inter, Roboto, purple gradients, glowing borders, scanlines, cyan/teal glow effects.

### State Pattern

Pages own their state. API calls are always in callbacks or `useCallback` hooks. Loading states use `useState(true)`.

```javascript
const [parts, setParts] = useState([]);
const [loading, setLoading] = useState(true);

const load = useCallback(async () => {
  try {
    const data = await fetchHardwareInventory();
    setParts(data);
  } catch (e) {
    console.error(e);
  } finally {
    setLoading(false);
  }
}, []);

useEffect(() => { load(); }, [load]);
```

---

## Adding a New SILVIA Tool

### Step 1: Implement the tool function

In `backend/app/tools/` or `backend/app/services/`:

```python
# backend/app/tools/my_tool.py
async def my_new_tool(arg1: str, arg2: int) -> str:
    """Do something useful."""
    result = f"Did something with {arg1} and {arg2}"
    return result
```

### Step 2: Register in SYSTEM_RULES (planner.py)

Add to the `SYSTEM_RULES` string in `backend/app/tools/planner.py`:

```python
SYSTEM_RULES = """...
- my_new_tool: args {"arg1": string, "arg2": int}
  Use for: "trigger my thing", "do something with X and 5"
  Examples: "do something with foo and 5"
..."""
```

### Step 3: Add few-shot examples

```python
FEW_SHOTS = [
    ...
    {"role": "user",      "content": "do something with foo and 5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"my_new_tool","args":{"arg1":"foo","arg2":5}}'},
]
```

### Step 4: Handle in conversation_service.py

In `_run_tool()` inside `conversation_service.py`:

```python
elif tool_name == "my_new_tool":
    result = await my_new_tool(
        args.get("arg1", ""),
        int(args.get("arg2", 0))
    )
    return str(result)
```

That's it. SILVIA will now route matching queries to your tool.

---

## Adding a Hardware Assistant Command

### Read-only query (no data mutation)

In `HardwareAssistantService.handle()` in `hardware_assistant_service.py`:

Add your pattern **before** the catch-all `^show\s+` block:

```python
# Add near the top of handle(), before catch-all
if re.search(r"\bmy pattern\b|\bother pattern\b", lowered):
    return self._my_handler(text)
```

Implement the handler:

```python
def _my_handler(self, text: str) -> dict:
    # Call hardware_service methods — no LLM, pure DB
    data = self.hardware.some_method()
    if not data:
        return _info("Nothing found.")
    lines = ["Results:"]
    for item in data[:25]:
        lines.append(f"- {item['name']}: {item['value']}")
    return _info("\n".join(lines), data)
```

### Mutation (changes data)

1. Add pattern to `plan_mutation()`:

```python
def plan_mutation(self, text: str) -> dict | None:
    my_match = re.search(r"^my mutation command (.+)$", text, re.I)
    if my_match:
        return {"type": "my_mutation", "arg": my_match.group(1)}
    ...
```

2. Add preview to `preview()`:

```python
def preview(self, action: dict) -> dict:
    if action["type"] == "my_mutation":
        return _preview_response("Preview:", action, [f"- Will do {action['arg']}"])
    ...
```

3. Add execute to `execute()`:

```python
def execute(self, action: dict) -> dict:
    if action["type"] == "my_mutation":
        result = self.hardware.my_db_method(action["arg"])
        return _done(f"Done: {result}", result)
    ...
```

---

## Adding a New API Endpoint

1. Add Pydantic model (request body) to `backend/app/api/hardware.py`:

```python
class MyRequest(BaseModel):
    field: str
    count: int = 1
```

2. Add route handler:

```python
@router.post("/my-endpoint")
def my_endpoint(data: MyRequest, svc: HardwareService = Depends(_get_svc)):
    if not data.field:
        raise HTTPException(400, "field is required")
    result = svc.my_service_method(data.field, data.count)
    return result
```

3. Add service method in `hardware_service.py` (or the relevant service file).

4. Add frontend API function in `frontend/src/lib/api.js`:

```javascript
export async function callMyEndpoint(field, count) {
  return readJson(await _apiFetch(`${API_BASE}/hardware/my-endpoint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, count }),
  }));
}
```

---

## Database Migrations

SILVIA uses raw SQL with no ORM. Migrations are run at service initialization using try/except pattern:

```python
def _init_db(self) -> None:
    with sqlite3.connect(self._db_path) as conn:
        # Create tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS my_table (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # Add columns (safe migration — silently ignores if column exists)
        try:
            conn.execute("ALTER TABLE existing_table ADD COLUMN new_field TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        conn.commit()
```

**Rules:**
- `CREATE TABLE IF NOT EXISTS` for new tables
- `ALTER TABLE ADD COLUMN` wrapped in `try/except sqlite3.OperationalError: pass` for new columns
- Never drop columns (SQLite doesn't support it cleanly)
- Never use a migration framework — keep it simple

---

## Design System

Full design system documented in [design_system.md](../memory/design_system.md).

**Core rules:**
- Dark navy-black background (`#060b14`)
- Warm gold accent (`#c9943a`) — primary interactive color
- No scanlines, no glow effects, no neon colors, no gradients on text
- JetBrains Mono for all technical data (IDs, part names, commands, metrics)
- Inter for all UI labels and prose text
- Collapsible sections (▶ / ▼) for secondary content
- Table with `borderRight` dividers rather than card-grid layouts
- Status colors: green = good, orange = warning, red = error, blue = info

---

## Environment Variables Reference

All config is in `backend/config.py`. Every value reads from environment with a default.

| Variable | Default | Description |
|---|---|---|
| `OPENWEATHER_API_KEY` | `""` | OpenWeatherMap API key |
| `TIMEZONE` | `Asia/Kolkata` | Local timezone |
| `APP_HOST` | `0.0.0.0` | Backend bind address |
| `APP_PORT` | `8000` | Backend port |
| `CORS_ALLOW_ORIGINS` | `localhost:5173,8001` | Allowed CORS origins |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API base |
| `API_KEY` | `""` | Auth key (empty = disabled) |
| `BRAIN63_VAULT_PATH` | Windows path | Obsidian vault root |
| `SPEACHES_URL` | `""` | Speaches server URL |
| `SPEACHES_API_KEY` | `speaches` | Speaches auth key |
| `SPEACHES_STT_MODEL` | `rtlingo/...` | STT model name |
| `SPEACHES_TTS_MODEL` | `speaches-ai/Kokoro...` | TTS model name |
| `SPEACHES_TTS_VOICE` | `af_aoede` | Voice ID |
| `WHISPER_MODEL_SIZE` | `base` | Local Whisper model size |
| `PIPER_MODEL_PATH` | Windows path | Piper TTS model file |
| `PIPER_USE_CUDA` | `false` | Enable CUDA for Piper |
| `SEARXNG_URL` | `""` | SearXNG instance URL |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key (vision) |
| `VISION_PROVIDER` | `auto` | Vision provider: auto/anthropic/ollama |
| `VISION_MODEL_ANTHROPIC` | `claude-haiku-4-5-20251001` | Claude vision model |
| `VISION_MODEL_OLLAMA` | `llava` | Ollama vision model |
| `VISION_CONFIDENCE_THRESHOLD` | `0.65` | Min confidence for auto-approval |
| `NOTIFICATION_WEBHOOK_URL` | `""` | Discord/Slack webhook URL |
| `NOTIFICATION_WEBHOOK_FORMAT` | `discord` | Webhook format |
| `NOTIFICATION_EMAIL_HOST` | `""` | SMTP host |
| `NOTIFICATION_EMAIL_PORT` | `587` | SMTP port |
| `NOTIFICATION_EMAIL_USER` | `""` | SMTP username |
| `NOTIFICATION_EMAIL_PASS` | `""` | SMTP password |
| `NOTIFICATION_EMAIL_TO` | `""` | Alert recipient email |
| `NOTIFICATION_MIN_SEVERITY` | `critical` | Minimum severity to notify |
| `DECISION_TIMEOUT_SECONDS` | `180` | Multi-brain debate timeout |

---

## Related Documentation

- [Architecture.md](ARCHITECTURE.md) — System diagrams
- [Troubleshooting.md](Troubleshooting.md) — Common issues
- [Commands.md](Commands.md) — All commands by category
