import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
ROOT_PROMPTS_DIR = BASE_DIR.parent / "prompts"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

# Tools
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
SEARXNG_URL = os.getenv("SEARXNG_URL", "")  # Empty = disabled; set in .env to enable
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8001,http://localhost:8001",
    ).split(",")
    if origin.strip()
]
DECISION_TIMEOUT_SECONDS = int(os.getenv("DECISION_TIMEOUT_SECONDS", "45"))

# Voice — local providers (fallback when Speaches not configured)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", r"C:\Piper\models\en-us-ryan-high.onnx")
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "")
PIPER_USE_CUDA = os.getenv("PIPER_USE_CUDA", "false").lower() == "true"

# Speaches — OpenAI-compatible local STT/TTS server (same one used by llm-voice-assistant)
# When SPEACHES_URL is set, Speaches is preferred over local Whisper/Piper.
# PORT NOTE: Speaches default port is 8000 (same as CMD-CTR). Change Speaches docker-compose
# to "9000:8000" so it exposes on 9000, then set SPEACHES_URL=http://localhost:9000 in .env
SPEACHES_URL = os.getenv("SPEACHES_URL", "")  # empty = disabled, use local Whisper/Piper
SPEACHES_API_KEY = os.getenv("SPEACHES_API_KEY", "speaches")
SPEACHES_STT_MODEL = os.getenv("SPEACHES_STT_MODEL", "rtlingo/mobiuslabsgmbh-faster-whisper-large-v3-turbo")
SPEACHES_TTS_MODEL = os.getenv("SPEACHES_TTS_MODEL", "speaches-ai/Kokoro-82M-v1.0-ONNX")
SPEACHES_TTS_VOICE = os.getenv("SPEACHES_TTS_VOICE", "af_aoede")

WORLD_MODEL_NAME = "phi4-mini-reasoning:latest"
CONVERSATION_MODEL = "gemma3:4b"
ACTION_GENERATOR_MODEL = "qwen2.5:3b"
SARASWATI_MODEL = "phi4-mini-reasoning:latest"
LAKSHMI_MODEL = "gemma2:2b"
DURGA_MODEL = "qwen2.5:3b"
VIVEKA_MODEL = "phi3:mini"

WORLD_MODEL_PROMPT = PROMPTS_DIR / "world_model.txt"
ACTION_GENERATOR_PROMPT = PROMPTS_DIR / "action_generator.txt"
SARASWATI_PROMPT = PROMPTS_DIR / "saraswati.txt"
LAKSHMI_PROMPT = PROMPTS_DIR / "lakshmi.txt"
DURGA_PROMPT = PROMPTS_DIR / "durga.txt"
DEBATE_PROMPT = PROMPTS_DIR / "debate_response.txt"
CHAIR_PROMPT = ROOT_PROMPTS_DIR / "chair.txt"

WORLD_MODEL_TEMPERATURE = 0.2
ACTION_GENERATOR_TEMPERATURE = 0.7
SARASWATI_TEMPERATURE = 0.2
LAKSHMI_TEMPERATURE = 0.4
DURGA_TEMPERATURE = 0.8
VIVEKA_TEMPERATURE = 0.3

TIMEOUT_SECONDS = 120
KEEP_ALIVE = "-1m"

SPECIAL_SELECTIONS = {"ABSTAIN", "UNDECIDED"}
MIN_ACTIONS = 3
MAX_ACTIONS = 5

BRAIN_CONFIGS = [
    {
        "name": "SARASWATI",
        "model": SARASWATI_MODEL,
        "prompt_path": SARASWATI_PROMPT,
        "temperature": SARASWATI_TEMPERATURE,
    },
    {
        "name": "LAKSHMI",
        "model": LAKSHMI_MODEL,
        "prompt_path": LAKSHMI_PROMPT,
        "temperature": LAKSHMI_TEMPERATURE,
    },
    {
        "name": "DURGA",
        "model": DURGA_MODEL,
        "prompt_path": DURGA_PROMPT,
        "temperature": DURGA_TEMPERATURE,
    },
]
