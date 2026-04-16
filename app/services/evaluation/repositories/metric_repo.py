"""
In-memory implementation of MetricRepo for evaluation feature.
Used for rapid prototyping and testing.
"""
from typing import Dict, Optional, List
from threading import Lock

from ..business import Metric, MetricRepo


class InMemoryMetricRepo(MetricRepo):
    """
    In-memory implementation of MetricRepo.
    Thread-safe for concurrent access.
    """
    
    def __init__(self) -> None:
        self._metrics: Dict[str, Metric] = {}
        self._section_index: Dict[str, List[str]] = {}  # dialog_section_id -> list of metric_ids
        self._lock = Lock()
    
    def save(self, metric: Metric) -> None:
        """Save a metric."""
        with self._lock:
            self._metrics[metric.id] = metric
            
            # Update section index
            if metric.dialog_section_id not in self._section_index:
                self._section_index[metric.dialog_section_id] = []
            if metric.id not in self._section_index[metric.dialog_section_id]:
                self._section_index[metric.dialog_section_id].append(metric.id)
    
    def get_by_id(self, metric_id: str) -> Optional[Metric]:
        """Get metric by ID."""
        with self._lock:
            return self._metrics.get(metric_id)
    
    def get_by_dialog_section_id(self, dialog_section_id: str) -> List[Metric]:
        """Get all metrics for a dialog section."""
        with self._lock:
            metric_ids = self._section_index.get(dialog_section_id, [])
            return [self._metrics[metric_id] for metric_id in metric_ids if metric_id in self._metrics]
    
    def get_all(self) -> List[Metric]:
        """Get all metrics."""
        with self._lock:
            return list(self._metrics.values())
    
    def clear(self) -> None:
        """Clear all metrics (useful for testing)."""
        with self._lock:
            self._metrics.clear()
            self._section_index.clear()