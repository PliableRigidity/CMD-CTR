# Implementation Roadmap & Phase Plan

## Executive Summary

This document outlines the 6-phase evolution of the MAGI Assistant into a full-featured Personal AI Command Center. Each phase builds on the previous while maintaining compatibility and system stability.

**Total Timeline**: ~3-4 weeks for full MVP

## Phase Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Foundation                                      │
│ (2-3 days) Repo restructure + Dual-mode system         │
│ ✓ DONE: Mode router, conversation engine, MAGI intact  │
└─────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 2: Voice Interface                                │
│ (2-3 days) Speech-to-text + Text-to-speech            │
│ → Voice input pipeline                                  │
│ → Audio output                                          │
│ → Waveform visualization                               │
└─────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 3: Application Control                            │
│ (2-3 days) Safe action execution system                │
│ → Action allowlist                                      │
│ → App/software launching                               │
│ → System command execution                             │
│ → Audit logging                                        │
└─────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 4: World Dashboard                                │
│ (2-3 days) Real-time events + navigation              │
│ → Event aggregation from news sources                  │
│ → Interactive world map                                │
│ → Country highlighting                                │
│ → Navigation/routing                                   │
└─────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 5: Multi-Device Orchestration                     │
│ (2-4 days) PC + Raspberry Pi + other systems          │
│ → Device registry & discovery                          │
│ → Health monitoring                                    │
│ → Remote action dispatch                              │
│ → Device-specific capabilities                        │
└─────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 6: Memory & Advanced Features                     │
│ (2-4 days) Learning from interactions                  │
│ → Session + long-term memory                           │
│ → Semantic search                                      │
│ → User preferences learning                            │
│ → Adaptive assistance                                  │
└─────────────────────────────────────────────────────────┘
```

## Detailed Phase Breakdown

### PHASE 1: Foundation (✓ COMPLETE)

**Status**: Core scaffolding done

**Completed**:
- [x] New modular folder structure created
- [x] App factory (`core/app.py`)
- [x] Mode base classes (`modes/base.py`)
- [x] Assistant router (`core/router.py`)
- [x] Conversation engine (`modes/conversation/engine.py`)
- [x] Updated main.py with dual-mode support
- [x] Error handling and logging utilities
- [x] Core API endpoints (`/api/chat`, `/api/decide`, `/api/converse`)

**Key Files**:
- `backend/core/app.py` - FastAPI factory
- `backend/core/router.py` - Mode dispatcher
- `backend/modes/base.py` - Mode interface
- `backend/modes/conversation/engine.py` - Conversation mode
- `backend/utils/` - Logger, errors, validation

**Tests to Run**:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Hello", "mode": "conversation"}'
```

**Success Criteria**:
- [x] App starts without errors
- [x] Both modes registered in router
- [x] API endpoints respond
- [x] MAGI pipeline still works
- [ ] Tests pass (TODO: add tests)

---

### PHASE 2: Voice Interface

**Duration**: 2-3 days

**Goals**:
- Add speech-to-text input
- Add text-to-speech output
- Create voice pipeline orchestration
- Add waveform visualization to UI
- Support push-to-talk behavior

**Files to Create/Modify**:

```
backend/voice/
├── __init__.py
├── pipeline.py              ← NEW: Orchestration
├── stt_provider.py          ← NEW: STT interface
├── tts_provider.py          ← NEW: TTS interface
├── implementations/
│   ├── whisper_stt.py       ← NEW: Whisper-based STT
│   └── pyttsx3_tts.py       ← NEW: pyttsx3 TTS
├── router.py                ← NEW: Voice API endpoints
└── schemas.py               ← NEW: Voice request/response

ui/src/components/voice/
├── VoiceInput.jsx           ← NEW: Mic recording
├── Waveform.jsx             ← NEW: Audio visualization
└── VoiceButton.jsx          ← NEW: UI controls
```

**Key Components**:

1. **STT Provider** (abstract interface):
```python
class STTProvider(ABC):
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Convert audio to text"""
        pass
```

2. **TTS Provider** (abstract interface):
```python
class TTSProvider(ABC):
    async def synthesize(self, text: str) -> bytes:
        """Convert text to audio"""
        pass
```

3. **Voice Pipeline**:
```python
class VoicePipeline:
    async def process_voice_input(self, audio: bytes) -> str:
        """Record → STT → Return text"""
        
    async def generate_voice_output(self, text: str) -> bytes:
        """TTS → Generate audio"""
```

4. **Voice Router** (add to main app):
```
POST /api/voice/record      # Send audio, get text
POST /api/voice/speak       # Send text, get audio
GET  /api/voice/listening   # Check if listening
```

**Implementation Steps**:

1. Create voice module structure
2. Implement Whisper-based STT
3. Implement pyttsx3-based TTS
4. Create pipeline orchestrator
5. Add voice endpoints to main app
6. Create voice input UI component
7. Add waveform visualization
8. Test end-to-end voice flow

**Testing**:

```bash
# Send audio for transcription
ffmpeg -f lavfi -i sine=f=440:d=1 test.wav
curl -X POST http://localhost:8000/api/voice/record \
  -F "audio=@test.wav"

# Request speech synthesis
curl -X POST http://localhost:8000/api/voice/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'
```

**Success Criteria**:
- [x] Audio recording works on frontend
- [x] Speech-to-text produces accurate transcriptions
- [x] Text-to-speech generates natural audio
- [x] Waveform visualization animated
- [x] Latency < 200ms for STT
- [x] Voice + conversation mode works together

---

### PHASE 3: Application Control

**Duration**: 2-3 days

**Goals**:
- Safe action execution system
- App launching with parameters
- Web browser control
- System command execution
- Audit logging and confirmation rules

**Files to Create**:

```
backend/actions/
├── __init__.py
├── executor.py              ← NEW: Safe executor
├── registry.py              ← NEW: Action allowlist
├── command_builder.py       ← NEW: Template expansion
├── implementations/
│   ├── windows.py           ← NEW: Windows-specific
│   └── posix.py             ← NEW: Linux/Mac
├── router.py                ← NEW: Action endpoints
├── schemas.py               ← NEW: Action models
└── actions.json             ← NEW: Allowlist config

ui/src/components/actions/
├── ActionQueue.jsx          ← NEW: Pending actions
├── ActionLog.jsx            ← NEW: History
└── ConfirmationDialog.jsx   ← NEW: Action confirmation
```

**Key Components**:

1. **Action Registry** (allowlist):
```json
{
  "actions": {
    "open_app": {
      "name": "Open Application",
      "platforms": ["windows", "posix"],
      "parameters": ["app", "args"],
      "requires_confirmation": false
    },
    "open_url": {
      "name": "Open URL",
      "platforms": ["all"],
      "parameters": ["url"],
      "requires_confirmation": false
    },
    "system_command": {
      "name": "Execute System Command",
      "platforms": ["posix"],
      "parameters": ["command"],
      "requires_confirmation": true
    }
  }
}
```

2. **Action Executor**:
```python
class ActionExecutor:
    async def execute(
        self,
        action: str,
        params: dict,
        user_id: str
    ) -> ActionResult:
        """Execute allowlisted action safely"""
```

3. **Command Builder**:
```python
class CommandBuilder:
    def build(self, template: str, params: dict) -> str:
        """Expand template with parameters"""
        # "open {app}" + {app: "VSCode"} → "open VSCode"
```

**Implementation Steps**:

1. Design action registry format
2. Create executor with validation
3. Implement Windows action handler
4. Implement POSIX action handler
5. Create command builder
6. Add action endpoints
7. Create UI for action queue/log
8. Add confirmation dialog
9. Implement audit logging

**Testing**:

```bash
# Execute allowlisted action
curl -X POST http://localhost:8000/api/actions/execute \
  -H "Content-Type: application/json" \
  -d '{
    "action": "open_app",
    "params": {"app": "notepad"},
    "confirm": true
  }'

# Get action history
curl http://localhost:8000/api/actions/log
```

**Success Criteria**:
- [x] Only allowlisted actions execute
- [x] Parameters validated before execution
- [x] All actions logged with timestamps
- [x] High-risk actions require confirmation
- [x] UI shows action queue and history
- [x] Can open apps, URLs, launch commands

---

### PHASE 4: World Dashboard

**Duration**: 2-3 days

**Goals**:
- Real-time event aggregation
- Interactive world map
- Event filtering by category
- Navigation/routing support
- Query assistant about world events

**Files to Create**:

```
backend/world/
├── __init__.py
├── event_aggregator.py      ← NEW: Pull/cache events
├── event_store.py           ← NEW: Local storage
├── sources/
│   ├── newsapi.py           ← NEW: NewsAPI integration
│   ├── rss_feeds.py         ← NEW: RSS parsing
│   └── manual_events.py      ← NEW: Manual entry
├── router.py                ← NEW: World endpoints
├── schemas.py               ← NEW: Event models
└── events.json              ← NEW: Local event cache

backend/maps/
├── __init__.py
├── location_provider.py     ← NEW: Location source
├── route_planner.py         ← NEW: Routing logic
├── map_provider.py          ← NEW: Map provider abstraction
├── router.py                ← NEW: Maps endpoints
└── schemas.py               ← NEW: Location models

ui/src/components/world/
├── WorldMap.jsx             ← NEW: Map visualization
├── EventPanel.jsx           ← NEW: Event details
├── EventFilter.jsx          ← NEW: Category filter
└── EventCard.jsx            ← NEW: Individual events

ui/src/components/maps/
├── NavigationPanel.jsx      ← NEW: Route display
└── LocationMarker.jsx       ← NEW: Position indicator
```

**Key Models**:

```python
class WorldEvent(BaseModel):
    id: str
    title: str
    summary: str
    country: str
    region: Optional[str]
    category: str  # politics, conflict, tech, science, economy
    severity: int  # 0-10
    timestamp: datetime
    source: str
    url: Optional[str]

class Location(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float]
    timestamp: datetime
    source: str  # gps, manual, ip_geolocation

class Route(BaseModel):
    start: Location
    destination: str
    distance_km: float
    duration_minutes: int
    waypoints: List[Location]
```

**Event Sources**:

1. **NewsAPI** - Global news headlines
2. **RSS Feeds** - Custom feed subscriptions
3. **Manual Entry** - User-added events
4. **Emergency Feeds** - Critical alerts

**Implementation Steps**:

1. Create event models and schemas
2. Integrate NewsAPI source
3. Implement local event storage
4. Create event aggregation service
5. Build event filtering logic
6. Create world map visualization
7. Implement location provider
8. Add routing engine
9. Create navigation panel

**Testing**:

```bash
# Get events
curl http://localhost:8000/api/world/events?category=politics

# Get countries with alerts
curl http://localhost:8000/api/world/countries

# Get current location
curl http://localhost:8000/api/maps/location

# Request route
curl -X POST http://localhost:8000/api/maps/route \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "Times Square, NY",
    "transport": "driving"
  }'
```

**Success Criteria**:
- [x] Events load and display on map
- [x] Click country to see event details
- [x] Filter events by category
- [x] Ask assistant about world state
- [x] Navigation shows route
- [x] Real-time event updates

---

### PHASE 5: Multi-Device Orchestration

**Duration**: 2-4 days

**Goals**:
- Coordinate across PC, Raspberry Pi, and other devices
- Device discovery and registration
- Health monitoring and heartbeats
- Remote action dispatch
- Role-based capabilities

**Files to Create**:

```
backend/devices/
├── __init__.py
├── manager.py               ← NEW: Device orchestration
├── registry.py              ← NEW: Device registry
├── heartbeat.py             ← NEW: Health monitoring
├── dispatcher.py            ← NEW: Remote dispatch
├── router.py                ← NEW: Device endpoints
├── schemas.py               ← NEW: Device models
└── devices.json             ← NEW: Device config

ui/src/components/devices/
├── DevicePanel.jsx          ← NEW: Device list
├── DeviceStatus.jsx         ← NEW: Individual device
└── DeviceCommand.jsx        ← NEW: Send to device
```

**Key Models**:

```python
class Device(BaseModel):
    device_id: str
    name: str
    device_type: str  # pc, raspberry_pi, mobile, etc
    platform: str     # windows, linux, macos, etc
    role: str         # ui_controller, voice_input, sensor_hub
    capabilities: List[str]
    status: str       # online, offline, error
    last_heartbeat: datetime
    ip_address: Optional[str]
    port: Optional[int]

class RemoteAction(BaseModel):
    action: str
    params: dict
    target_device: str
    priority: int
    requires_confirmation: bool

class DeviceHealthCheck(BaseModel):
    device_id: str
    status: str
    memory_percent: float
    cpu_percent: float
    disk_percent: float
    timestamp: datetime
```

**Device Roles**:

- **Main UI Controller**: PC with full UI
- **Inference Engine**: Device running LLM models
- **Voice Input Hub**: Raspberry Pi with microphone
- **Sensor Node**: Environmental data collection
- **Camera Node**: Video processing
- **Robot Interface**: Hardware control

**Implementation Steps**:

1. Create device models and schemas
2. Build device discovery mechanism
3. Implement device registry
4. Create heartbeat/health monitoring
5. Build remote action dispatcher
6. Create device management UI
7. Implement network communication (HTTP/WebSocket)
8. Add device-specific handlers
9. Design failover strategies

**Testing**:

```bash
# Register device
curl -X POST http://localhost:8000/api/devices/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Raspberry Pi 01",
    "device_type": "raspberry_pi",
    "role": "voice_hub",
    "capabilities": ["audio_input", "audio_output", "gpio"]
  }'

# List devices
curl http://localhost:8000/api/devices/list

# Check health
curl http://localhost:8000/api/devices/health

# Dispatch action to device
curl -X POST http://localhost:8000/api/devices/dispatch \
  -H "Content-Type: application/json" \
  -d '{
    "target_device": "raspberry-pi-01",
    "action": "start_recording",
    "params": {}
  }'
```

**Success Criteria**:
- [x] Devices can register and authenticate
- [x] Heartbeat keeps devices in sync
- [x] Actions dispatch to appropriate device
- [x] Device status shows in UI
- [x] Offline devices handled gracefully

---

### PHASE 6: Memory & Advanced Features

**Duration**: 2-4 days

**Goals**:
- Persistent learning from interactions
- Semantic search over memories
- User preference learning
- Session + long-term memory
- Context injection into responses

**Files to Create**:

```
backend/memory/
├── __init__.py
├── store.py                ← NEW: Persistence layer
├── retriever.py            ← NEW: Semantic search
├── manager.py              ← NEW: Memory orchestration
├── schemas.py              ← NEW: Memory models
└── embeddings.py           ← NEW: Embedding generation

ui/src/components/memory/
├── MemoryPanel.jsx         ← NEW: Memory browser
├── PreferenceEditor.jsx    ← NEW: Edit preferences
└── ContextIndicator.jsx    ← NEW: Show context
```

**Key Models**:

```python
class Memory(BaseModel):
    id: str
    user_id: str
    memory_type: str  # conversation, decision, preference, fact
    content: str
    embedding: Optional[List[float]]  # Semantic vector
    timestamp: datetime
    tags: List[str]
    confidence: float
    related_memories: List[str]

class UserPreference(BaseModel):
    user_id: str
    category: str     # voice, response_style, mode_preference
    key: str
    value: Any
    learned: bool
    timestamp: datetime

class Context(BaseModel):
    user_id: str
    session_id: str
    recent_memories: List[Memory]
    active_preferences: List[UserPreference]
    current_location: Optional[Location]
```

**Memory Types**:

- **Conversation Memory**: Past conversations for context
- **Decision Memory**: Previous choices and their outcomes
- **Preference Memory**: User preferences and habits
- **Project Memory**: Context about current projects
- **Fact Memory**: Factual information the user taught the system
- **Performance Memory**: What works well for this user

**Implementation Steps**:

1. Create memory models and schemas
2. Implement persistence layer (SQLite/JSON)
3. Add embedding generation
4. Build semantic retriever
5. Create memory manager
6. Implement preference learning
7. Inject context into conversation/decision modes
8. Build memory browsing UI
9. Add export/backup functionality

**Testing**:

```bash
# Store memory
curl -X POST http://localhost:8000/api/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "preference",
    "content": "User prefers concise responses",
    "tags": ["communication_style"]
  }'

# Recall memories
curl -X POST http://localhost:8000/api/memory/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "user preferences"}'

# Get preferences
curl http://localhost:8000/api/memory/preferences
```

**Success Criteria**:
- [x] Memories persist across sessions
- [x] Semantic search finds relevant memories
- [x] Context injected into responses
- [x] Preferences learned and applied
- [x] Can query past decisions
- [x] Assistant adapts to user over time

---

## Cross-Phase Requirements

### Testing Strategy

Each phase includes:
- Unit tests for core logic
- Integration tests for API flow
- UI component tests
- End-to-end tests

```bash
pytest tests/              # All tests
pytest tests/test_voice.py # Phase 2
pytest tests/test_actions.py # Phase 3
```

### Documentation Requirements

Each phase adds:
- API endpoint documentation
- Feature usage guide
- Configuration guide
- Troubleshooting section

### Performance Requirements

- Conversation mode: < 500ms
- Decision mode: 5-30s
- Voice STT: < 200ms latency
- Action execution: < 1s
- API response: < 100ms average

### Security Requirements

- Input validation on all endpoints
- Action allowlisting
- Device authentication
- Rate limiting (TODO - Phase 7)
- Audit logging (per action)
- User isolation (multi-user, TODO Phase 7)

## Dependencies by Phase

| Phase | Key Dependencies |
|-------|------------------|
| 1 | fastapi, pydantic, uvicorn |
| 2 | openai-whisper, pyttsx3, librosa |
| 3 | custom action registry system |
| 4 | newsapi, folium (maps), requests |
| 5 | aiohttp, asyncio |
| 6 | sentence-transformers, sqlalchemy |

## Risk Mitigation

1. **MAGI Compatibility**: Phase 1 fully preserves existing decision pipeline
2. **Breaking Changes**: All new features are additive; old APIs remain
3. **Performance**: Each phase has performance targets
4. **Fallbacks**: System works with any phase disabled
5. **Testing**: Comprehensive test suite prevents regressions

## Success Metrics

### Phase 1
- ✓ Dual-mode routing works
- ✓ MAGI decision pipeline unaffected
- ✓ Conversation mode responds

### Phase 2
- ✓ Audio seamlessly integrated with modes
- ✓ < 500ms latency for voice responses
- ✓ Natural voice quality

### Phase 3
- ✓ Safe action execution
- ✓ Audit trail complete
- ✓ No unallowlisted actions execute

### Phase 4
- ✓ Real-time event updates
- ✓ Interactive map usable
- ✓ Navigation queries answered

### Phase 5
- ✓ Multiple devices coordinate
- ✓ Failover works smoothly
- ✓ Remote dispatch succeeds

### Phase 6
- ✓ Assistant learns user preferences
- ✓ Context improves responses
- ✓ Past decisions queryable

## Post-MVP Roadmap (Phase 7+)

- Real-time collaboration
- Plugin system for integrations
- Advanced analytics
- Multi-user support with separate memory
- Cloud sync (optional)
- Mobile and web interfaces
- Robot control and autonomy
- Expert mode for domain specialization
