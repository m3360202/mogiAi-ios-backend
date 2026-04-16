"""
Public API interfaces for the evaluation service.

This module exposes the public interfaces that external modules should use
to interact with the evaluation service.
"""

from .evaluation_api import EvaluationAPI, EvaluationAPIImpl, get_evaluation_api
from .two_phase_evaluation_api import TwoPhaseEvaluationAPI, TwoPhaseEvaluationAPIImpl, get_two_phase_evaluation_api

__all__ = [
    "EvaluationAPI",
    "EvaluationAPIImpl",
    "get_evaluation_api",
    "TwoPhaseEvaluationAPI",
    "TwoPhaseEvaluationAPIImpl",
    "get_two_phase_evaluation_api",
]