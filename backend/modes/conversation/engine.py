"""
Conversation mode engine.

Simple, fast assistant responses using direct LLM calls.
No deliberation, no debate - just natural conversation.
"""

import time
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from backend.modes.base import Mode, ModeType, ModeRequest, ModeResponse
from backend.utils import get_logger


logger = get_logger(__name__)


class ConversationRequest(ModeRequest):
    """Conversation-specific request."""
    include_memory: bool = Field(default=True)
    personality: str = Field(default="helpful", pattern="^(helpful|creative|analytical|friendly)$")


class ConversationResponse(ModeResponse):
    """Conversation-specific response."""
    follow_up_suggestions: Optional[list[str]] = None


class ConversationEngine(Mode):
    """
    Direct conversation mode.
    
    Processes queries through a single LLM call for fast, natural responses.
    Suitable for:
    - General questions
    - Casual chat
    - Quick information retrieval
    - Commands
    """
    
    def __init__(self):
        """Initialize conversation engine."""
        super().__init__("Conversation", ModeType.CONVERSATION)
        self.model_name = "conversation_model"  # TODO: Get from config
        self.system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for conversation mode."""
        return """You are a helpful, intelligent personal AI assistant. 
You provide clear, concise, and accurate responses to user queries.
You're friendly but professional.
When uncertain, you acknowledge limitations and offer alternatives."""
    
    async def validate_input(self, request: ModeRequest) -> bool:
        """
        Validate conversation request.
        
        Args:
            request: Request to validate
            
        Returns:
            True if valid
        """
        if not isinstance(request.query, str) or len(request.query.strip()) == 0:
            logger.warning("Invalid conversation request: empty query")
            return False
        
        if len(request.query) > 10000:
            logger.warning("Invalid conversation request: query too long")
            return False
        
        return True
    
    async def process(self, request: ModeRequest) -> ConversationResponse:
        """
        Process request in conversation mode.
        
        Current implementation: TODO - will invoke LLM once integrated.
        For now, returns a placeholder response.
        
        Args:
            request: User query and context
            
        Returns:
            Conversation response
        """
        start_time = time.time()
        
        # Validate input
        if not await self.validate_input(request):
            logger.error("Conversation request validation failed")
            return ConversationResponse(
                mode=ModeType.CONVERSATION,
                answer="I didn't understand that. Could you rephrase?",
                confidence=0.0,
                processing_time_ms=(time.time() - start_time) * 1000,
            )
        
        try:
            # TODO: Invoke LLM service
            # answer = await self.llm_service.complete(
            #     system_prompt=self.system_prompt,
            #     user_message=request.query,
            #     context=request.context,
            # )
            
            # Placeholder answer
            answer = f"I understand you asked: {request.query[:50]}... (LLM integration pending)"
            
            logger.debug(f"Conversation response generated in {time.time() - start_time:.2f}s")
            
            return ConversationResponse(
                mode=ModeType.CONVERSATION,
                answer=answer,
                confidence=0.85,
                processing_time_ms=(time.time() - start_time) * 1000,
                follow_up_suggestions=[
                    "Tell me more",
                    "How does that help?",
                    "What should I do?",
                ]
            )
        
        except Exception as e:
            logger.exception(f"Error in conversation processing: {e}")
            return ConversationResponse(
                mode=ModeType.CONVERSATION,
                answer=f"I encountered an error: {str(e)}",
                confidence=0.0,
                processing_time_ms=(time.time() - start_time) * 1000,
            )
    
    async def activate(self) -> None:
        """Activate conversation mode."""
        await super().activate()
        logger.info("Conversation mode activated")
    
    async def deactivate(self) -> None:
        """Deactivate conversation mode."""
        await super().deactivate()
        logger.info("Conversation mode deactivated")
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get conversation mode capabilities."""
        caps = super().get_capabilities()
        caps.update({
            "supported_features": [
                "natural_conversation",
                "quick_retrieval",
                "command_execution",
                "reasoning_explanation",
            ],
            "response_time_target_ms": 500,
            "uses_reasoning": False,
        })
        return caps
