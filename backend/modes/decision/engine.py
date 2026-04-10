"""
Decision mode engine.

Multi-agent deliberation system (MAGI) for complex decision-making.
Uses structured debate, voting, and chair summarization.
"""

import asyncio
import time
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.modes.base import Mode, ModeType, ModeRequest, ModeResponse
from backend.modes.decision.orchestrator import run_pipeline
from backend.modes.decision.schemas import RawUserInput, FinalDecision
from backend.utils import get_logger


logger = get_logger(__name__)


class DecisionRequest(ModeRequest):
    """Decision-specific request."""
    goal: Optional[str] = None
    constraints: Optional[list[str]] = None
    include_world_model: bool = Field(default=True)
    include_debate: bool = Field(default=True)


class DecisionResponse(ModeResponse):
    """Decision-specific response."""
    final_decision: str
    reasoning: str
    recommended_action: str
    situation_model: Optional[Dict[str, Any]] = None
    actions_considered: Optional[list[Dict[str, Any]]] = None
    debate_summary: Optional[Dict[str, Any]] = None


class DecisionEngine(Mode):
    """
    MAGI decision mode.

    Processes complex decisions through multi-agent deliberation:
    1. World modeling
    2. Action generation
    3. Multi-round debate (Durga, Lakshmi, Saraswati)
    4. Voting and chair summarization

    Suitable for:
    - Complex decisions
    - Ethical dilemmas
    - Strategic planning
    - Risk assessment
    """

    def __init__(self):
        """Initialize decision engine."""
        super().__init__("MAGI Decision", ModeType.DECISION)
        self.max_processing_time = 300  # 5 minutes timeout
        logger.info("Decision engine initialized")

    async def validate_input(self, request: ModeRequest) -> bool:
        """
        Validate decision request.

        Args:
            request: Request to validate

        Returns:
            True if valid
        """
        if not isinstance(request.query, str) or len(request.query.strip()) == 0:
            logger.warning("Invalid decision request: empty query")
            return False

        if len(request.query) > 5000:  # Decision queries can be detailed
            logger.warning("Invalid decision request: query too long")
            return False

        return True

    async def process(self, request: ModeRequest) -> DecisionResponse:
        """
        Process request through MAGI deliberation pipeline.

        Args:
            request: User decision query and context

        Returns:
            Decision response with deliberation results
        """
        start_time = time.time()

        # Validate input
        if not await self.validate_input(request):
            logger.error("Decision request validation failed")
            return DecisionResponse(
                mode=ModeType.DECISION,
                answer="I need a clear decision question to deliberate on.",
                confidence=0.0,
                final_decision="Unable to process",
                reasoning="Invalid input",
                recommended_action="Please rephrase your decision question",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        try:
            # Convert to MAGI input format
            magi_input = RawUserInput(
                problem=request.query,
                goal=getattr(request, 'goal', None),
                constraints=getattr(request, 'constraints', [])
            )

            logger.info(f"Starting MAGI deliberation for: {request.query[:50]}...")

            # Run the full MAGI pipeline (in thread pool since it's sync)
            result: FinalDecision = await asyncio.to_thread(run_pipeline, magi_input)

            processing_time = (time.time() - start_time) * 1000

            logger.info(f"MAGI deliberation completed in {processing_time:.2f}ms")

            # Format response
            return DecisionResponse(
                mode=ModeType.DECISION,
                answer=result.chair_summary.summary,
                confidence=0.95,  # MAGI decisions are high confidence
                final_decision=result.chair_summary.final_decision,
                reasoning=result.chair_summary.dominant_reasoning,
                recommended_action=result.chair_summary.recommended_action,
                situation_model=result.situation_model.model_dump() if result.situation_model else None,
                actions_considered=[action.model_dump() for action in result.actions.actions] if result.actions else None,
                debate_summary=result.vote_summary.model_dump() if result.vote_summary else None,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.exception(f"Error in MAGI deliberation: {e}")
            return DecisionResponse(
                mode=ModeType.DECISION,
                answer=f"I encountered an error during deliberation: {str(e)}",
                confidence=0.0,
                final_decision="Error occurred",
                reasoning="System error",
                recommended_action="Please try again or simplify the question",
                processing_time_ms=(time.time() - start_time) * 1000,
            )

    async def activate(self) -> None:
        """Activate decision mode."""
        await super().activate()
        logger.info("MAGI decision mode activated")

    async def deactivate(self) -> None:
        """Deactivate decision mode."""
        await super().deactivate()
        logger.info("MAGI decision mode deactivated")

    def get_capabilities(self) -> Dict[str, Any]:
        """Get decision mode capabilities."""
        caps = super().get_capabilities()
        caps.update({
            "supported_features": [
                "multi_agent_deliberation",
                "world_modeling",
                "structured_debate",
                "voting_system",
                "chair_summarization",
            ],
            "processing_time": "2-5 minutes",
            "max_query_length": 5000,
            "agents": ["Durga", "Lakshmi", "Saraswati", "Chair"],
        })
        return caps