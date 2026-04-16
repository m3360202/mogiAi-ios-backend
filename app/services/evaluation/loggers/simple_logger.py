"""
SimpleLogger implementation that persists to local disk.

This module implements the Logger interface from the business layer,
providing logging functionality that writes to local disk files using Python's built-in logging library.

Log Format: [<datetime>] [<log level>] [<source file>:<line number>] <msg> <parameters in json format>
- datetime: 2024-07-04 20:43:30.484338  
- log level: ERROR, WARNING, INFO, DEBUG
- msg: <module>.<class>.<context>.<action>
- predefined parameters:
  - log_id: a unique id to sequence all the log happens for one workflow(from request to response)

Example: [2024-07-04 20:43:30.484338] [ERROR] [XXX/YYY/ZZZService.py:61] order.ZZZService.submit.error {"log-id": "6eb148f18b6c4e4a8195b8a9a48a048e", "first-lang": "zh", "foreign-lang": "en"}

Features:
- Uses Python's built-in logging library for robust logging
- TimedRotatingFileHandler for automatic daily log rotation
- Thread-safe logging
- Automatic log directory creation
"""

import json
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING
from enum import Enum

from ..business.services import Logger
from .context import get_current_log_id

if TYPE_CHECKING:
    pass


class SimpleLogger(Logger):
    """
    A Logger implementation that persists to local disk using Python's built-in logging library.
    
    Implementation Details:
    - Uses TimedRotatingFileHandler for automatic daily log rotation
    - Thread-safe logging provided by Python's logging library
    - Automatic creation of log directory if it doesn't exist
    - Custom formatter to match the specified log format
    - Keeps up to 30 days of log files by default
    """

    def __init__(self, log_file_path: str = "logs/app.log", backup_count: int = 30):
        """
        Initialize the SimpleLogger.
        
        Args:
            log_file_path: Path to the log file. Directory will be created if it doesn't exist.
            backup_count: Number of backup log files to keep (default: 30 days)
        """
        self._log_file_path = log_file_path
        
        # Create log directory if it doesn't exist
        log_dir = Path(log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create logger instance
        self._logger = logging.getLogger(f"SimpleLogger_{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        
        # Remove any existing handlers to avoid duplicates
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)
        
        # Create TimedRotatingFileHandler (rotates daily at midnight)
        # Use delay=True to avoid file locking issues on Windows with multiple processes
        self._file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_file_path,
            when='midnight',
            interval=1,
            backupCount=backup_count,
            encoding='utf-8',
            delay=True  # Delay file opening until first write
        )
        
        # Create custom formatter to match the specified format
        formatter = CustomLogFormatter()
        self._file_handler.setFormatter(formatter)
        
        # Add handler to logger
        self._logger.addHandler(self._file_handler)
        
        # Prevent propagation to root logger
        self._logger.propagate = False

    def _log_with_context(self, level: int, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a message with context information.
        
        Args:
            level: Logging level (from logging module constants)
            message: The log message
            error: Optional exception for error logs
            context: Optional context dictionary with additional information
        """
        # Prepare context data
        log_context = context.copy() if context else {}
        
        # Add log ID from ContextVar
        log_id = get_current_log_id()
        if log_id:
            log_context["log_id"] = log_id
        
        # Add error information if present
        if error:
            log_context["error_type"] = error.__class__.__name__
            log_context["error_message"] = str(error)
        
        # Create log record with extra context
        extra = {'log_context': log_context}
        
        # Log the message with the appropriate level
        # Use stacklevel=3 to skip: _log_with_context -> debug/info/warning/error -> actual caller
        self._logger.log(level, message, extra=extra, stacklevel=3)

    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a debug message.
        
        Args:
            message: The debug message to log
            context: Optional context dictionary with additional information
        """
        self._log_with_context(logging.DEBUG, message, None, context)

    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an info message.
        
        Args:
            message: The info message to log
            context: Optional context dictionary with additional information
        """
        self._log_with_context(logging.INFO, message, None, context)

    def warning(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a warning message.
        
        Args:
            message: The warning message to log
            error: Optional exception that caused the warning
            context: Optional context dictionary with additional information
        """
        self._log_with_context(logging.WARNING, message, error, context)

    def error(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an error message.
        
        Args:
            message: The error message to log
            error: Optional exception that caused the error
            context: Optional context dictionary with additional information
        """
        self._log_with_context(logging.ERROR, message, error, context)


class CustomLogFormatter(logging.Formatter):
    """
    Custom formatter to match the specified log format.
    
    Format: [<datetime>] [<log level>] [<source file>:<line number>] <msg> <parameters in json format>
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record according to the specified format.
        
        Args:
            record: The log record to format
            
        Returns:
            Formatted log string
        """
        # Format timestamp with microseconds
        import datetime
        dt = datetime.datetime.fromtimestamp(record.created)
        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        
        # Get log level
        level = record.levelname
        
        # Get source file and line number
        filename = record.pathname
        line_number = record.lineno
        source_info = f"{filename}:{line_number}"
        
        # Get the message
        message = record.getMessage()
        
        # Get context from extra attributes
        log_context = getattr(record, 'log_context', {})
        # Custom JSON serialization to handle Enum types
        if log_context:
            try:
                context_json = json.dumps(log_context, default=lambda o: o.value if isinstance(o, Enum) else str(o))
            except Exception:
                context_json = "{}"
        else:
            context_json = "{}"
        
        # Format the complete log entry
        return f"[{timestamp}] [{level}] [{source_info}] {message} {context_json}"
