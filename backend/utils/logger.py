"""
Logging configuration and utilities.

Provides structured logging across the application with
appropriate levels and formatting.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Log file paths
LOG_FILE = LOG_DIR / "app.log"
ERROR_LOG_FILE = LOG_DIR / "errors.log"


def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    error_file: Optional[Path] = None,
) -> None:
    """
    Configure application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to main log file (default: logs/app.log)
        error_file: Path to error log file (default: logs/errors.log)
    """
    log_file = log_file or LOG_FILE
    error_file = error_file or ERROR_LOG_FILE
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if getattr(setup_logging, "_configured", False):
        return
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # File handler (all logs)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        )
        file_handler.setFormatter(file_format)
        root_logger.addHandler(file_handler)
    except PermissionError:
        root_logger.warning("Could not attach main log file handler; continuing with console logging only.")
    
    # Error file handler (errors and above)
    try:
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        error_handler.setLevel(logging.ERROR)
        error_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s - %(exc_info)s"
        )
        error_handler.setFormatter(error_format)
        root_logger.addHandler(error_handler)
    except PermissionError:
        root_logger.warning("Could not attach error log file handler; continuing without file error logging.")

    setup_logging._configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
