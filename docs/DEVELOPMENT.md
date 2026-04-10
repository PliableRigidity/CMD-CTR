# Development Setup Guide

## Prerequisites

- Python 3.9+
- pip or conda
- Git
- Ollama (for local LLM) - [Download here](https://ollama.ai)
- Node.js 16+ (for UI development)

## Backend Setup

### 1. Create Python Environment

```bash
cd backend

# Using venv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Or using conda
conda create -n magi-assistant python=3.11
conda activate magi-assistant
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Ollama

Start Ollama service:

```bash
ollama serve
```

In another terminal, pull required models:

```bash
# For decision mode (MAGI)
ollama pull phi4-mini-reasoning:latest
ollama pull qwen2.5:3b
ollama pull gemma2:2b
ollama pull phi3:mini

# For conversation mode (lighter models)
ollama pull mistral:latest
ollama pull neural-chat:latest
```

### 4. Environment Configuration

Create a `.env` file in the root directory:

```bash
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_URL=http://localhost:11434/api/chat

# Models
WORLD_MODEL_NAME=phi4-mini-reasoning:latest
ACTION_GENERATOR_MODEL=qwen2.5:3b
SARASWATI_MODEL=phi4-mini-reasoning:latest
LAKSHMI_MODEL=gemma2:2b
DURGA_MODEL=qwen2.5:3b
VIVEKA_MODEL=phi3:mini

# Conversation
CONVERSATION_MODEL=mistral:latest
CONVERSATION_TEMPERATURE=0.7

# Logging
LOG_LEVEL=INFO

# Features (enable/disable subsystems)
ENABLE_VOICE=false
ENABLE_WORLD_EVENTS=false
ENABLE_ACTIONS=false
ENABLE_DEVICES=false
ENABLE_MEMORY_STORE=false
```

### 5. Run the Backend

```bash
# Simple mode
python main.py

# Or with uvicorn (development with auto-reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/docs` (Swagger UI)

## Frontend Setup

### 1. Install Dependencies

```bash
cd ui
npm install
```

### 2. Environment Configuration

Create `ui/.env`:

```
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

### 3. Run Development Server

```bash
npm run dev
```

The UI will be available at `http://localhost:5173`

### 4. Build for Production

```bash
npm run build
```

## Running Everything

### Option A: Terminal Tabs

Terminal 1:
```bash
ollama serve
```

Terminal 2:
```bash
cd backend
python main.py
```

Terminal 3:
```bash
cd ui
npm run dev
```

### Option B: Using a Script

Create `start_all.sh`:

```bash
#!/bin/bash
echo "Starting Ollama..."
ollama serve &

sleep 2

echo "Starting Backend..."
cd backend
python main.py &

sleep 2

echo "Starting Frontend..."
cd ui
npm run dev &

wait
```

Run with:
```bash
bash start_all.sh
```

## Testing the API

### Using curl

```bash
# Conversation mode
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France?",
    "mode": "conversation"
  }'

# Decision mode
curl -X POST http://localhost:8000/api/decide \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Should I learn Python or JavaScript?",
    "goal": "Get a job in tech",
    "constraints": ["Only 3 months to learn"],
    "mode": "decision"
  }'
```

### Using Python

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Conversation request
response = requests.post(
    f"{BASE_URL}/api/chat",
    json={
        "query": "What is the capital of France?",
        "mode": "conversation"
    }
)
print(json.dumps(response.json(), indent=2))
```

### Using Postman or Insomnia

1. Import the API collection
2. Set base URL to `http://localhost:8000`
3. Use provided request templates

## Debugging

### Enable Debug Logging

Modify `backend/utils/logger.py`:

```python
setup_logging(level=logging.DEBUG)
```

Or set environment variable:

```bash
LOG_LEVEL=DEBUG python main.py
```

### Check Logs

```bash
tail -f logs/app.log       # Follow app logs
tail -f logs/errors.log    # Follow error logs
```

### Debug MAGI Pipeline

Add debug prints in decision mode:

```python
# In backend/modes/decision/orchestrator.py
logger.debug(f"Situation model: {situation_model}")
logger.debug(f"Actions: {action_set}")
```

## Common Issues

### Ollama Connection Refused

```
Error: Connection to http://localhost:11434 refused
```

**Solution**: Make sure Ollama is running:
```bash
ollama serve
```

### Model Not Found

```
Error: Model not found: phi4-mini-reasoning:latest
```

**Solution**: Pull the model:
```bash
ollama pull phi4-mini-reasoning:latest
```

### Port Already in Use

```
Error: Address already in use: ('0.0.0.0', 8000)
```

**Solution**: Use a different port:
```bash
python main.py --port 8001
```

Or kill the process:
```bash
lsof -i :8000
kill -9 <PID>
```

### CORS Issues

If frontend can't reach backend, check CORS settings in `backend/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_conversation.py

# Run with coverage
pytest --cov=backend tests/

# Run async tests
pytest -v -s tests/test_async.py
```

## IDE Setup

### VS Code

Install extensions:
- Python
- Pylance
- FastAPI
- REST Client

`.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true
  }
}
```

### PyCharm

- Right-click on `venv` → "Configure Python Interpreter"
- Run configurations:
  - Script: `backend/main.py`
  - Working directory: Project root

## Next Steps

1. **Understand the architecture**: Read [ARCHITECTURE.md](ARCHITECTURE.md)
2. **Learn about modes**: Read [MODES.md](MODES.md)
3. **Explore existing MAGI system**: Check `backend/modes/decision/`
4. **Start implementing Phase 2**: Voice Pipeline ([VOICE.md](VOICE.md))

## Useful Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Pydantic Documentation](https://docs.pydantic.dev)
- [Ollama Documentation](https://ollama.ai/library)
- [React Documentation](https://react.dev)
- [Vite Documentation](https://vitejs.dev)

## Getting Help

- Check logs in `logs/` directory
- Review API documentation at `/docs` endpoint
- Ask in development channel
- Open an issue with detailed error messages
