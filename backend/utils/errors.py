"""
Custom exception definitions for the application.

Provides structured error handling across all subsystems.
"""

from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""
    # Validation errors
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    
    # Operation errors
    OPERATION_FAILED = "OPERATION_FAILED"
    TIMEOUT = "TIMEOUT"
    NOT_FOUND = "NOT_FOUND"
    
    # Service errors
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    
    # Voice errors
    VOICE_INPUT_FAILED = "VOICE_INPUT_FAILED"
    VOICE_OUTPUT_FAILED = "VOICE_OUTPUT_FAILED"
    
    # Decision/MAGI errors
    DECISION_ENGINE_ERROR = "DECISION_ENGINE_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    
    # Device errors
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    DEVICE_UNREACHABLE = "DEVICE_UNREACHABLE"
    
    # Action errors
    ACTION_NOT_ALLOWED = "ACTION_NOT_ALLOWED"
    ACTION_FAILED = "ACTION_FAILED"
    
    # Generic
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppException(Exception):
    """
    Base exception for the application.
    
    Provides structured error information for API responses.
    """
    
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: ErrorCode = ErrorCode.OPERATION_FAILED,
        details: Optional[dict] = None,
    ):
        """
        Initialize application exception.
        
        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Machine-readable error code
            details: Additional error details
        """
        self.message = message
        self.status_code = status_code
        self.error_code = error_code.value if isinstance(error_code, ErrorCode) else error_code
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """Convert to API response dict."""
        return {
            "error": self.message,
            "code": self.error_code,
            "details": self.details,
        }


class ValidationError(AppException):
    """Raised when input validation fails."""
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message,
            status_code=400,
            error_code=ErrorCode.INVALID_INPUT,
            details=details,
        )


class NotFoundError(AppException):
    """Raised when a resource is not found."""
    def __init__(self, resource: str):
        super().__init__(
            f"{resource} not found",
            status_code=404,
            error_code=ErrorCode.NOT_FOUND,
        )


class TimeoutError(AppException):
    """Raised when an operation times out."""
    def __init__(self, operation: str, timeout_sec: float):
        super().__init__(
            f"{operation} timed out after {timeout_sec}s",
            status_code=408,
            error_code=ErrorCode.TIMEOUT,
        )


class VoiceError(AppException):
    """Base exception for voice pipeline errors."""
    pass


class STTError(VoiceError):
    """Speech-to-text processing failed."""
    def __init__(self, message: str):
        super().__init__(
            f"Speech-to-text failed: {message}",
            status_code=400,
            error_code=ErrorCode.VOICE_INPUT_FAILED,
        )


class TTSError(VoiceError):
    """Text-to-speech processing failed."""
    def __init__(self, message: str):
        super().__init__(
            f"Text-to-speech failed: {message}",
            status_code=400,
            error_code=ErrorCode.VOICE_OUTPUT_FAILED,
        )


class ActionError(AppException):
    """Base exception for action execution errors."""
    pass


class ActionNotAllowedError(ActionError):
    """Requested action is not in the allowlist."""
    def __init__(self, action: str):
        super().__init__(
            f"Action not allowed: {action}",
            status_code=403,
            error_code=ErrorCode.ACTION_NOT_ALLOWED,
        )


class ActionExecutionError(ActionError):
    """Action execution failed."""
    def __init__(self, action: str, message: str):
        super().__init__(
            f"Action '{action}' failed: {message}",
            status_code=400,
            error_code=ErrorCode.ACTION_FAILED,
        )


class DecisionEngineError(AppException):
    """MAGI decision engine error."""
    def __init__(self, message: str):
        super().__init__(
            f"Decision engine error: {message}",
            status_code=500,
            error_code=ErrorCode.DECISION_ENGINE_ERROR,
        )


class DeviceError(AppException):
    """Base exception for device-related errors."""
    pass


class DeviceNotFoundError(DeviceError):
    """Device not found in registry."""
    def __init__(self, device_id: str):
        super().__init__(
            f"Device not found: {device_id}",
            status_code=404,
            error_code=ErrorCode.DEVICE_NOT_FOUND,
        )


class DeviceUnreachableError(DeviceError):
    """Device is not reachable."""
    def __init__(self, device_id: str):
        super().__init__(
            f"Device unreachable: {device_id}",
            status_code=503,
            error_code=ErrorCode.DEVICE_UNREACHABLE,
        )
