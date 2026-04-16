"""
Use cases for the evaluation feature.

This module implements the application logic layer of the evaluation feature
according to Clean Architecture principles. It orchestrates business entities,
repositories, and services to fulfill specific evaluation use cases.

The main use case is EvaluationUseCase, which handles the complete workflow
of evaluating interview dialog data according to configured strategies.
"""
from .evaluation_use_case import EvaluationUseCase, EvaluationUseCaseImpl

__all__ = [
    "EvaluationUseCase",
    "EvaluationUseCaseImpl",
]