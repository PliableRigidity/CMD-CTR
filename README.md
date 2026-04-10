# Personal AI Assistant - MAGI Evolution

*Evolved from a MAGI deliberation engine into a local-first personal AI command center*

## 🎯 Overview

This is a sophisticated personal AI assistant built on the foundation of the MAGI multi-agent decision system. It combines:

- **⚡ Conversation Mode**: Fast, natural responses for everyday queries
- **🧠 Decision Mode**: Deep MAGI deliberation for complex choices
- **🎤 Voice Interface**: Speech-to-text and text-to-speech (Phase 2)
- **🌍 World Dashboard**: Real-time news and events (Phase 4)
- **⌨️ Action System**: Safe application and system control (Phase 3)
- **📱 Device Coordination**: Multi-machine orchestration (Phase 5)
- **💾 Memory System**: Learning from interactions (Phase 6)

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 16+
- Ollama (for local LLMs)

### Setup (5 minutes)

```bash
# Backend setup
cd backend
pip install -r requirements.txt

# Frontend setup
cd ../ui
npm install

# Start Ollama in another terminal
ollama serve

# Pull models
ollama pull phi4-mini-reasoning:latest
ollama pull qwen2.5:3b
ollama pull gemma2:2b
ollama pull phi3:mini

# Start backend
python main.py

# In another terminal, start frontend
cd ui && npm run dev
```

Open your browser to `http://localhost:5173`

## 📚 Documentation

Start here to understand the system:

1. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design and how components interact
2. **[docs/MODES.md](docs/MODES.md)** - How conversation and decision modes work
3. **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Setup and development guide
4. **[docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md)** - Phased implementation plan

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│      PERSONAL AI COMMAND CENTER UI          │
│  (Dark mode, sci-fi panels, live updates)   │
└────────┬────────────────────────────┬───────┘
         │ WebSocket (real-time)      │ REST (stateful)
         │                            │
    ┌────▼────────────────────────────▼────┐
    │    ASSISTANT ROUTER & ORCHESTRATOR   │
    │  - Mode selection (auto or manual)   │
    │  - Request routing                   │
    │  - Context aggregation               │
    └────┬────────────────────────────┬────┘
         │                            │
    ┌────▼─────────┐         ┌───────▼────────┐
    │ CONVERSATION │         │    DECISION    │
    │    ENGINE    │         │   ENGINE       │
    │ (Fast LLM)   │         │  (MAGI-based)  │
    ├──────────────┤         ├────────────────┤
    │ • Quick Q&A  │         │ • World model  │
    │ • Commands   │         │ • Action gen   │
    │ • Retrieval  │         │ • Debates      │
    │ • Reasoning  │         │ • Final votes  │
    └──────────────┘         └────────────────┘
         │                            │
    ┌────▼────────────────────────────▼────────────┐
    │         SHARED SERVICES LAYER                │
    │                                              │
    │ ┌─────────────┐ ┌──────────────────────────┐│
    │ │Voice        │ │World Events / Maps      ││
    │ │Pipeline     │ │Application Control / ... ││
    │ │(Phase 2)    │ │(Phases 3-6 in progress) ││
    │ └─────────────┘ └──────────────────────────┘│
    │                                              │
    └──────────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────┐
    │    LOCAL EXECUTION LAYER              │
    │                                       │
    │ • Ollama LLMs                         │
    │ • SQLite/JSON Storage                 │
    │ • Device APIs                         │
    │ • Audio streams                       │
    └───────────────────────────────────────┘
```

## 📋 Current Status (Phase 1 ✅ COMPLETE)

### ✅ Completed

- [x] Modular project structure
- [x] Dual-mode operation (conversation + decision)
- [x] Mode router with auto-detection
- [x] FastAPI app factory
- [x] Error handling and logging
- [x] MAGI pipeline preserved and working
- [x] API endpoints (`/api/chat`, `/api/decide`, `/api/converse`)
- [x] Core documentation

### 📝 What's Next

**Phase 2**: Voice Interface
- Speech-to-text with Whisper
- Text-to-speech synthesis
- Waveform visualization
- Low-latency audio handling

**Phase 3**: Application Control
- Safe action execution
- App launching
- System commands
- Audit logging

**Phases 4-6**: World Dashboard, Multi-Device, Memory System

See [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) for detailed phase breakdown.

## 🔌 API Endpoints

### Chat & Decision

```bash
# Auto-detect mode (tries decision if relevant, else conversation)
POST /api/chat
{
  "query": "Should I learn Python?",
  "goal": "Get a tech job",
  "constraints": ["3 months available"]
}

# Force conversation mode
POST /api/converse
{
  "query": "What's the capital of France?"
}

# Force decision mode
POST /api/decide
{
  "query": "Which programming language?",
  "context": {}
}

# Get available modes
GET /api/modes

# Get active mode
GET /api/modes/active
```

## 🧠 How It Works

### Conversation Mode (Fast)

```
User Query
    ↓
Router detects: No decision keywords
    ↓
Conversation Engine
    ↓
Direct LLM call (< 500ms)
    ↓
Natural Response
```

### Decision Mode (Deep)

```
User Query + Goal + Constraints
    ↓
Router detects: Decision keywords
    ↓
MAGI Pipeline
    ├─ World Model: Normalize problem
    ├─ Action Generation: Create options
    ├─ Brain Round 1: SARASWATI, LAKSHMI, DURGA evaluate
    ├─ Debate Round: Agents react to each other
    ├─ Voting: Determine majority
    └─ Chair Summary: VIVEKA synthesizes
    ↓
Structured Decision with Reasoning (5-30s)
```

## 🤖 MAGI Agents

The decision mode uses four specialized agents:

- **SARASWATI** 🧠 Logic - Analytical, fact-based reasoning
- **LAKSHMI** ❤️ Emotion - Values-based, intuition-driven
- **DURGA** ⚔️ Determination - Action-oriented, risk assessment
- **VIVEKA** 🎯 Wisdom - Synthesizes all perspectives into final recommendation

## 📦 Project Structure

```
backend/
├── core/                     # FastAPI app + router
│   ├── app.py               # App factory
│   └── router.py            # Mode dispatcher
├── modes/                    # Operating modes
│   ├── base.py              # Mode interface
│   ├── conversation/        # Fast responses
│   └── decision/            # MAGI pipeline (preserved)
├── voice/                    # Voice I/O (Phase 2)
├── world/                    # Events/news (Phase 4)
├── maps/                     # Navigation (Phase 4)
├── actions/                  # App control (Phase 3)
├── devices/                  # Multi-device (Phase 5)
├── memory/                   # Learning (Phase 6)
├── integrations/             # LLM providers
├── utils/                    # Logging, errors, validation
└── main.py                   # Entry point

ui/
├── src/
│   ├── components/           # React components
│   ├── hooks/               # Custom React hooks
│   ├── services/            # API clients
│   ├── layouts/             # Page layouts
│   └── App.jsx              # Root component
└── vite.config.js           # Build config

docs/
├── ARCHITECTURE.md          # System design
├── MODES.md                # Mode documentation
├── DEVELOPMENT.md          # Dev setup
└── IMPLEMENTATION_ROADMAP.md # Phase plan
```

## 🚀 Development

### Running Tests

```bash
pytest tests/
pytest tests/test_conversation.py -v
```

### Building for Production

```bash
# Backend
python -m pip install -r backend/requirements.txt
# Backend runs as: uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Frontend
cd ui
npm run build
# Output in ui/dist
```

### Debugging

```bash
# Enable debug logging
LOG_LEVEL=DEBUG python main.py

# Check logs
tail -f logs/app.log
tail -f logs/errors.log
```

## 🔐 Security

- **Action Allowlist**: Only pre-approved actions execute
- **Input Validation**: Pydantic validates all inputs
- **Audit Logging**: All actions logged with timestamps
- **Device Auth**: Devices authenticate before operating
- **Confirmation Rules**: High-risk actions require user confirmation

## 📈 Performance Targets

| Component | Target | Status |
|-----------|--------|--------|
| Conversation response | < 500ms | ✅ |
| Decision response | 5-30s | ✅ |
| Voice STT | < 200ms | 🔄 Phase 2 |
| API response | < 100ms | ✅ |
| Mode switch | < 100ms | ✅ |

## 🎯 Design Philosophy

1. **Local-First**: Everything possible runs locally for privacy
2. **Modular**: Features are independent and pluggable
3. **Preserved**: MAGI logic stays exactly as it was
4. **Extensible**: Easy to add new subsystems
5. **Transparent**: Reasoning is visible and explainable
6. **User-Centric**: System learns from and adapts to user

## 🎨 UI Features

The UI is designed as a futuristic command center:

- Dark theme with neon accents
- Modular panel layout
- Real-time status indicators
- Mode toggle button
- Conversation history
- Agent deliberation visualization (coming Phase 2)
- Device status panel (coming Phase 5)
- World map (coming Phase 4)

## 🐛 Troubleshooting

### Models not found

```bash
ollama pull phi4-mini-reasoning:latest
ollama pull qwen2.5:3b
ollama pull gemma2:2b
ollama pull phi3:mini
```

### Port already in use

```bash
lsof -i :8000
kill -9 <PID>
```

### CORS errors

Check `allow_origins` in `backend/main.py`

### API not responding

1. Check Ollama is running: `curl http://localhost:11434`
2. Check backend is running: `curl http://localhost:8000/health`
3. Check logs: `tail -f logs/app.log`

## 📚 Additional Resources

- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Pydantic Docs](https://docs.pydantic.dev)
- [Ollama Guide](https://ollama.ai/library)
- [React Documentation](https://react.dev)

## 📞 Support

- **Documentation**: See `docs/` folder
- **Issues**: Check existing GitHub issues
- **Questions**: Open a discussion

## 🙏 Acknowledgments

Built on the foundation of the MAGI decision system with deep respect for its multi-agent reasoning architecture.

---

**Ready to explore?** Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to understand the system design, then [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) to get running locally.
