"""
Base mode class and mode interface.

All operating modes (conversation, decision, etc.)
inherit from this base class and implement the mode interface.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ModeType(str, Enum):
    """Available operating modes."""
    CONVERSATION = "conversation"
    DECISION = "decision"


class ModeRequest(BaseModel):
    """Base request for any mode."""
    query: str = Field(..., min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    user_id: str = Field(default="default_user")
    session_id: str = Field(default="default_session")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ModeResponse(BaseModel):
    """Base response from any mode."""
    mode: ModeType
    answer: str
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reasoning: Optional[str] = None
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class Mode(ABC):
    """
    Abstract base class for all operating modes.
    
    Modes are responsible for:
    1. Processing user input
    2. Routing to appropriate services (LLM, decision engine, etc.)
    3. Formatting and returning responses
    4. Managing mode-specific state
    """
    
    def __init__(self, name: str, mode_type: ModeType):
        """
        Initialize mode.
        
        Args:
            name: Human-readable mode name
            mode_type: Type of this mode
        """
        self.name = name
        self.mode_type = mode_type
        self.is_active = False
    
    @abstractmethod
    async def process(self, request: ModeRequest) -> ModeResponse:
        """
        Process a request in this mode.
        
        Args:
            request: User request and context
            
        Returns:
            Response from mode
        """
        pass
    
    @abstractmethod
    async def validate_input(self, request: ModeRequest) -> bool:
        """
        Validate input before processing.
        
        Args:
            request: Request to validate
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    async def activate(self) -> None:
        """Activate this mode (optional setup)."""
        self.is_active = True
    
    async def deactivate(self) -> None:
        """Deactivate this mode (optional cleanup)."""
        self.is_active = False
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Return mode capabilities.
        
        Can include: supported features, constraints, etc.
        """
        return {
            "name": self.name,
            "type": self.mode_type.value,
            "active": self.is_active,
        }
