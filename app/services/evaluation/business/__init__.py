"""
Business module for evaluation feature.
Contains all entities, value objects, repositories (interfaces), and services (interfaces).
"""

# Enums
from .enums import (
    MessageRole,
    ScoreLabel,
    MetricType,
    SuperMetricType,
    StrategyId,
)

# Value Objects
from .value_objects import (
    DialogMessage,
    RawDialogInfo,
    Score,
    MetricMetadata,
    SuperMetricMetadata,
    MetricGroup,
    SuperMetricSectionScore,
    SuperMetric,
    SuperMetricFeedback,
    SuperMetricSectionFeedback,
    SuperMetricFeedbackContributorSectionGroup,
)

# Entities
from .entities import (
    DialogSection,
    Metric,
    EvaluationStrategy,
    EvaluationRecord,
)

# Repository Interfaces
from .repositories import (
    EvaluationRecordRepo,
    DialogSectionRepo,
    MetricRepo,
    EvaluationStrategyRepo,
)

# Service Interfaces
from .services import (
    MetricCalculationService,
    MetricCalcServiceBuilder,
    SuperMetricCalculationService,
    SuperMetricCalcServiceBuilder,
    EvaluationCalculationService,
    EvaluationCalcServiceBuilder,
    SuperMetricFeedbackService,
    SimpleSectionFeedbackService,
    ScoreTransformationService,
    Logger,
    IdGenerator,
)

__all__ = [
    # Enums
    "MessageRole",
    "ScoreLabel",
    "MetricType",
    "SuperMetricType",
    # Value Objects
    "DialogMessage",
    "RawDialogInfo",
    "Score",
    "MetricMetadata",
    "SuperMetricMetadata",
    "MetricGroup",
    "SuperMetricSectionScore",
    "SuperMetric",
    "SuperMetricFeedback",
    "SuperMetricSectionFeedback",
    "SuperMetricFeedbackContributorSectionGroup",
    # Entities
    "DialogSection",
    "Metric",
    "EvaluationStrategy",
    "EvaluationRecord",
    # Repository Interfaces
    "EvaluationRecordRepo",
    "DialogSectionRepo",
    "MetricRepo",
    "EvaluationStrategyRepo",
    # Service Interfaces
    "MetricCalculationService",
    "MetricCalcServiceBuilder",
    "SuperMetricCalculationService",
    "SuperMetricCalcServiceBuilder",
    "EvaluationCalculationService",
    "EvaluationCalcServiceBuilder",
    "SuperMetricFeedbackService",
    "SimpleSectionFeedbackService",
    "ScoreTransformationService",
    "Logger",
    "IdGenerator",
]