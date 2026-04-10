"""
Assistant router and dispatcher.

Routes user queries to the appropriate operating mode and orchestrates
interaction between modes and subsystems.

Supports:
- Conversation mode (fast, direct responses)
- Decision mode (MAGI multi-agent deliberation)
- Auto-detection based on query content
"""

from typing import Optional, List, Dict
from enum import Enum
import time

from pydantic import BaseModel, Field

from backend.modes.base import Mode, ModeType
from backend.modes.conversation import ConversationEngine
from backend.modes.decision.engine import DecisionEngine
from backend.utils import get_logger


logger = get_logger(__name__)


class ModeSelector(str, Enum):
    """Strategies for selecting the mode."""
    AUTO = "auto"              # Automatic based on query analysis
    CONVERSATION = "conversation"  # Force conversation mode
    DECISION = "decision"      # Force decision mode


class AssistantRequest(BaseModel):
    """Unified request model for all modes."""
    query: str = Field(..., min_length=1, max_length=10000)
    mode: Optional[str] = Field(default="auto", pattern="^(auto|conversation|decision)$")
    goal: Optional[str] = None
    constraints: Optional[List[str]] = None
    context: Optional[Dict] = Field(default_factory=dict)
    user_id: str = Field(default="user")
    session_id: str = Field(default="session")
    metadata: Optional[Dict] = Field(default_factory=dict)


class AssistantResponse(BaseModel):
    """Unified response model from all modes."""
    mode: str
    answer: str
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    decision_data: Optional[Dict] = None  # For decision mode details
    processing_time_ms: float
    metadata: Optional[Dict] = Field(default_factory=dict)


class AssistantRouter:
    """
    Routes user queries to appropriate operating mode.
    
    Responsibilities:
    1. Register available modes
    2. Determine which mode to use (auto-detect or forced)
    3. Execute mode and return response
    4. Handle mode switching
    5. Aggregate responses from multiple modes if needed
    """
    
    def __init__(self):
        """Initialize the assistant router."""
        self.modes: Dict[str, Mode] = {}
        self.active_mode: Optional[str] = None
        self.default_mode = "conversation"
        self._register_default_modes()
        logger.info("AssistantRouter initialized")
    
    def _register_default_modes(self) -> None:
        """Register built-in modes."""
        # Conversation mode (always available)
        conv_engine = ConversationEngine()
        self.modes["conversation"] = conv_engine
        logger.info(f"Registered mode: conversation")
        
        # Decision mode (MAGI deliberation)
        decision_engine = DecisionEngine()
        self.modes["decision"] = decision_engine
        logger.info(f"Registered mode: decision")
    
    def register_mode(self, name: str, mode: Mode) -> None:
        """
        Register a new operating mode.
        
        Args:
            name: Name to register mode under
            mode: Mode instance to register
        """
        self.modes[name] = mode
        logger.info(f"Registered mode: {name}")
    
    async def set_active_mode(self, mode_name: str, activate: bool = True) -> None:
        """
        Switch to a different active mode.
        
        Args:
            mode_name: Name of mode to switch to
            activate: Whether to call activate() on the mode
        """
        if mode_name not in self.modes:
            logger.error(f"Mode not registered: {mode_name}")
            return
        
        # Deactivate current mode
        if self.active_mode and self.active_mode != mode_name:
            old_mode = self.modes[self.active_mode]
            if hasattr(old_mode, 'deactivate'):
                try:
                    await old_mode.deactivate()
                except Exception as e:
                    logger.warning(f"Error deactivating mode {self.active_mode}: {e}")
        
        # Activate new mode
        self.active_mode = mode_name
        if activate:
            new_mode = self.modes[mode_name]
            if hasattr(new_mode, 'activate'):
                try:
                    await new_mode.activate()
                except Exception as e:
                    logger.warning(f"Error activating mode {mode_name}: {e}")
        
        logger.info(f"Active mode switched to: {mode_name}")
    
    async def route(self, request: AssistantRequest) -> AssistantResponse:
        """
        Route a request to appropriate mode and return response.
        
        Args:
            request: User request with query and context
            
        Returns:
            Response from the selected mode
        """
        start_time = time.time()
        
        # Determine which mode to use
        target_mode = self._select_mode(request.query, request.mode)
        
        if target_mode not in self.modes:
            logger.error(f"Selected mode not available: {target_mode}")
            target_mode = self.default_mode
        
        logger.debug(f"Routing to mode: {target_mode}")
        
        # Switch to target mode if needed
        if self.active_mode != target_mode:
            await self.set_active_mode(target_mode)
        
        # Execute request in selected mode
        try:
            mode = self.modes[target_mode]
            
            # Mode-specific processing
            if target_mode == "decision":
                return await self._process_decision_mode(request, start_time, mode)
            else:  # conversation
                return await self._process_conversation_mode(request, start_time, mode)
        
        except Exception as e:
            logger.exception(f"Error during routing: {e}")
            processing_time = (time.time() - start_time) * 1000
            return AssistantResponse(
                mode=target_mode,
                answer=f"An error occurred: {str(e)}",
                confidence=0.0,
                processing_time_ms=processing_time,
                metadata={"error": str(e)},
            )
    
    async def _process_conversation_mode(self, request: AssistantRequest, start_time: float, mode: Mode) -> AssistantResponse:
        """Process request in conversation mode."""
        # Convert to mode-specific request if needed
        from backend.modes.conversation import ConversationRequest
        mode_request = ConversationRequest(
            query=request.query,
            context=request.context,
            user_id=request.user_id,
            session_id=request.session_id,
            metadata=request.metadata,
        )
        
        mode_response = await mode.process(mode_request)
        
        return AssistantResponse(
            mode="conversation",
            answer=mode_response.answer,
            confidence=mode_response.confidence,
            reasoning=mode_response.reasoning,
            processing_time_ms=mode_response.processing_time_ms,
            metadata=mode_response.metadata,
        )
    
    async def _process_decision_mode(self, request: AssistantRequest, start_time: float, mode: Mode) -> AssistantResponse:
        """Process request in decision mode (MAGI)."""
        # Import here to avoid circular dependencies
        from backend.modes.decision.schemas import RawUserInput
        from backend.modes.decision.orchestrator import run_pipeline
        
        try:
            # Convert AssistantRequest to MAGI RawUserInput
            magi_input = RawUserInput(
                problem=request.query,
                goal=request.goal or "",
                constraints=request.constraints or [],
            )
            
            # Run MAGI decision pipeline
            decision_result = run_pipeline(magi_input)
            
            processing_time = (time.time() - start_time) * 1000
            
            return AssistantResponse(
                mode="decision",
                answer=decision_result.chair_summary.summary,
                confidence=None,  # MAGI provides voting results instead
                reasoning=decision_result.chair_summary.dominant_reasoning,
                decision_data={
                    "final_decision": decision_result.chair_summary.final_decision,
                    "recommended_action": decision_result.chair_summary.recommended_action,
                    "full_result": decision_result.model_dump(),  # Full deliberation data
                },
                processing_time_ms=processing_time,
                metadata={
                    "decision_mode": "magi_council",
                    "agents": ["SARASWATI", "LAKSHMI", "DURGA", "VIVEKA"],
                },
            )
        except Exception as e:
            logger.exception("Error in decision mode processing")
            processing_time = (time.time() - start_time) * 1000
            return AssistantResponse(
                mode="decision",
                answer=f"Decision engine error: {str(e)}",
                confidence=0.0,
                processing_time_ms=processing_time,
                metadata={"error": str(e)},
            )
    
    def _select_mode(self, query: str, selector: Optional[str] = "auto") -> str:
        """
        Determine which mode to use for query.
        
        Args:
            query: User query
            selector: Selection strategy ("auto", "conversation", or "decision")
            
        Returns:
            Selected mode name
        """
        # Forced mode selection
        if selector == "conversation" or selector == ModeSelector.CONVERSATION.value:
            if "conversation" in self.modes:
                return "conversation"
        elif selector == "decision" or selector == ModeSelector.DECISION.value:
            if "decision" in self.modes:
                return "decision"
        
        # Auto detection
        if selector == "auto" or selector == ModeSelector.AUTO.value:
            # Check if decision mode is available
            if "decision" not in self.modes:
                return "conversation"
            
            # Simple heuristic: check for decision/deliberation keywords
            decision_keywords = [
                "decide", "should", "which", "best", "recommend",
                "pros and cons", "compare", "evaluate", "debate",
                "consider", "analyze", "pros", "cons", "choice",
                "opinion", "advice", "think about"
            ]
            
            query_lower = query.lower()
            if any(keyword in query_lower for keyword in decision_keywords):
                return "decision"
            
            return "conversation"
        
        # Default fallback
        return self.default_mode
    
    def get_available_modes(self) -> Dict[str, dict]:
        """
        Get information about all available modes.
        
        Returns:
            Dict mapping mode name to info
        """
        available = {}
        for name, mode in self.modes.items():
            if hasattr(mode, 'get_capabilities'):
                available[name] = mode.get_capabilities()
            else:
                available[name] = {"name": name, "active": name == self.active_mode}
        return available
    
    def get_active_mode(self) -> Optional[str]:
        """Get name of currently active mode."""
        return self.active_mode
