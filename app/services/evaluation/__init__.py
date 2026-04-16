"""
Evaluation module for interview performance assessment using AI-driven analysis.

This module implements Domain-Driven Design (DDD) patterns and Clean Architecture
for the evaluation feature, providing comprehensive interview performance analysis.

Public API:
- EvaluationAPI: Main interface for evaluation operations
- EvaluationAPIImpl: Implementation with managed dependencies
"""

from . import business
from . import repositories
from . import loggers
from . import use_cases
from . import services
from . import public

# Expose the public API at the module level for easy access
from .public import EvaluationAPI, EvaluationAPIImpl

__all__ = [
    "business", 
    "repositories", 
    "loggers", 
    "use_cases", 
    "services", 
    "public",
    "EvaluationAPI",
    "EvaluationAPIImpl"
]