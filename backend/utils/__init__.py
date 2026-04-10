"""Utility modules for the application."""

from backend.utils.errors import (
    AppException,
    ValidationError,
    NotFoundError,
    TimeoutError,
    VoiceError,
    STTError,
    TTSError,
    ActionError,
    ActionNotAllowedError,
    ActionExecutionError,
    DecisionEngineError,
    DeviceError,
    DeviceNotFoundError,
    DeviceUnreachableError,
)
from backend.utils.logger import setup_logging, get_logger

__all__ = [
    "AppException",
    "ValidationError",
    "NotFoundError",
    "TimeoutError",
    "VoiceError",
    "STTError",
    "TTSError",
    "ActionError",
    "ActionNotAllowedError",
    "ActionExecutionError",
    "DecisionEngineError",
    "DeviceError",
    "DeviceNotFoundError",
    "DeviceUnreachableError",
    "setup_logging",
    "get_logger",
]
