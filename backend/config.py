from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
ROOT_PROMPTS_DIR = BASE_DIR.parent / "prompts"

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

WORLD_MODEL_NAME = "phi4-mini-reasoning:latest"
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
