import json

from backend.config import BRAIN_CONFIGS, DEBATE_PROMPT, SPECIAL_SELECTIONS
from backend.modes.decision.models import OllamaStructuredError, ask_ollama_structured, load_prompt
from backend.modes.decision.schemas import (
    ActionSet,
    BrainResponse,
    BrainRoundOnePayload,
    BrainRoundTwoPayload,
    SituationModel,
)


def _valid_action_ids(actions: ActionSet) -> set[str]:
    return {action.id for action in actions.actions}


def _validate_selection(selection: str, actions: ActionSet) -> str:
    valid_values = _valid_action_ids(actions) | SPECIAL_SELECTIONS
    if selection not in valid_values:
        raise ValueError(f"Invalid action selection: {selection}")
    return selection


def _fallback_response(brain_name: str, message: str) -> BrainResponse:
    return BrainResponse(
        brain_name=brain_name,
        selected_action="ABSTAIN",
        confidence=0,
        reason="Model call failed",
        risk="No reliable evaluation was produced",
        next_action="Inspect Ollama connectivity or prompts",
        critique=message,
        changed_mind=False,
        valid=False,
        error=message,
    )


def _round_one_message(situation_model: SituationModel, actions: ActionSet) -> str:
    payload = {
        "situation_model": situation_model.model_dump(),
        "actions": [action.model_dump() for action in actions.actions],
    }
    return json.dumps(payload, indent=2)


def _round_two_message(
    situation_model: SituationModel,
    actions: ActionSet,
    current_response: BrainResponse,
    other_responses: list[BrainResponse],
) -> str:
    payload = {
        "situation_model": situation_model.model_dump(),
        "actions": [action.model_dump() for action in actions.actions],
        "current_position": current_response.model_dump(
            exclude={"valid", "error", "brain_name"}
        ),
        "peer_feedback": [
            response.model_dump(exclude={"valid", "error"}) for response in other_responses
        ],
    }
    return json.dumps(payload, indent=2)


def run_first_round(situation_model: SituationModel, actions: ActionSet) -> dict[str, BrainResponse]:
    results: dict[str, BrainResponse] = {}

    for brain in BRAIN_CONFIGS:
        brain_name = brain["name"]
        try:
            payload = ask_ollama_structured(
                model_name=brain["model"],
                system_prompt=load_prompt(brain["prompt_path"]),
                user_message=_round_one_message(situation_model, actions),
                response_model=BrainRoundOnePayload,
                temperature=brain["temperature"],
            )
            results[brain_name] = BrainResponse(
                brain_name=brain_name,
                selected_action=_validate_selection(payload.selected_action, actions),
                confidence=payload.confidence,
                reason=payload.reason,
                risk=payload.risk,
                next_action=payload.next_action,
                critique=payload.critique,
                changed_mind=False,
                valid=True,
            )
        except (OllamaStructuredError, ValueError) as exc:
            results[brain_name] = _fallback_response(brain_name, str(exc))

    return results


def run_debate_round(
    situation_model: SituationModel,
    actions: ActionSet,
    first_round: dict[str, BrainResponse],
) -> dict[str, BrainResponse]:
    debate_prompt = load_prompt(DEBATE_PROMPT)
    final_votes: dict[str, BrainResponse] = {}

    for brain in BRAIN_CONFIGS:
        brain_name = brain["name"]
        peers = [response for name, response in first_round.items() if name != brain_name]

        try:
            payload = ask_ollama_structured(
                model_name=brain["model"],
                system_prompt=f"{load_prompt(brain['prompt_path'])}\n\n{debate_prompt}",
                user_message=_round_two_message(
                    situation_model=situation_model,
                    actions=actions,
                    current_response=first_round[brain_name],
                    other_responses=peers,
                ),
                response_model=BrainRoundTwoPayload,
                temperature=brain["temperature"],
            )
            final_votes[brain_name] = BrainResponse(
                brain_name=brain_name,
                selected_action=_validate_selection(payload.selected_action, actions),
                confidence=payload.confidence,
                reason=payload.reason,
                risk=payload.risk,
                next_action=payload.next_action,
                critique=first_round[brain_name].critique,
                changed_mind=payload.changed_mind,
                valid=True,
            )
        except (KeyError, OllamaStructuredError, ValueError) as exc:
            final_votes[brain_name] = _fallback_response(brain_name, str(exc))

    return final_votes
