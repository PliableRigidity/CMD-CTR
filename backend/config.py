import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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
DECISION_TIMEOUT_SECONDS = int(os.getenv("DECISION_TIMEOUT_SECONDS", "180"))

# Authentication — set API_KEY to enable; empty = disabled (localhost always passes)
API_KEY = os.getenv("API_KEY", "")

# Brain63 — Obsidian vault path (READ-ONLY knowledge source for SILVIA)
BRAIN63_VAULT_PATH = os.getenv(
    "BRAIN63_VAULT_PATH",
    "",
)
BRAIN_STEWARD_AUTODRAFT = os.getenv("BRAIN_STEWARD_AUTODRAFT", "false").lower() in ("true", "1", "yes")

# External notifications (Watch Officer alerts)
NOTIFICATION_WEBHOOK_URL     = os.getenv("NOTIFICATION_WEBHOOK_URL", "")
NOTIFICATION_WEBHOOK_FORMAT  = os.getenv("NOTIFICATION_WEBHOOK_FORMAT", "discord")
NOTIFICATION_EMAIL_HOST      = os.getenv("NOTIFICATION_EMAIL_HOST", "")
NOTIFICATION_EMAIL_PORT      = int(os.getenv("NOTIFICATION_EMAIL_PORT", "587"))
NOTIFICATION_EMAIL_USER      = os.getenv("NOTIFICATION_EMAIL_USER", "")
NOTIFICATION_EMAIL_PASS      = os.getenv("NOTIFICATION_EMAIL_PASS", "")
NOTIFICATION_EMAIL_TO        = os.getenv("NOTIFICATION_EMAIL_TO", "")
NOTIFICATION_MIN_SEVERITY    = os.getenv("NOTIFICATION_MIN_SEVERITY", "critical")

# Voice — local providers (fallback when Speaches not configured)
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", r"C:\Piper\models\en-us-ryan-high.onnx")
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "")
PIPER_USE_CUDA = os.getenv("PIPER_USE_CUDA", "false").lower() == "true"

# Voice provider selection
STT_PROVIDER = os.getenv("STT_PROVIDER", "speaches")  # speaches | whisper
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "speaches")  # speaches | piper

# ── Voice mode ────────────────────────────────────────────────────────────────
# STABLE DEFAULT is stt_only: speech-to-text only. No auto TTS, no sentence
# chunking, no follow-up listening, no continuous conversation loop. Wake word
# (or push-to-talk) captures ONE utterance, transcribes it, sends it to chat as
# text, and returns to listening. Speech output happens ONLY when the user clicks
# the manual play/replay button.
#
# Supported modes:
#   off                   — voice fully disabled
#   stt_only              — wake word → one utterance → transcribe → chat (STABLE DEFAULT)
#   push_to_talk          — manual mic button → one utterance → transcribe → chat
#   wake_word             — same as stt_only (wake-word gated capture)
#   presence_experimental — the old conversational pipeline (auto TTS, follow-up,
#                           barge-in, sentence streaming). UNSTABLE — disabled by
#                           default. Was formerly "presence_fast"/"presence".
VOICE_SUPPORTED_MODES = ("off", "stt_only", "push_to_talk", "wake_word", "presence_experimental")
VOICE_MODE = os.getenv("VOICE_MODE", "stt_only")
# Legacy aliases → presence_experimental (kept disabled unless explicitly opted in)
if VOICE_MODE in ("presence", "presence_fast"):
    VOICE_MODE = "presence_experimental"
if VOICE_MODE not in VOICE_SUPPORTED_MODES:
    VOICE_MODE = "stt_only"

# Conversational features — OFF in stable mode. Only honoured by presence_experimental.
VOICE_AUTO_TTS = os.getenv("VOICE_AUTO_TTS", "false").lower() in ("true", "1", "yes")
VOICE_FOLLOWUP_ENABLED = os.getenv("VOICE_FOLLOWUP_ENABLED", "false").lower() in ("true", "1", "yes")
VOICE_PRESENCE_ENABLED = (VOICE_MODE == "presence_experimental")

WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.65"))
WAKE_WORD_COOLDOWN_SECONDS = float(os.getenv("WAKE_WORD_COOLDOWN_SECONDS", "0"))  # 0=disabled for debugging; set to 2 in production
WAKE_BYPASS_COOLDOWN_CONFIDENCE = float(os.getenv("WAKE_BYPASS_COOLDOWN_CONFIDENCE", "0.95"))  # bypass cooldown when prob >= this
WAKE_CONFIRMATION_ENABLED = os.getenv("WAKE_CONFIRMATION_ENABLED", "false").lower() in ("true", "1", "yes")
WAKE_MIN_COMMAND_WORDS = int(os.getenv("WAKE_MIN_COMMAND_WORDS", "2"))
IGNORE_SYSTEM_AUDIO = os.getenv("IGNORE_SYSTEM_AUDIO", "true").lower() in ("true", "1", "yes")

# Terminal / SSH
TERMINAL_PROVIDER = os.getenv("TERMINAL_PROVIDER", "auto")  # auto | windows_terminal | cmd | powershell

# Presence Mode (Phase 16C)
VOICE_FOLLOWUP_WINDOW = int(os.getenv("VOICE_FOLLOWUP_WINDOW", "15"))
VOICE_CONFIRM_ACTIONS = os.getenv("VOICE_CONFIRM_ACTIONS", "true").lower() in ("true", "1", "yes")
DO_NOT_DISTURB = os.getenv("DO_NOT_DISTURB", "false").lower() in ("true", "1", "yes")

# Speaches — OpenAI-compatible local STT/TTS server
# IMPORTANT: Speaches and CMD-CTR must be on DIFFERENT ports.
# Speaches default Docker port is 8000; if CMD-CTR is also on 8000,
# remap Speaches in docker-compose: "8010:8000" then SPEACHES_BASE_URL=http://localhost:8010
SPEACHES_BASE_URL = os.getenv("SPEACHES_BASE_URL", os.getenv("SPEACHES_URL", ""))
SPEACHES_TRANSCRIBE_ENDPOINT = os.getenv("SPEACHES_TRANSCRIBE_ENDPOINT", "/v1/audio/transcriptions")
SPEACHES_API_KEY = os.getenv("SPEACHES_API_KEY", "speaches")
SPEACHES_STT_MODEL = os.getenv("SPEACHES_STT_MODEL", "rtlingo/mobiuslabsgmbh-faster-whisper-large-v3-turbo")
SPEACHES_TTS_MODEL = os.getenv("SPEACHES_TTS_MODEL", "speaches-ai/Kokoro-82M-v1.0-ONNX")
SPEACHES_TTS_VOICE = os.getenv("SPEACHES_TTS_VOICE", "af_aoede")

# Backward compat alias
SPEACHES_URL = SPEACHES_BASE_URL

# Vision (Phase 12F) — PAUSED/DEFERRED
# Set ENABLE_VISION_INVENTORY=true in .env to re-enable the experimental vision pipeline.
# When false (default) all /hardware/vision/* endpoints return 503 and no Ollama calls are made.
# Productivity (Phase 12G) — Gmail, Google Calendar, Google Contacts
# Create credentials at https://console.cloud.google.com/ (OAuth 2.0 Client ID → Web Application)
# Register the redirect URI below as an Authorized Redirect URI in the Google Cloud Console.
GOOGLE_CLIENT_ID           = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET       = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI  = os.getenv(
    "GOOGLE_OAUTH_REDIRECT_URI",
    f"http://localhost:{os.getenv('APP_PORT', '8000')}/api/productivity/auth/callback",
)
# Optional: path to a downloaded client_secrets JSON from Google Cloud Console.
# If set, GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are ignored.
GOOGLE_CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CLIENT_SECRETS_FILE", "")

# Log Google config status at startup (without leaking the secret)
import logging as _logging
_glog = _logging.getLogger("silvia.google_config")
_glog.info(
    "[Google OAuth] config — client_id_present=%s  client_secret_present=%s  "
    "secrets_file=%r  redirect_uri=%s",
    bool(GOOGLE_CLIENT_ID),
    bool(GOOGLE_CLIENT_SECRET),
    GOOGLE_CLIENT_SECRETS_FILE or "(not set)",
    GOOGLE_OAUTH_REDIRECT_URI,
)

ENABLE_VISION_INVENTORY      = os.getenv("ENABLE_VISION_INVENTORY", "false").lower() == "true"
# Telegram Chat Bridge (Phase 14C+)
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USER_IDS: set[int] = {
    int(uid.strip())
    for uid in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
    if uid.strip().lstrip("-").isdigit()
}
TELEGRAM_SESSION_ID = os.getenv("TELEGRAM_SESSION_ID", "telegram")

# Stability controls
SSH_REQUIRES_APPROVAL = os.getenv("SSH_REQUIRES_APPROVAL", "false").lower() in ("true", "1", "yes")
SILVIA_SAFE_MODE = os.getenv("SILVIA_SAFE_MODE", "false").lower() in ("true", "1", "yes")

# Capability execution — set to "false" to run in simulation mode (no real commands sent)
ENABLE_CAPABILITY_EXECUTION  = os.getenv("ENABLE_CAPABILITY_EXECUTION", "true").lower() == "true"
ANTHROPIC_API_KEY           = os.getenv("ANTHROPIC_API_KEY", "")
# The following vars are only read when ENABLE_VISION_INVENTORY=true:
VISION_PROVIDER             = os.getenv("VISION_PROVIDER", "auto")
VISION_MODEL_ANTHROPIC      = os.getenv("VISION_MODEL_ANTHROPIC", "claude-haiku-4-5-20251001")
VISION_MODEL_OLLAMA         = os.getenv("VISION_MODEL", os.getenv("VISION_MODEL_OLLAMA", "gemma4:e4b"))
VISION_FALLBACK_MODEL       = os.getenv("VISION_FALLBACK_MODEL", "gemma4:e2b")
VISION_LEGACY_FALLBACK      = os.getenv("VISION_LEGACY_FALLBACK", "llava:latest")
VISION_CONFIDENCE_THRESHOLD = float(os.getenv("VISION_CONFIDENCE_THRESHOLD", "0.65"))

WORLD_MODEL_NAME = "phi4-mini-reasoning:latest"
# Switched from gemma3:4b → qwen2.5:3b (2026-06-28): gemma3's Sliding-Window
# Attention trips Ollama 0.30.11's prompt-cache path, adding a fixed ~1.9s
# load_duration per request. qwen2.5:3b (non-SWA) cuts per-turn latency ~5s→~2s
# and roughly doubles generation throughput (127→229 tok/s) on this machine.
CONVERSATION_MODEL = "qwen2.5:3b"
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
