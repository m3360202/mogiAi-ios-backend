"""
Service interfaces for the evaluation business domain.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .entities import DialogSection, EvaluationStrategy
    from .value_objects import (
        RawDialogInfo, Score, MetricMetadata, SuperMetricMetadata, MetricGroup, SuperMetric, SuperMetricFeedback
    )
    from .enums import ScoreLabel
else:
    from .entities import DialogSection, EvaluationStrategy
    from .value_objects import (
        RawDialogInfo, Score, MetricMetadata, SuperMetricMetadata, MetricGroup, SuperMetric, SuperMetricFeedback
    )
    from .enums import ScoreLabel


class MetricCalculationService(ABC):
    """
    Service interface responsible for creating complete MetricGroup entities from dialog sections.
    """
    
    @abstractmethod
    async def create_metric_group(
        self, 
        dialog_sections: List[DialogSection], 
        metadata: MetricMetadata
    ) -> MetricGroup:
        """
        Create a complete MetricGroup entity for the given dialog sections.
        
        Args:
            dialog_sections: The dialog sections to analyze
            metadata: The metric metadata defining the metric type and configuration
            
        Returns:
            MetricGroup: Complete metric group with metrics for each section
        """
        raise NotImplementedError


class MetricCalcServiceBuilder(ABC):
    """
    Builder service for creating metric calculation services based on metadata specifications.
    """
    
    @abstractmethod
    def build(self, metadata: MetricMetadata) -> MetricCalculationService:
        """Build MetricCalculationService based on MetricMetadata."""
        raise NotImplementedError


class SuperMetricCalculationService(ABC):
    """
    Service interface responsible for creating complete SuperMetric entities from metric groups.
    """
    
    @abstractmethod
    def create_super_metric(
        self, 
        metric_groups: List[MetricGroup], 
        metadata: SuperMetricMetadata
    ) -> SuperMetric:
        """
        Create a complete SuperMetric entity from metric groups.
        
        Args:
            metric_groups: List of metric groups to analyze
            metadata: The super-metric metadata defining the type and configuration
            
        Returns:
            SuperMetric: Complete super-metric with score and feedback
        """
        raise NotImplementedError


class SuperMetricCalcServiceBuilder(ABC):
    """
    Builder service for creating super-metric calculation services based on metadata specifications.
    """
    
    @abstractmethod
    def build(self, metadata: SuperMetricMetadata) -> SuperMetricCalculationService:
        """Build SuperMetricCalculationService based on SuperMetricMetadata."""
        raise NotImplementedError


class EvaluationCalculationService(ABC):
    """
    Service interface responsible for calculating evaluation scores based on super-metrics.
    """
    
    @abstractmethod
    def calculate_score(self, super_metrics: List[SuperMetric]) -> Score:
        """Calculate overall evaluation score based on super-metrics."""
        raise NotImplementedError


class EvaluationCalcServiceBuilder(ABC):
    """
    Builder service for creating evaluation calculation services based on strategy specifications.
    """
    
    @abstractmethod
    def build(self, strategy: EvaluationStrategy) -> EvaluationCalculationService:
        """Build EvaluationCalculationService based on EvaluationStrategy."""
        raise NotImplementedError


class SuperMetricFeedbackService(ABC):
    """
    Service interface responsible for generating and updating feedback for all super-metrics.
    """
    
    @abstractmethod
    async def generate_and_update_feedback(self, super_metrics: List[SuperMetric], language: str = "ja") -> List[SuperMetric]:
        """
        Generate and update feedback for all super-metrics.
        
        Args:
            super_metrics: List of super-metrics to generate feedback for
            language: Language for the feedback (ja/en/zh)
            
        Returns:
            List[SuperMetric]: Updated super-metrics with generated feedback
        """
        raise NotImplementedError

class SuperMetricFeedbackServiceBuilder(ABC):
    """
    Builder service for creating super-metric feedback services based on strategy specifications.
    """
    
    @abstractmethod
    def build(self, strategy: EvaluationStrategy) -> SuperMetricFeedbackService:
        """Build SuperMetricFeedbackService based on EvaluationStrategy."""
        raise NotImplementedError

class Logger(ABC):
    """
    Service interface for logging operations.
    """

    @abstractmethod
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a debug message.
        
        Args:
            message: The debug message to log
            context: Optional context dictionary with additional information
        """
        raise NotImplementedError()

    @abstractmethod
    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an info message.
        
        Args:
            message: The info message to log
            context: Optional context dictionary with additional information
        """
        raise NotImplementedError()

    @abstractmethod
    def warning(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log a warning message.
        
        Args:
            message: The warning message to log
            error: Optional exception that caused the warning
            context: Optional context dictionary with additional information
        """
        raise NotImplementedError()

    @abstractmethod
    def error(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an error message.
        
        Args:
            message: The error message to log
            error: Optional exception that caused the error
            context: Optional context dictionary with additional information
        """
        raise NotImplementedError()


class DialogSectionBuilder(ABC):
    """
    Service interface responsible for parsing raw dialog information into structured dialog sections.
    This service only transforms data and does not handle persistence.
    """
    
    @abstractmethod
    def build_dialog_sections(self, raw_dialog_info: RawDialogInfo) -> List[DialogSection]:
        """
        Parse RawDialogInfo into DialogSections without persisting them.
        
        Args:
            raw_dialog_info: The raw dialog information to parse
            
        Returns:
            List[DialogSection]: The created dialog sections (not yet persisted)
        """
        raise NotImplementedError


class SimpleSectionFeedbackService(ABC):
    """
    Simplified service interface for generating feedback for a single super-metric in a single section.
    This is a KISS (Keep It Simple and Stupid) version focused on single section feedback generation.
    """
    
    @abstractmethod
    async def generate_feedback_for_super_metric(
        self, 
        section: 'DialogSection', 
        super_metric: 'SuperMetric',
        language: str = "ja",
        current_score: Optional[float] = None,
        previous_score: Optional[float] = None
    ) -> 'SuperMetricFeedback':
        """
        Generate feedback for a single super-metric in a single section.
        
        Args:
            section: The dialog section to generate feedback for
            super_metric: The super-metric with score to generate feedback for
            language: Language for the feedback (ja/en/zh)
            
        Returns:
            SuperMetricFeedback: Generated feedback for this super-metric in this section
        """
        raise NotImplementedError


class SimpleSectionFeedbackServiceBuilder(ABC):
    """
    Builder service for creating simple section feedback services based on strategy specifications.
    """
    
    @abstractmethod
    def build(self, strategy: 'EvaluationStrategy') -> SimpleSectionFeedbackService:
        """Build SimpleSectionFeedbackService based on EvaluationStrategy."""
        raise NotImplementedError


class IdGenerator(ABC):
    """
    Infrastructure Service: Service for generating unique identifiers.
    """
    
    @abstractmethod
    def generate(self) -> str:
        """Generate a unique identifier."""
        raise NotImplementedError()


class ScoreTransformationService(ABC):
    """
    Service interface for transforming between score labels and numeric scores.
    This abstracts the common pattern of converting ScoreLabel enums to numeric scores.
    """
    
    @abstractmethod
    def label_to_numeric_score(self, score_label: "ScoreLabel") -> float:
        """
        Convert a ScoreLabel to its corresponding numeric score.
        
        Args:
            score_label: The score label to convert
            
        Returns:
            float: The numeric score corresponding to the label
        """
        ...
    
    @abstractmethod
    def numeric_score_to_label(self, numeric_score: float) -> "ScoreLabel":
        """
        Convert a numeric score to its corresponding ScoreLabel.
        
        Args:
            numeric_score: The numeric score to convert (0.0-100.0)
            
        Returns:
            ScoreLabel: The label corresponding to the numeric score
        """
        ...
    
    @abstractmethod
    def create_score(self, score_label: "ScoreLabel", numeric_score: Optional[float] = None) -> "Score":
        """
        Create a Score object with consistent label and numeric score.
        If numeric_score is not provided, it will be derived from the label.
        
        Args:
            score_label: The score label
            numeric_score: Optional explicit numeric score, otherwise derived from label
            
        Returns:
            Score: A Score object with consistent label and numeric values
        """
        ...