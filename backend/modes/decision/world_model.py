import json

from backend.config import WORLD_MODEL_NAME, WORLD_MODEL_PROMPT, WORLD_MODEL_TEMPERATURE
from backend.modes.decision.models import ask_ollama_structured, load_prompt
from backend.modes.decision.schemas import RawUserInput, SituationModel, WorldModelPayload


def build_world_model_message(user_input: RawUserInput) -> str:
    return json.dumps(user_input.model_dump(), indent=2)


def generate_world_model(user_input: RawUserInput) -> SituationModel:
    payload = ask_ollama_structured(
        model_name=WORLD_MODEL_NAME,
        system_prompt=load_prompt(WORLD_MODEL_PROMPT),
        user_message=build_world_model_message(user_input),
        response_model=WorldModelPayload,
        temperature=WORLD_MODEL_TEMPERATURE,
    )
    return SituationModel.model_validate(payload.model_dump())
