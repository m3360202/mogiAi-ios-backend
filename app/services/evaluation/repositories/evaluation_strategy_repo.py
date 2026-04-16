"""
In-memory implementation of EvaluationStrategyRepo for evaluation feature.
Used for rapid prototyping and testing.
"""
from typing import Dict, Optional, List
from threading import Lock

from ..business import (
    EvaluationStrategy, 
    EvaluationStrategyRepo,
    SuperMetricMetadata,
    MetricMetadata,
    SuperMetricType,
    MetricType,
)


class InMemoryEvaluationStrategyRepo(EvaluationStrategyRepo):
    """
    In-memory implementation of EvaluationStrategyRepo.
    Thread-safe for concurrent access.
    """
    
    def __init__(self) -> None:
        self._strategies: Dict[str, EvaluationStrategy] = {}
        self._lock = Lock()
        self._populate_default_strategies()
    
    def save(self, strategy: EvaluationStrategy) -> None:
        """Save an evaluation strategy."""
        with self._lock:
            self._strategies[strategy.strategy_id] = strategy
    
    def get_by_id(self, strategy_id: str) -> Optional[EvaluationStrategy]:
        """Get evaluation strategy by ID."""
        with self._lock:
            return self._strategies.get(strategy_id)
    
    def get_all(self) -> List[EvaluationStrategy]:
        """Get all evaluation strategies."""
        with self._lock:
            return list(self._strategies.values())
    
    def clear(self) -> None:
        """Clear all strategies (useful for testing)."""
        with self._lock:
            self._strategies.clear()
    
    def _populate_default_strategies(self) -> None:
        """Populate with default evaluation strategies."""
        # Create default strategy metadata
        clarity_metadata = SuperMetricMetadata(
            super_metric_type=SuperMetricType.CLARITY,
            metric_metadata_list=[
                MetricMetadata(metric_type=MetricType.CONCISENESS),
                MetricMetadata(metric_type=MetricType.LOGICAL_STRUCTURE),
            ]
        )
        
        evidence_metadata = SuperMetricMetadata(
            super_metric_type=SuperMetricType.EVIDENCE,
            metric_metadata_list=[
                MetricMetadata(metric_type=MetricType.RELEVANCE),
                MetricMetadata(metric_type=MetricType.COMPLETENESS),
            ]
        )
        
        # Create default strategy
        default_strategy = EvaluationStrategy(
            strategy_id="strategy_1",
            name="Default Strategy",
            description="Default evaluation strategy focusing on clarity and evidence",
            super_metric_metadata_list=[clarity_metadata, evidence_metadata]
        )
        
        self._strategies[default_strategy.strategy_id] = default_strategy