import json
from pathlib import Path
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from backend.config import KEEP_ALIVE, OLLAMA_CHAT_URL, TIMEOUT_SECONDS

T = TypeVar("T", bound=BaseModel)


class OllamaStructuredError(RuntimeError):
    pass


def load_prompt(prompt_path: str | Path) -> str:
    return Path(prompt_path).read_text(encoding="utf-8").strip()


def parse_json_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise OllamaStructuredError(f"Model returned invalid JSON: {content}") from exc


def ask_ollama_structured(
    model_name: str,
    system_prompt: str,
    user_message: str,
    response_model: type[T],
    temperature: float,
) -> T:
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "format": response_model.model_json_schema(),
        "options": {"temperature": temperature},
    }

    try:
        response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaStructuredError(f"Ollama request failed: {exc}") from exc

    message = response.json().get("message", {})
    content = message.get("content", "")
    parsed = parse_json_content(content)

    try:
        return response_model.model_validate(parsed)
    except ValidationError as exc:
        raise OllamaStructuredError(f"Structured validation failed: {exc}") from exc
