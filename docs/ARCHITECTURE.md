# Personal AI Assistant - Architecture Documentation

## System Overview

The Personal AI Assistant is a sophisticated local-first AI command center evolved from the MAGI decision system. It combines:

- **Fast Conversation Mode**: Direct LLM responses for natural dialogue
- **Deep Decision Mode**: MAGI multi-agent deliberation for complex choices
- **Voice Interface**: Full speech-to-text and text-to-speech support
- **World Dashboard**: Real-time news and event aggregation
- **Application Control**: Safe execution of system commands and app launching
- **Device Orchestration**: Coordination across multiple machines
- **Persistent Memory**: Learning from user interactions and preferences

## Core Architecture

### 1. Mode System

The assistant operates in different modes depending on query type:

```
User Query
    ↓
Mode Router (Auto-detect or manual selection)
    ↓
    ├─ Conversation Mode → Direct LLM call → Fast response (100-500ms)
    └─ Decision Mode → MAGI Pipeline → Deep reasoning (5-30s)
         ├─ World Model
         ├─ Action Generation
         ├─ Brain Evaluation (Saraswati, Lakshmi, Durga)
         ├─ Debate Round
         ├─ Voting
         └─ Chair Summary
```

### 2. Subsystem Architecture

```
┌─ Core Orchestration (core/)
│  ├─ App Factory (app.py)
│  ├─ Router/Dispatcher (router.py)
│  ├─ Context Management (context.py)
│  └─ WebSocket Manager (websocket_manager.py)
│
├─ Operating Modes (modes/)
│  ├─ Conversation Engine
│  └─ Decision Engine (MAGI) [PRESERVED]
│
├─ Subsystems
│  ├─ Voice Pipeline (voice/)
│  ├─ World Events (world/)
│  ├─ Maps & Navigation (maps/)
│  ├─ Action Executor (actions/)
│  ├─ Device Manager (devices/)
│  └─ Memory Store (memory/)
│
├─ Integrations (integrations/)
│  ├─ Ollama Provider
│  └─ [Other LLM providers]
│
└─ Utilities (utils/)
   ├─ Logging
   ├─ Error Handling
   └─ Validation
```

## API Endpoints

### Chat & Decision

- `POST /api/chat` - Route through auto-detected mode
- `POST /api/converse` - Force conversation mode
- `POST /api/decide` - Force decision mode
- `GET /api/modes` - List available modes
- `GET /api/modes/active` - Get active mode

### Voice (Phase 2)

- `POST /api/voice/record` - Speech-to-text
- `POST /api/voice/speak` - Text-to-speech
- `GET /api/voice/listening` - Check listening state

### World Events (Phase 4)

- `GET /api/world/events` - Fetch events
- `GET /api/world/countries` - List countries with alerts
- `POST /api/world/subscribe` - Subscribe to event category

### Actions (Phase 3)

- `POST /api/actions/execute` - Execute allowlisted action
- `GET /api/actions/available` - List available actions
- `GET /api/actions/log` - Action execution history

### Devices (Phase 5)

- `POST /api/devices/register` - Register new device
- `GET /api/devices/list` - List connected devices
- `GET /api/devices/health` - Check device health
- `POST /api/devices/dispatch` - Send remote action

### Memory (Phase 6)

- `POST /api/memory/store` - Store memory item
- `POST /api/memory/recall` - Retrieve memories
- `GET /api/memory/preferences` - Get user preferences

## Request/Response Models

### Standard Chat Request

```json
{
  "query": "Should I jump or climb?",
  "mode": "auto",
  "goal": "Reach the top safely",
  "constraints": ["Limited energy", "Afraid of heights"],
  "context": {},
  "user_id": "user123",
  "session_id": "session456"
}
```

### Standard Response

```json
{
  "mode": "decision",
  "answer": "Based on the council's deliberation, climbing is recommended...",
  "confidence": 0.85,
  "reasoning": "Risk analysis favors climbing given the constraints",
  "decision_data": {
    "final_decision": "CLIMB",
    "recommended_action": "Start climbing carefully",
    "full_result": {...}
  },
  "processing_time_ms": 8250,
  "metadata": {}
}
```

## Data Models

### Core Models

- `ModeRequest`: Base request for any mode
- `ModeResponse`: Base response from any mode
- `AssistantRequest`: Unified API request format
- `AssistantResponse`: Unified API response format

### Conversation Models

- `ConversationRequest`: Conversation-specific request
- `ConversationResponse`: Conversation-specific response

### Decision Models (Preserved from MAGI)

- `RawUserInput`: User problem + goal + constraints
- `SituationModel`: Normalized understanding of the situation
- `ActionSet`: Generated candidate actions
- `BrainResponse`: Individual agent evaluation
- `FinalVote`: Final agent votes
- `ChairSummary`: Chair's synthesis of the debate
- `FinalDecision`: Full decision result

## Configuration

Configuration is managed through:

1. `backend/config.py` - Main configuration
2. `.env` files - Environment-specific settings
3. Runtime overrides - Passed during initialization

Key configuration categories:

- **LLM Settings**: Model names, temperatures, API endpoints
- **Logic Settings**: Timeouts, retry policies, constraints
- **Feature Flags**: Which subsystems are enabled
- **Security**: Allowlists, action permissions, device registry

## Integration Points

### LLM Integration

The system abstracts LLM access through an integration layer:

```python
from backend.integrations import get_llm_provider

provider = get_llm_provider()  # Returns Ollama or other provider
response = await provider.complete(prompt, context)
```

### Device Integration

Devices communicate via API:

```python
from backend.devices import DeviceManager

manager = DeviceManager()
device = await manager.get_device("raspberry-pi-01")
await device.execute_action("start_mic", {})
```

### Action Integration

Actions execute through a safe abstraction:

```python
from backend.actions import ActionExecutor

executor = ActionExecutor()
result = await executor.execute("open_app", {"app": "VSCode"})
```

## Security Considerations

1. **Action Allowlist**: Only pre-approved actions can execute
2. **Input Validation**: All requests validated with Pydantic
3. **Rate Limiting**: TODO - implement per-user rate limits
4. **Audit Logging**: All actions logged with timestamps and user IDs
5. **Device Authentication**: Devices must register and authenticate
6. **Confirmation Rules**: High-risk actions require confirmation

## Performance Targets

- Conversation mode: < 500ms per response
- Decision mode: 5-30s per decision
- Voice input: < 200ms latency
- Mode switching: < 100ms
- Device dispatch: < 1s round-trip

## Future Extensions

Design supports adding:

- Multi-user support with separate memory per user
- Advanced voice features (continuous listening, speaker ID)
- Custom model fine-tuning
- Cloud integration (optional)
- Real-time collaboration
- Plugin system for custom subsystems
- Mobile and web interfaces
- Advanced memory with semantic search
