"""
Logger implementations and middleware for the evaluation system.

This package provides logging infrastructure for the evaluation system, including:

- SimpleLogger: A Logger implementation that writes to local disk files
- LogIdMiddleware: FastAPI middleware for generating and managing log IDs
- Context management: ContextVar-based context management for request-scoped log IDs

Usage:
    from .simple_logger import SimpleLogger
    from .log_id_middleware import LogIdMiddleware
    from .context import get_current_log_id, set_current_log_id
"""

from .simple_logger import SimpleLogger
from .log_id_middleware import LogIdMiddleware
from .context import get_current_log_id, set_current_log_id

__all__ = [
    "SimpleLogger",
    "LogIdMiddleware", 
    "get_current_log_id",
    "set_current_log_id"
]