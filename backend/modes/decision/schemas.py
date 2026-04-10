from typing import Dict, List

from pydantic import BaseModel, Field, field_validator

from backend.config import MAX_ACTIONS, MIN_ACTIONS


class RawUserInput(BaseModel):
    problem: str = Field(min_length=1)
    goal: str = ""
    constraints: List[str] = Field(default_factory=list)

    @field_validator("constraints")
    @classmethod
    def normalize_constraints(cls, value: List[str]) -> List[str]:
        return [item.strip() for item in value if item and item.strip()]


class SituationModel(BaseModel):
    problem_summary: str
    goal: str
    constraints: List[str]
    risks: List[str]
    unknowns: List[str]


class CandidateAction(BaseModel):
    id: str
    title: str
    description: str


class ActionSet(BaseModel):
    actions: List[CandidateAction] = Field(min_length=MIN_ACTIONS, max_length=MAX_ACTIONS)


class BrainResponse(BaseModel):
    brain_name: str
    selected_action: str
    confidence: int = Field(ge=0, le=100)
    reason: str
    risk: str
    next_action: str
    critique: str = ""
    changed_mind: bool = False
    valid: bool = True
    error: str | None = None


class FinalVote(BaseModel):
    brain_name: str
    selected_action: str
    confidence: int = Field(ge=0, le=100)


class VoteSummary(BaseModel):
    majority_decision: str
    vote_counts: Dict[str, int]
    final_votes: Dict[str, FinalVote]


class ChairSummary(BaseModel):
    final_decision: str
    dominant_reasoning: str
    summary: str
    recommended_action: str


class FinalDecision(BaseModel):
    situation_model: SituationModel
    actions: List[CandidateAction]
    first_round: Dict[str, BrainResponse]
    final_votes: Dict[str, BrainResponse]
    majority_decision: str
    vote_counts: Dict[str, int]
    chair_summary: ChairSummary


class WorldModelPayload(BaseModel):
    problem_summary: str
    goal: str
    constraints: List[str]
    risks: List[str]
    unknowns: List[str]


class ActionSetPayload(BaseModel):
    actions: List[CandidateAction] = Field(min_length=MIN_ACTIONS, max_length=MAX_ACTIONS)


class GeneratedActionPayload(BaseModel):
    title: str
    description: str


class GeneratedActionSetPayload(BaseModel):
    actions: List[GeneratedActionPayload] = Field(
        min_length=MIN_ACTIONS,
        max_length=MAX_ACTIONS,
    )


class BrainRoundOnePayload(BaseModel):
    selected_action: str
    confidence: int = Field(ge=0, le=100)
    reason: str
    risk: str
    next_action: str
    critique: str


class BrainRoundTwoPayload(BaseModel):
    selected_action: str
    confidence: int = Field(ge=0, le=100)
    reason: str
    risk: str
    next_action: str
    changed_mind: bool
