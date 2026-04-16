"""
评估相关数据模式
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class InterviewTimestamp(BaseModel):
    """面试时间戳"""
    start: str = Field(..., description="开始时间，格式如 '0:00:00'")
    end: str = Field(..., description="结束时间，格式如 '0:05:00'")


class VoicePerformance(BaseModel):
    """语音表现"""
    speed: Optional[str] = Field(None, description="语速评价")
    tone: Optional[str] = Field(None, description="语调评价")
    volume: Optional[str] = Field(None, description="音量评价")
    pronunciation: Optional[str] = Field(None, description="发音评价")
    pause: Optional[str] = Field(None, description="停顿评价")
    summary: Optional[str] = Field(None, description="语音表现总结")
    # Score labels for each metric
    speed_score_label: Optional[str] = Field(None, description="语速评分标签 (Poor/Fair/Good)")
    tone_score_label: Optional[str] = Field(None, description="语调评分标签 (Poor/Fair/Good)")
    volume_score_label: Optional[str] = Field(None, description="音量评分标签 (Poor/Fair/Good)")
    pronunciation_score_label: Optional[str] = Field(None, description="发音评分标签 (Poor/Fair/Good)")
    pause_score_label: Optional[str] = Field(None, description="停顿评分标签 (Poor/Fair/Good)")


class VisualPerformance(BaseModel):
    """视觉表现"""
    eye_contact: Optional[str] = Field(None, description="眼神接触评价")
    facial_expression: Optional[str] = Field(None, description="面部表情评价")
    body_posture: Optional[str] = Field(None, description="身体姿态评价")
    appearance: Optional[str] = Field(None, description="外观评价")
    summary: Optional[str] = Field(None, description="视觉表现总结")
    # Score labels for each metric
    eye_contact_score_label: Optional[str] = Field(None, description="眼神接触评分标签 (Poor/Fair/Good)")
    facial_expression_score_label: Optional[str] = Field(None, description="面部表情评分标签 (Poor/Fair/Good)")
    body_posture_score_label: Optional[str] = Field(None, description="身体姿态评分标签 (Poor/Fair/Good)")
    appearance_score_label: Optional[str] = Field(None, description="外观评价标签 (Poor/Fair/Good)")


class NonverbalPerformance(BaseModel):
    """非语言表现"""
    voice_performance: Optional[VoicePerformance] = None
    visual_performance: Optional[VisualPerformance] = None


class InterviewDialogItem(BaseModel):
    """面试对话项"""
    timestamp: InterviewTimestamp
    role: str = Field(..., description="角色：'agent' 或 'user'")
    content: str = Field(..., description="对话内容")
    nonverbal: Optional[NonverbalPerformance] = Field(None, description="非语言表现分析（仅用户发言时有）")
    target_dimensions: Optional[List[str]] = Field(
        default=None,
        description="本轮重点评估的维度键列表（如 ['content', 'expression']）"
    )


class InterviewEvalRequest(BaseModel):
    """面试评估请求（直接评估对话内容）"""
    interview: List[InterviewDialogItem] = Field(..., description="面试对话列表")
    language: str = Field(default="ja", description="Language code (ja/en/zh)")


class EvaluationDimension(BaseModel):
    """评估维度"""
    score: int = Field(..., ge=0, le=100, description="分数")
    label: str = Field(..., description="等级标签")
    brief: str = Field(..., description="简要评价")
    feedback: str = Field(..., description="详细反馈")


class OverallEvaluation(BaseModel):
    """整体评价"""
    score: int = Field(..., ge=0, le=100, description="总分")
    label: str = Field(..., description="等级标签")


class InterviewEvalResponse(BaseModel):
    """面试评估响应"""
    code: int = Field(0, description="状态码")
    msg: str = Field("success", description="消息")
    data: Dict[str, Any] = Field(..., description="评估数据")

    class Config:
        json_schema_extra = {
            "example": {
                "code": 0,
                "msg": "success",
                "data": {
                    "overall": {
                        "score": 65,
                        "label": "Fair"
                    },
                    "clarity": {
                        "score": 50,
                        "label": "Poor",
                        "brief": "表达不够清晰，内容单薄，需加强信息的完整性和逻辑性",
                        "feedback": "建议在回答中提供更多细节和具体例子，确保信息传递清晰且有条理"
                    },
                    "evidence": {
                        "score": 70,
                        "label": "Fair",
                        "brief": "提供了一定的支持性信息，但缺乏具体细节和数据",
                        "feedback": "建议引用更多具体数据或实例来支持你的观点，以增强说服力"
                    },
                    "engagement": {
                        "score": 80,
                        "label": "Good",
                        "brief": "整体表现较为积极，能够引起听众的兴趣",
                        "feedback": "继续保持积极的态度，同时尝试通过更多互动来提升参与感"
                    },
                    "impact": {
                        "score": 60,
                        "label": "Fair",
                        "brief": "影响力一般，未能充分展示个人优势和独特性",
                        "feedback": "建议突出个人亮点，展示独特的技能和经验，以提升整体影响力"
                    },
                    "verbal_performance": {
                        "score": 55,
                        "label": "Poor",
                        "brief": "语音表现一般，内容单薄且语调平淡，需加强情感表达和内容丰富度",
                        "feedback": "建议提升语调的变化和情感表达，同时丰富回答内容，避免过于简短"
                    },
                    "visual_performance": {
                        "score": 60,
                        "label": "Fair",
                        "brief": "视觉表现有待提升，表情不够生动，眼神接触稳定性不足，需增强亲和力和放松度",
                        "feedback": "建议增加面部表情的变化，保持稳定的眼神接触，并尝试放松身体以展现更自然的形象"
                    }
                }
            }
        }


class EvaluationScores(BaseModel):
    """评估分数"""
    clarity_score: float = Field(..., ge=0, le=100)
    evidence_score: float = Field(..., ge=0, le=100)
    expression_score: float = Field(..., ge=0, le=100)
    engagement_score: float = Field(..., ge=0, le=100)
    etiquette_score: float = Field(..., ge=0, le=100)
    impression_score: float = Field(..., ge=0, le=100)
    overall_score: float = Field(..., ge=0, le=100)


class AudioFeatures(BaseModel):
    """音频特征"""
    speech_rate: float
    pause_frequency: float
    volume_variation: float
    pitch_variation: float
    clarity_score: float
    confidence_indicator: float


class RadarChartData(BaseModel):
    """雷达图数据"""
    dimensions: List[str]
    scores: List[float]
    max_value: float = 100.0


class EvaluationResponse(BaseModel):
    """评估响应"""
    id: UUID
    interview_id: UUID
    
    # 分数
    clarity_score: float
    evidence_score: float
    expression_score: float
    engagement_score: float
    etiquette_score: float
    impression_score: float
    overall_score: float
    
    # 反馈和建议
    detailed_feedback: Optional[str]
    improvement_suggestions: Optional[Dict[str, Any]]
    strengths: Optional[Dict[str, Any]]
    weaknesses: Optional[Dict[str, Any]]
    
    # 音频特征和雷达图
    audio_features: Optional[Dict[str, Any]]
    radar_chart_data: Optional[Dict[str, Any]]
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class EvaluationRequest(BaseModel):
    """评估请求"""
    interview_id: UUID

