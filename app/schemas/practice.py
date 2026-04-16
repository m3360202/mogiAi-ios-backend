"""
练习模式Schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


# ==================== Practice Topic Schemas ====================

class PracticeTopicBase(BaseModel):
    title: str
    category: str  # beginner | advanced
    icon: Optional[str] = None
    dimension: Optional[str] = None
    min_duration: int = 120
    max_duration: int = 300
    recommended_duration: Optional[str] = None
    description: Optional[str] = None
    hints: Optional[Dict[str, Any]] = None
    evaluation_criteria: Optional[Dict[str, Any]] = None


class PracticeTopicCreate(PracticeTopicBase):
    pass


class PracticeTopicResponse(PracticeTopicBase):
    id: UUID
    sort_order: int
    is_active: bool
    created_at: datetime
    
    # 用户进度信息（如果有）
    proficiency: Optional[str] = None  # none | bronze | silver | gold
    
    class Config:
        from_attributes = True


class PracticeTopicListResponse(BaseModel):
    beginner: List[PracticeTopicResponse]
    advanced: List[PracticeTopicResponse]


# ==================== User Topic Progress Schemas ====================

class UserTopicProgressBase(BaseModel):
    topic_id: UUID
    proficiency_level: str = "none"


class UserTopicProgressUpdate(BaseModel):
    proficiency_level: str


class UserTopicProgressResponse(UserTopicProgressBase):
    id: UUID
    user_id: UUID
    practice_count: int
    best_score: Optional[float] = None
    average_score: Optional[float] = None
    last_practiced_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Practice Statistics Schemas ====================

class PracticeStatisticsResponse(BaseModel):
    id: UUID
    user_id: UUID
    total_practices: int
    practices_today: int
    practices_this_week: int
    practices_this_month: int
    current_streak: int
    max_streak: int
    last_practice_date: Optional[datetime] = None
    average_overall_score: Optional[float] = None
    average_scores: Optional[Dict[str, float]] = None
    score_history: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


# ==================== Detailed Evaluation Schemas ====================

class DimensionAnalysis(BaseModel):
    performance: str
    issues: str
    last_comparison: Optional[Dict[str, str]] = Field(
        default=None,
        description="包含 improvements 和 weaknesses"
    )
    suggestions: str


class DetailedScores(BaseModel):
    content: float
    expression: float
    logic: float
    attitude: float
    professionalism: float
    fluency: float
    overall: float


class DetailedEvaluationBase(BaseModel):
    content_score: float
    expression_score: float
    logic_score: float
    attitude_score: float
    professionalism_score: float
    fluency_score: float
    overall_score: float
    content_analysis: Optional[DimensionAnalysis] = None
    expression_analysis: Optional[DimensionAnalysis] = None
    logic_analysis: Optional[DimensionAnalysis] = None
    attitude_analysis: Optional[DimensionAnalysis] = None
    professionalism_analysis: Optional[DimensionAnalysis] = None
    fluency_analysis: Optional[DimensionAnalysis] = None
    comparison_data: Optional[Dict[str, Any]] = None


class DetailedEvaluationCreate(DetailedEvaluationBase):
    interview_id: UUID


class DetailedEvaluationResponse(DetailedEvaluationBase):
    id: UUID
    interview_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Video Recording Schemas ====================

class VideoRecordingBase(BaseModel):
    video_url: str
    thumbnail_url: Optional[str] = None
    duration: int
    file_size: Optional[int] = None
    format: Optional[str] = None
    resolution: Optional[str] = None


class VideoRecordingCreate(VideoRecordingBase):
    interview_id: UUID
    user_id: UUID


class VideoRecordingResponse(VideoRecordingBase):
    id: UUID
    interview_id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ==================== Practice Result Schemas ====================

class PracticeResultResponse(BaseModel):
    """练习结果综合响应"""
    interview_id: UUID
    topic: str
    duration: int
    overall_score: float
    
    # 六维评分
    scores: DetailedScores
    
    # 详细分析
    detailed_analysis: Dict[str, DimensionAnalysis]
    
    # 对比数据
    average_scores: Dict[str, float]
    passing_scores: Dict[str, float]
    
    # 练习统计
    practice_stats: Dict[str, int]
    
    # 视频信息（如果有）
    video_url: Optional[str] = None
    
    created_at: datetime


# ==================== Practice Request Schemas ====================

class StartPracticeRequest(BaseModel):
    topic_id: UUID
    mode: str = "practice"  # practice | real


class SubmitPracticeRequest(BaseModel):
    interview_id: UUID
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    transcript: Optional[str] = None
    duration: int

