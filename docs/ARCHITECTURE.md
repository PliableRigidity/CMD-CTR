# SILVIA Architecture

## Table of Contents

1. [System Overview](#system-overview)
2. [Frontend → Backend Data Flow](#frontend--backend-data-flow)
3. [LLM Routing](#llm-routing)
4. [Voice Pipeline](#voice-pipeline)
5. [Hardware Board Architecture](#hardware-board-architecture)
6. [Node Registry Architecture](#node-registry-architecture)
7. [Database Schema](#database-schema)
8. [Background Loops](#background-loops)

---

## System Overview

```mermaid
graph TB
    subgraph Frontend["Frontend (React + Vite, port 5173/8001)"]
        CC[CommandCenterPage]
        HB[HardwareBoardPage]
        IB[IntelBoardPage]
        VD[VoiceDiagnosticsPage]
    end

    subgraph Backend["Backend (FastAPI, port 8000)"]
        API[API Layer]
        CS[Conversation Service gemma3:4b]
        PL[Tool Planner qwen2.5:3b]
        HE[Hermes Engine phi4-mini-reasoning]
        HA[Hardware Assistant regex routing]
        VS[Vision Service]
        NS[Node Service]
        WO[Watch Officer]
        DA[Desktop Awareness]
        PO[Personal Ops]
        SM[Semantic Memory]
    end

    subgraph Storage["Storage"]
        DB[(data/cmdctr.db SQLite)]
    end

    subgraph LLMs["Local LLMs via Ollama"]
        G[gemma3:4b conversation]
        Q[qwen2.5:3b tool planning]
        P[phi4-mini-reasoning Hermes + world]
        G2[gemma2:2b Lakshmi]
        E[nomic-embed-text embeddings]
        L[llava vision optional]
    end

    Frontend -->|HTTP REST + WebSocket| API
    API --> CS
    API --> HA
    API --> VS
    API --> NS
    CS --> PL
    CS --> HE
    PL --> Q
    CS --> G
    HE --> P
    VS --> L
    SM --> E
    NS --> WO
    Backend --> DB
```

---

## Frontend → Backend Data Flow

### Chat Request

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as POST /api/assistant/chat
    participant PL as Planner qwen2.5:3b
    participant TL as Tool Executor
    participant EX as Conversation gemma3:4b

    U->>FE: types message
    FE->>API: {message, history}
    API->>PL: classify intent
    alt tool needed
        PL-->>API: call_tool JSON
        API->>TL: execute tool
        TL-->>API: structured result
    else no tool
        PL-->>API: final
    end
    API->>EX: synthesize response
    EX-->>API: response text
    API-->>FE: {reply, tool_results}
    FE-->>U: display
```

### Hardware Assistant — Preview/Confirm Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Hardware Assistant Panel
    participant API as POST /api/hardware/assistant
    participant HA as HardwareAssistantService
    participant DB as SQLite

    U->>FE: "I bought: 5 ESP32-S3"
    FE->>API: {message, pending_action: null}
    API->>HA: handle(message)
    HA->>DB: find_part_smart("ESP32-S3")
    DB-->>HA: existing part qty=3
    HA-->>API: {reply: "preview...", pending_action: {...}, committed: false}
    API-->>FE: preview shown

    U->>FE: "confirm"
    FE->>API: {message: "confirm", pending_action: {...}}
    API->>HA: execute(pending_action)
    HA->>DB: update_part qty=8
    HA-->>API: {committed: true}
    API-->>FE: confirmed
```

### WebSocket Events

The frontend connects to `ws://{host}:8000/api/ws/events` on page load. Events are pushed from background loops:

| Event Type | Payload | Triggered by |
|---|---|---|
| `node_telemetry` | `{node_id, cpu, ram, disk, battery, ...}` | Agent poll loop every 30s |
| `watch_alert` | `{severity, message, category}` | Watch Officer rule match |
| `reminder_due` | `{message, escalation_level}` | Reminder loop |

---

## LLM Routing

| Model | Role | Temperature | Why |
|---|---|---|---|
| `qwen2.5:3b` | Tool planner | 0.7 | Fast structured JSON output |
| `gemma3:4b` | Conversation | — | Natural language synthesis |
| `phi4-mini-reasoning` | World model + Hermes | 0.2 | Structured reasoning, multi-step |
| `gemma2:2b` | Lakshmi debate brain | 0.4 | Balanced second opinion |
| `qwen2.5:3b` | Durga debate brain | 0.8 | Contrarian high-temperature |
| `nomic-embed-text` | Embeddings | — | Semantic memory search |
| `llava` | Vision (optional) | — | Component detection from images |

### Planner Output Shapes

```json
// Single tool
{"action": "call_tool", "name": "get_weather", "args": {"place": "london"}}

// Multiple tools in parallel
{"action": "call_tools", "calls": [
  {"name": "get_time_in", "args": {"place": "london"}},
  {"name": "get_weather", "args": {"place": "london"}}
]}

// No tool — send directly to conversation model
{"action": "final"}
```

### MAGI Council — Debate Mode

```mermaid
flowchart TB
    Q[Question] --> SA[SARASWATI phi4-mini-reasoning temp=0.2]
    Q --> LA[LAKSHMI gemma2:2b temp=0.4]
    Q --> DU[DURGA qwen2.5:3b temp=0.8]
    SA --> CH[Chair phi4-mini-reasoning consensus]
    LA --> CH
    DU --> CH
    CH --> ANS[Final answer]
```

---

## Voice Pipeline

```mermaid
sequenceDiagram
    participant MIC as Microphone
    participant VAD as Silero VAD
    participant WW as Wake Word Detector
    participant STT as STT Provider
    participant CORE as SILVIA Core
    participant TTS as TTS Provider
    participant SPK as Speaker

    loop always listening
        MIC->>VAD: raw audio
        VAD->>WW: speech detected
    end
    WW-->>CORE: Hey SILVIA detected
    CORE->>MIC: capture utterance
    VAD-->>CORE: silence = end of speech
    CORE->>STT: audio bytes
    STT-->>CORE: transcribed text
    CORE->>CORE: process command
    CORE->>TTS: response text
    TTS-->>SPK: audio
```

**Provider selection:**

```
SPEACHES_URL set? → Speaches (faster-whisper-large-v3-turbo + Kokoro TTS)
               NO → local Whisper (base) + Piper TTS
```

---

## Hardware Board Architecture

### Entity Relationships

```mermaid
erDiagram
    hw_inventory {
        text id PK
        text name
        text category
        int quantity
        text status
        int reorder_threshold
    }

    hw_projects {
        text id PK
        text name
        text status
        text priority
    }

    hw_project_parts {
        text project_id FK
        text part_id FK
        int quantity_required
        text acceptable_substitutes
    }

    hw_orders {
        text id PK
        text part_name
        text vendor
        int quantity
        text status
        text date_received
    }

    hw_projects ||--o{ hw_project_parts : "requires"
    hw_inventory ||--o{ hw_project_parts : "used in"
```

### Hardware Assistant Routing

```mermaid
flowchart TD
    MSG[User message] --> PA{pending_action?}
    PA -->|confirm| EX[execute]
    PA -->|cancel| CX[cancelled]
    PA -->|no| CHECK[Route checks in order]

    CHECK --> B1{"blocked/buildable\nquery?"}
    B1 -->|yes| R1[project readiness functions]
    B1 -->|no| B2{"missing parts?"}
    B2 -->|yes| R2[_missing_parts]
    B2 -->|no| B3{"can I build X?"}
    B3 -->|yes| R3[_build_readiness]
    B3 -->|no| B4{"requirements for X?"}
    B4 -->|yes| R4[_show_project]
    B4 -->|no| B5{"procurement\nquery?"}
    B5 -->|recommendations| R5[_show_recommendations]
    B5 -->|low stock| R6[_show_low_stock]
    B5 -->|after delivery| R7[_after_delivery_readiness]
    B5 -->|no| B6{"order queries?"}
    B6 -->|yes| R8[_show_orders]
    B6 -->|no| B7{"project list?"}
    B7 -->|yes| R9[_show_projects]
    B7 -->|no| B8{inventory\nquery?}
    B8 -->|yes| R10[_show_inventory]
    B8 -->|no| PM[plan_mutation]
    PM -->|matched| PV[preview + pending_action]
    PM -->|no match| HLP[help message]
```

---

## Node Registry Architecture

```mermaid
graph LR
    subgraph DB["Database"]
        N[nodes table]
        S[node_services table]
        C[service_capabilities table]
        W[watch_alerts table]
    end

    subgraph Loops["Background Loops"]
        AP[Agent Poll 30s]
        PP[Probe Loop 5min]
        WL[Watch Officer 30s]
    end

    subgraph Agent["silvia-agent nodes"]
        A1[node with agent_url]
        A2[GET /metrics]
    end

    subgraph Passive["Passive nodes"]
        P1[node with hostname only]
        P2[DNS + Tailscale + ping]
    end

    N --> AP
    N --> PP
    AP --> A1
    A1 --> A2
    A2 -->|telemetry| N
    PP --> P1
    P1 --> P2
    P2 -->|status update| N
    N --> WL
    WL -->|threshold exceeded| W
    W -->|WebSocket| FE[Frontend]
```

---

## Database Schema

All tables in `data/cmdctr.db`. Created automatically, migrated safely with `ALTER TABLE ADD COLUMN`.

| Table | Purpose |
|---|---|
| `nodes` | Node registry with telemetry |
| `node_services` | Services on each node |
| `service_capabilities` | Capabilities per service |
| `watch_alerts` | Watch Officer alert log |
| `tasks` | Personal task list |
| `reminders` | Timed reminders with escalation |
| `calendar_events` | Calendar |
| `projects` | Mission Control project registry |
| `conversation_memory` | Semantic memory (text + embedding) |
| `hw_inventory` | Hardware component inventory |
| `hw_projects` | Hardware build projects |
| `hw_project_parts` | BOM links (project ↔ component) |
| `hw_orders` | Procurement orders |
| `hw_imports` | BOM/inventory import log |
| `locations` | Trusted filesystem locations |
| `app_registry` | Discovered applications |
| `launch_preferences` | Open-target preferences |
| `scheduled_tasks` | Hermes cron tasks |

---

## Background Loops

All run as `asyncio` tasks from `backend/app/core/application.py`:

| Loop | Interval | Purpose |
|---|---|---|
| Agent poll | 30s | Fetch live telemetry from silvia-agent nodes |
| Node probe | 5 min | DNS/Tailscale/ping verification for passive nodes |
| Watch Officer | 30s | Evaluate threshold rules, emit alerts, push WebSocket |
| Reminder checker | 60s | Due reminders, escalation (24h → warning, 72h → critical) |
| Scheduled task runner | 60s | Execute due Hermes tasks |
| RSS ingestor | 15 min | Pull world intelligence RSS feeds |
