import json

from backend.config import (
    ACTION_GENERATOR_MODEL,
    ACTION_GENERATOR_PROMPT,
    ACTION_GENERATOR_TEMPERATURE,
    MAX_ACTIONS,
    MIN_ACTIONS,
)
from backend.modes.decision.models import ask_ollama_structured, load_prompt
from backend.modes.decision.schemas import (
    ActionSet,
    CandidateAction,
    GeneratedActionSetPayload,
    SituationModel,
)


def build_action_generator_message(situation_model: SituationModel) -> str:
    return json.dumps(situation_model.model_dump(), indent=2)


def _normalize_actions(payload: GeneratedActionSetPayload) -> ActionSet:
    actions: list[CandidateAction] = []
    for index, action in enumerate(payload.actions[:MAX_ACTIONS], start=1):
        actions.append(
            CandidateAction(
                id=f"ACTION_{index}",
                title=action.title.strip(),
                description=action.description.strip(),
            )
        )

    if len(actions) < MIN_ACTIONS:
        raise ValueError("Action generator returned fewer than three actions.")

    return ActionSet(actions=actions)


def generate_actions(situation_model: SituationModel) -> ActionSet:
    payload = ask_ollama_structured(
        model_name=ACTION_GENERATOR_MODEL,
        system_prompt=load_prompt(ACTION_GENERATOR_PROMPT),
        user_message=build_action_generator_message(situation_model),
        response_model=GeneratedActionSetPayload,
        temperature=ACTION_GENERATOR_TEMPERATURE,
    )
    return _normalize_actions(payload)
