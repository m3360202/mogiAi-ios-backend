"""
Entities for the evaluation business domain.
"""
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel

# Import enums as needed
from .value_objects import (
    DialogMessage, Score, MetricMetadata, SuperMetricMetadata, SuperMetric
)


class DialogSection(BaseModel):
    """
    Entity: Represents a section of dialogue in an interview.
    Always starting with interviewer messages, and ending with candidate messages.
    """
    id: str
    dialog_id: str
    section_index: int  # 0-based index indicating the order of this section within the dialog
    messages: List[DialogMessage]
    start_time: datetime
    end_time: datetime
    language: str = "ja"  # Language of the section (ja/en/zh)


class Metric(BaseModel):
    """
    Entity: Represents a metric used in evaluation.
    Can contain multiple sub-metrics as a generic dictionary.
    """
    id: str
    metadata: MetricMetadata
    dialog_section_id: str
    dialog_section_index: int
    sub_metrics: Dict[str, Any]
    score: Score
    revision: str


class EvaluationStrategy(BaseModel):
    """
    Entity: Represents metadata for an evaluation calculation strategy.
    """
    strategy_id: str
    name: str
    description: str
    super_metric_metadata_list: List[SuperMetricMetadata]


class EvaluationRecord(BaseModel):
    """
    Entity: Represents the overall evaluation record for an interview.
    """
    id: str
    strategy: EvaluationStrategy
    interview_record_id: str
    super_metrics: List[SuperMetric]
    overall_score: Score