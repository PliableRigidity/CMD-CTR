import json

from backend.modes.decision.action_generator import generate_actions
from backend.config import CHAIR_PROMPT, VIVEKA_MODEL, VIVEKA_TEMPERATURE
from backend.modes.decision.debate import run_debate_round, run_first_round
from backend.modes.decision.models import OllamaStructuredError, ask_ollama_structured, load_prompt
from backend.modes.decision.schemas import ChairSummary, FinalDecision, RawUserInput
from backend.modes.decision.voting import summarize_votes
from backend.modes.decision.world_model import generate_world_model


def _build_chair_message(
    majority_decision: str,
    situation_model,
    actions,
    final_votes,
) -> str:
    payload = {
        "majority_decision": majority_decision,
        "situation_model": situation_model.model_dump(),
        "actions": [action.model_dump() for action in actions],
        "final_votes": {
            name: vote.model_dump(exclude={"valid", "error"}) for name, vote in final_votes.items()
        },
    }
    return json.dumps(payload, indent=2)


def _fallback_chair_summary(majority_decision: str) -> ChairSummary:
    return ChairSummary(
        final_decision=majority_decision,
        dominant_reasoning="VIVEKA summary unavailable",
        summary="Python determined the result, but the chair summary could not be generated.",
        recommended_action=majority_decision,
    )


def run_pipeline(user_input: RawUserInput) -> FinalDecision:
    situation_model = generate_world_model(user_input)
    action_set = generate_actions(situation_model)
    first_round = run_first_round(situation_model, action_set)
    final_votes = run_debate_round(situation_model, action_set, first_round)

    vote_summary = summarize_votes(
        actions=[action.id for action in action_set.actions],
        responses=final_votes,
    )

    try:
        chair_summary = ask_ollama_structured(
            model_name=VIVEKA_MODEL,
            system_prompt=load_prompt(CHAIR_PROMPT),
            user_message=_build_chair_message(
                majority_decision=vote_summary.majority_decision,
                situation_model=situation_model,
                actions=action_set.actions,
                final_votes=final_votes,
            ),
            response_model=ChairSummary,
            temperature=VIVEKA_TEMPERATURE,
        )
        chair_summary = chair_summary.model_copy(
            update={"final_decision": vote_summary.majority_decision}
        )
    except OllamaStructuredError:
        chair_summary = _fallback_chair_summary(vote_summary.majority_decision)

    return FinalDecision(
        situation_model=situation_model,
        actions=action_set.actions,
        first_round=first_round,
        final_votes=final_votes,
        majority_decision=vote_summary.majority_decision,
        vote_counts=vote_summary.vote_counts,
        chair_summary=chair_summary,
    )
