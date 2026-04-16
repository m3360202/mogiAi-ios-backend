"""
Value objects for the evaluation business domain.
"""
from typing import List, TYPE_CHECKING, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .enums import MessageRole, ScoreLabel, MetricType, SuperMetricType

if TYPE_CHECKING:
    from .entities import Metric


class VoicePerformance(BaseModel):
    """
    Value Object: Represents voice performance metrics for evaluation.
    """
    speed: Optional[str] = Field(None, description="Speed evaluation")
    tone: Optional[str] = Field(None, description="Tone evaluation")
    volume: Optional[str] = Field(None, description="Volume evaluation")
    pronunciation: Optional[str] = Field(None, description="Pronunciation evaluation")
    pause: Optional[str] = Field(None, description="Pause evaluation")
    summary: Optional[str] = Field(None, description="Voice performance summary")
    speed_score_label: Optional[str] = Field(None, description="Speed score label (Poor/Fair/Good)")
    tone_score_label: Optional[str] = Field(None, description="Tone score label (Poor/Fair/Good)")
    volume_score_label: Optional[str] = Field(None, description="Volume score label (Poor/Fair/Good)")
    pronunciation_score_label: Optional[str] = Field(None, description="Pronunciation score label (Poor/Fair/Good)")
    pause_score_label: Optional[str] = Field(None, description="Pause score label (Poor/Fair/Good)")
    
    model_config = {"frozen": True}


class VisualPerformance(BaseModel):
    """
    Value Object: Represents visual performance metrics for evaluation.
    """
    eye_contact: Optional[str] = Field(None, description="Eye contact evaluation")
    facial_expression: Optional[str] = Field(None, description="Facial expression evaluation")
    body_posture: Optional[str] = Field(None, description="Body posture evaluation")
    appearance: Optional[str] = Field(None, description="Appearance evaluation")
    summary: Optional[str] = Field(None, description="Visual performance summary")
    eye_contact_score_label: Optional[str] = Field(None, description="Eye contact score label (Poor/Fair/Good)")
    facial_expression_score_label: Optional[str] = Field(None, description="Facial expression score label (Poor/Fair/Good)")
    body_posture_score_label: Optional[str] = Field(None, description="Body posture score label (Poor/Fair/Good)")
    appearance_score_label: Optional[str] = Field(None, description="Appearance score label (Poor/Fair/Good)")
    
    model_config = {"frozen": True}


class NonverbalPerformance(BaseModel):
    """
    Value Object: Represents non-verbal performance metrics for evaluation.
    """
    voice_performance: Optional[VoicePerformance] = None
    visual_performance: Optional[VisualPerformance] = None
    
    model_config = {"frozen": True}


class DialogMessage(BaseModel):
    """
    Value Object: Represents a single message in a dialogue section.
    """
    section_id: str
    role: MessageRole
    content: str
    start_time: datetime
    end_time: datetime
    nonverbal: Optional[NonverbalPerformance] = Field(None, description="Non-verbal performance data (for candidate messages)")
    target_dimensions: Optional[List[str]] = Field(
        default=None,
        description="重点评估的维度键列表（例如 ['content', 'expression']）"
    )
    
    model_config = {"frozen": True}


class RawDialogInfo(BaseModel):
    """
    Value Object: Represents the raw dialogue information from an interview session.
    """
    dialog_id: str
    messages: List[DialogMessage]
    language: str = Field(default="ja", description="Language of the interview (ja/en/zh)")
    
    model_config = {"frozen": True}





class Score(BaseModel):
    """
    Value Object: Represents the score for a metric or sub-metric.
    """
    score_label: ScoreLabel
    numeric_score: float = Field(..., ge=0.0, le=100.0)
    
    model_config = {"frozen": True}


class MetricMetadata(BaseModel):
    """
    Value Object: Represents metadata for a metric used in evaluation.
    """
    metric_type: MetricType
    model: str = Field(default="gpt-4o", description="Model for LLM-based evaluation")
    weight: float = Field(..., ge=0.0, description="Weight of this metric in the overall evaluation")
    eval_system_prompt_path: Optional[str] = Field(None, description="Path to evaluation system prompt file")
    
    model_config = {"frozen": True}


class SuperMetricMetadata(BaseModel):
    """
    Value Object: Represents metadata for a super-metric used in evaluation.
    """
    super_metric_type: SuperMetricType
    metric_metadata_list: List[MetricMetadata]
    weight: float = Field(..., ge=0.0, description="Weight of this super-metric in the overall evaluation")
    
    model_config = {"frozen": True}


class MetricGroup(BaseModel):
    """
    Value Object: Represents a group of metrics used in evaluation.
    """
    metric_type: MetricType
    metrics: List['Metric']  # Forward reference
    
    model_config = {"frozen": True}


class SuperMetricSectionScore(BaseModel):
    """
    Value Object: Represents the score for a specific section within a super-metric.
    """
    section_id: str
    section_index: int = Field(..., ge=0, description="0-based index indicating the order of the section within the dialog")
    score: Score
    
    model_config = {"frozen": True}


class SuperMetricFeedback(BaseModel):
    """
    Value Object: Represents comprehensive feedback for a super-metric.
    """
    brief_feedback: str = Field(description="Short, appealing sentence highlighting key opportunity")
    revised_response: str = Field(description="Improved version of candidate's response")
    feedback: str = Field(description="Detailed explanation with examples and advice")
    section_index: int = Field(..., ge=0, description="0-based index indicating the order of the section within the dialog")
    
    model_config = {"frozen": True}


class SuperMetricSectionFeedback(BaseModel):
    """
    Value Object: Represents feedback for a specific section within a super-metric.
    """
    section_id: str = Field(description="DialogSection ID this feedback is for")
    section_index: int = Field(..., ge=0, description="0-based index indicating the order of the section within the dialog")
    brief_feedback: str = Field(description="Short, appealing sentence highlighting key opportunity for this section")
    revised_response: str = Field(description="Improved version of candidate's response for this section")
    feedback: str = Field(description="Detailed explanation with examples and advice for this section")
    
    model_config = {"frozen": True}


class SuperMetric(BaseModel):
    """
    Value Object: Represents a super-metric used in evaluation.
    """
    metadata: SuperMetricMetadata
    metric_groups: List[MetricGroup]
    score: Score
    section_scores: List[SuperMetricSectionScore]
    section_feedbacks: List[SuperMetricSectionFeedback] = Field(default_factory=list, description="Feedback for each section")
    feedback: SuperMetricFeedback
    
    model_config = {"frozen": True}


class SuperMetricFeedbackContributorSectionGroup(BaseModel):
    """
    Value Object: Represents a single dialog section that contributes to the feedback of a super-metric.
    """
    super_metric_type: SuperMetricType
    section_id: str = Field(description="DialogSection ID that contributes to the feedback")
    section_index: int = Field(..., ge=0, description="0-based index indicating the order of the section within the dialog")
    is_positive: bool = Field(description="True if section contributed positively, False if negatively")
    
    model_config = {"frozen": True}


class SectionEvaluationResult(BaseModel):
    """
    Value Object: Represents the result of evaluating a single dialog section.
    Used in two-phase evaluation to capture section-level results.
    """
    section_id: str = Field(description="ID of the dialog section that was evaluated")
    section_index: int = Field(..., ge=0, description="0-based index indicating the order of the section within the dialog")
    super_metrics: List[SuperMetric] = Field(description="Super-metrics for this section with scores and feedback")
    
    model_config = {"frozen": True}