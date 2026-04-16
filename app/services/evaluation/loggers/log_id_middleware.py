"""
LogIdMiddleware - Generates and manages log IDs for request tracing.

This middleware generates a unique log ID for each request and stores it in a ContextVar.
If a log ID is already provided by the client, it will be used instead of generating a new one.
This middleware should be placed at the front of other middleware to ensure proper log ID propagation.
"""

import uuid
from typing import TYPE_CHECKING, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .context import set_current_log_id, get_current_log_id

if TYPE_CHECKING:
    pass


class LogIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate a log ID and store it in ContextVar.
    
    Implementation Details:
    - Generates a new log ID if not provided by the client
    - Uses UUID4 for unique log ID generation
    - Stores log ID in ContextVar for access by other components
    - Should be placed in the front of other middlewares
    """

    LOG_ID_HEADER = "X-Log-Id"

    def __init__(self, app, *args, **kwargs):
        """
        Initialize the LogIdMiddleware.
        
        Args:
            app: The ASGI application to wrap
        """
        super().__init__(app, *args, **kwargs)

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request and add log ID handling.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler
            
        Returns:
            The HTTP response with log ID in headers
        """
        # Check if log ID is already provided by the client
        log_id = request.headers.get(self.LOG_ID_HEADER)
        
        # Generate a new log ID if not provided
        if not log_id:
            log_id = str(uuid.uuid4())
        
        # Store log ID in ContextVar for access by other components
        set_current_log_id(log_id)
        
        # Process the request
        response = await call_next(request)
        
        # Add log ID to response headers for client reference
        response.headers[self.LOG_ID_HEADER] = log_id
        
        return response

    @staticmethod
    def get_log_id(_request: Optional[Request] = None) -> str:  # pylint: disable=unused-argument
        """
        Get the log ID from the ContextVar.
        
        Args:
            _request: The HTTP request object (kept for backward compatibility, unused)
            
        Returns:
            The log ID string, or empty string if not found
        """
        return get_current_log_id()
