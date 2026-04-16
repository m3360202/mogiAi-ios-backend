"""
Repository interfaces for the evaluation business domain.
"""
from abc import ABC, abstractmethod
from typing import Optional

from .entities import EvaluationRecord, DialogSection, Metric, EvaluationStrategy


class EvaluationRecordRepo(ABC):
    """
    Repository interface for persisting and retrieving EvaluationRecord entities.
    """
    
    @abstractmethod
    def save(self, evaluation_record: EvaluationRecord) -> None:
        """Save an evaluation record."""
        ...
    
    @abstractmethod
    def get_by_interview_record_id(self, interview_record_id: str) -> Optional[EvaluationRecord]:
        """Get evaluation record by interview record ID."""
        ...


class DialogSectionRepo(ABC):
    """
    Repository interface for persisting and retrieving DialogSection entities.
    """
    
    @abstractmethod
    def save(self, dialog_section: DialogSection) -> None:
        """Save a dialog section."""
        pass
    
    @abstractmethod
    def get_by_id(self, section_id: str) -> Optional[DialogSection]:
        """Get dialog section by ID."""
        pass


class MetricRepo(ABC):
    """
    Repository interface for persisting and retrieving Metric entities.
    """
    
    @abstractmethod
    def save(self, metric: Metric) -> None:
        """Save a metric."""
        pass
    
    @abstractmethod
    def get_by_id(self, metric_id: str) -> Optional[Metric]:
        """Get metric by ID."""
        pass


class EvaluationStrategyRepo(ABC):
    """
    Repository interface for retrieving EvaluationStrategy entities.
    """
    
    @abstractmethod
    def get_by_id(self, strategy_id: str) -> Optional[EvaluationStrategy]:
        """Get evaluation strategy by ID."""
        pass