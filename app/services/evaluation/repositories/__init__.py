"""
Repositories module for evaluation feature.
Manages the storage of all kinds of entities with in-memory implementations
for rapid prototyping and testing, and JSON file-backed implementations
for configuration-driven strategies.
"""

# In-memory implementations
from .evaluation_record_repo import InMemoryEvaluationRecordRepo
from .dialog_section_repo import InMemoryDialogSectionRepo
from .metric_repo import InMemoryMetricRepo
from .evaluation_strategy_repo import InMemoryEvaluationStrategyRepo

# JSON file-backed implementations
from .json_file_strategy_repo import JsonFileEvaluationStrategyRepo

__all__ = [
    # In-memory implementations
    "InMemoryEvaluationRecordRepo",
    "InMemoryDialogSectionRepo", 
    "InMemoryMetricRepo",
    "InMemoryEvaluationStrategyRepo",
    # JSON file-backed implementations
    "JsonFileEvaluationStrategyRepo",
]