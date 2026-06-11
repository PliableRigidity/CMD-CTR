# SILVIA Command Center

Local-first AI operating system. Node registry, infrastructure telemetry, robotics command & control, semantic memory, voice interface, and multi-agent decision-making — all running on your machine via Ollama.

## Quick Start

```bash
# 1. Pull required models
ollama pull gemma3:4b
ollama pull qwen2.5:3b
ollama pull hermes3
ollama pull nomic-embed-text

# 2. Install backend deps
pip install -r backend/requirements.txt

# 3. Install frontend deps
cd frontend && npm install && cd ..

# 4. Create .env in project root
echo "OPENWEATHER_API_KEY=your_key_here" > .env
echo "TIMEZONE=Asia/Kolkata" >> .env

# 5. Start backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Start frontend (separate terminal)
cd frontend && npm run dev
```

Open **http://localhost:5173**

## Documentation

Full documentation: **[docs/SILVIA.md](docs/SILVIA.md)**

Covers: setup, all chat commands, node registry, silvia-agent deployment, robotics, Hermes multi-step execution, semantic memory, voice, Watch Officer alerts, configuration reference, and troubleshooting.
