import asyncio
import time

from backend.app.models.assistant import AgentStatus, AssistantRequest, AssistantResponse, CommandLogEntry
from backend.modes.decision.orchestrator import run_pipeline
from backend.modes.decision.schemas import RawUserInput


class DecisionService:
    async def handle(self, request: AssistantRequest) -> AssistantResponse:
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    run_pipeline,
                    RawUserInput(
                        problem=request.query,
                        goal=request.goal or "",
                        constraints=request.constraints or [],
                    ),
                ),
                timeout=12,
            )
            elapsed = (time.perf_counter() - started) * 1000
            agents = []
            for name, vote in result.final_votes.items():
                agents.append(
                    AgentStatus(
                        name=name,
                        role="decision_agent",
                        state="complete",
                        confidence=vote.confidence,
                        summary=vote.reason,
                    )
                )
            agents.append(
                AgentStatus(
                    name="VIVEKA",
                    role="chair",
                    state="complete",
                    summary=result.chair_summary.summary,
                )
            )
            return AssistantResponse(
                mode="decision",
                title="Decision Mode",
                answer=result.chair_summary.summary,
                reasoning=result.chair_summary.dominant_reasoning,
                processing_time_ms=elapsed,
                agents=agents,
                logs=[
                    CommandLogEntry(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        title="Decision pipeline completed",
                        detail=f"MAGI decision engine evaluated {len(result.actions)} candidate actions.",
                    )
                ],
                payload={
                    "majority_decision": result.majority_decision,
                    "recommended_action": result.chair_summary.recommended_action,
                    "vote_counts": result.vote_counts,
                    "situation_model": result.situation_model.model_dump(),
                    "actions": [item.model_dump() for item in result.actions],
                    "first_round": {key: value.model_dump() for key, value in result.first_round.items()},
                    "final_votes": {key: value.model_dump() for key, value in result.final_votes.items()},
                    "chair_summary": result.chair_summary.model_dump(),
                },
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - started) * 1000
            return AssistantResponse(
                mode="decision",
                title="Decision Mode",
                answer="Decision Mode is wired to the MAGI engine, but the local deliberation stack is currently unavailable.",
                reasoning=str(exc),
                processing_time_ms=elapsed,
                agents=[
                    AgentStatus(
                        name="Decision Engine",
                        role="magi_subsystem",
                        state="error",
                        summary="The preserved MAGI workflow could not complete this request.",
                    )
                ],
                logs=[
                    CommandLogEntry(
                        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        title="Decision pipeline failed",
                        detail=str(exc),
                        level="error",
                    )
                ],
                payload={"error": str(exc)},
            )
