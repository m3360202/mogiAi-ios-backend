"""
练习模式相关数据模型
"""
from datetime import datetime
from typing import List, Optional
from uuid import uuid4
from sqlalchemy import String, DateTime, Integer, Float, Boolean, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum

from app.core.database import Base


class TopicCategory(str, enum.Enum):
    """题目类别"""
    BEGINNER = "beginner"  # 初级篇
    ADVANCED = "advanced"  # 应用篇


class ProficiencyLevel(str, enum.Enum):
    """熟练度等级"""
    NONE = "none"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class PracticeTopic(Base):
    """练习题目模型"""
    __tablename__ = "practice_topics"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 题目信息
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[TopicCategory] = mapped_column(SQLEnum(TopicCategory), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 维度信息（初级篇专属）
    dimension: Mapped[str] = mapped_column(String(50), nullable=True)  # content, expression, logic, etc.
    
    # 时间配置
    min_duration: Mapped[int] = mapped_column(Integer, default=120)  # 最小时长（秒）
    max_duration: Mapped[int] = mapped_column(Integer, default=300)  # 最大时长（秒）
    recommended_duration: Mapped[str] = mapped_column(String(20), nullable=True)  # "2-3分"
    
    # 题目描述和提示
    description: Mapped[str] = mapped_column(Text, nullable=True)
    hints: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 提示信息
    
    # 评分标准
    evaluation_criteria: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 排序和状态
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user_progress: Mapped[List["UserTopicProgress"]] = relationship("UserTopicProgress", back_populates="topic")
    
    def __repr__(self):
        return f"<PracticeTopic {self.title} - {self.category}>"


class UserTopicProgress(Base):
    """用户题目进度"""
    __tablename__ = "user_topic_progress"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    topic_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("practice_topics.id"), nullable=False)
    
    # 熟练度等级
    proficiency_level: Mapped[ProficiencyLevel] = mapped_column(
        SQLEnum(ProficiencyLevel), 
        default=ProficiencyLevel.NONE
    )
    
    # 练习统计
    practice_count: Mapped[int] = mapped_column(Integer, default=0)
    best_score: Mapped[float] = mapped_column(Float, nullable=True)
    average_score: Mapped[float] = mapped_column(Float, nullable=True)
    
    # 最后练习信息
    last_practiced_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_interview_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="topic_progress")
    topic: Mapped["PracticeTopic"] = relationship("PracticeTopic", back_populates="user_progress")
    
    def __repr__(self):
        return f"<UserTopicProgress {self.user_id} - {self.topic_id} - {self.proficiency_level}>"


class PracticeStatistics(Base):
    """练习统计"""
    __tablename__ = "practice_statistics"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    
    # 练习次数统计
    total_practices: Mapped[int] = mapped_column(Integer, default=0)
    practices_today: Mapped[int] = mapped_column(Integer, default=0)
    practices_this_week: Mapped[int] = mapped_column(Integer, default=0)
    practices_this_month: Mapped[int] = mapped_column(Integer, default=0)
    
    # 连续练习天数
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_practice_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # 平均分数
    average_overall_score: Mapped[float] = mapped_column(Float, nullable=True)
    
    # 各维度平均分
    average_scores: Mapped[dict] = mapped_column(JSONB, nullable=True)  # {content: 85, expression: 90, ...}
    
    # 历史数据（用于生成图表）
    score_history: Mapped[dict] = mapped_column(JSONB, nullable=True)  # [{date: "2024-01-01", score: 85}, ...]
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="practice_statistics")
    
    def __repr__(self):
        return f"<PracticeStatistics {self.user_id} - Total: {self.total_practices}>"


class DetailedEvaluation(Base):
    """详细评价模型 - 六维详细分析"""
    __tablename__ = "detailed_evaluations"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True)
    
    # 六维评分（0-100分）
    content_score: Mapped[float] = mapped_column(Float, nullable=False)  # 内容
    expression_score: Mapped[float] = mapped_column(Float, nullable=False)  # 表現力
    logic_score: Mapped[float] = mapped_column(Float, nullable=False)  # 論理性
    attitude_score: Mapped[float] = mapped_column(Float, nullable=False)  # 態度
    professionalism_score: Mapped[float] = mapped_column(Float, nullable=False)  # 専門性
    fluency_score: Mapped[float] = mapped_column(Float, nullable=False)  # 流暢度
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)  # 综合得分
    
    # 详细分析（每个维度）
    content_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    expression_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    logic_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    attitude_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    professionalism_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    fluency_analysis: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 每个维度的分析包含：
    # {
    #   "performance": "本次表现描述",
    #   "issues": "发现的问题",
    #   "last_comparison": {
    #     "improvements": "改进的地方",
    #     "weaknesses": "仍需改进"
    #   },
    #   "suggestions": "改善建议"
    # }
    
    # 与平均值和合格线的对比
    comparison_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # {
    #   "average_scores": {content: 75, expression: 78, ...},
    #   "passing_scores": {content: 70, expression: 70, ...}
    # }
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 关系
    interview: Mapped["Interview"] = relationship("Interview", back_populates="detailed_evaluation")
    
    def __repr__(self):
        return f"<DetailedEvaluation {self.interview_id} - Score: {self.overall_score}>"


class VideoRecording(Base):
    """录像记录"""
    __tablename__ = "video_recordings"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # 视频信息
    video_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(String(500), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)  # 秒
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)  # 字节
    
    # 视频元数据
    format: Mapped[str] = mapped_column(String(20), nullable=True)  # mp4, webm, etc.
    resolution: Mapped[str] = mapped_column(String(20), nullable=True)  # 1920x1080
    
    # 处理状态
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing, ready, failed
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 关系
    interview: Mapped["Interview"] = relationship("Interview", back_populates="video_recording")
    user: Mapped["User"] = relationship("User", back_populates="video_recordings")
    
    def __repr__(self):
        return f"<VideoRecording {self.interview_id}>"

