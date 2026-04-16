"""
Context management for logger components.

This module provides context variables for managing request-scoped data
like log IDs across async operations without explicit parameter passing.
"""

from contextvars import ContextVar
from typing import Optional

# Context variable to store the current log ID
log_id_context: ContextVar[Optional[str]] = ContextVar('log_id', default=None)


def get_current_log_id() -> str:
    """
    Get the current log ID from context.
    
    Returns:
        The current log ID, or empty string if not set
    """
    return log_id_context.get() or ""


def set_current_log_id(log_id: str) -> None:
    """
    Set the current log ID in context.
    
    Args:
        log_id: The log ID to set in context
    """
    log_id_context.set(log_id)
