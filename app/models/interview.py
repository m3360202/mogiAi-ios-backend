"""
面试记录数据模型
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import String, DateTime, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class Interview(Base):
    """面试记录模型"""
    __tablename__ = "interviews"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # 面试配置
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # basic, advanced, corporate
    status: Mapped[str] = mapped_column(String(20), default="created")  # created, recording, completed, evaluated
    
    # 面试类型（practice=练习模式, corporate=职场测试）
    interview_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    practice_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # basic, advanced
    
    # 面试主题和配置
    topic: Mapped[str] = mapped_column(String(100), nullable=True)
    scenario: Mapped[str] = mapped_column(String(100), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=300)  # 秒
    
    # 企业信息（Corporate模式）
    company_name: Mapped[str] = mapped_column(String(100), nullable=True)
    position: Mapped[str] = mapped_column(String(100), nullable=True)
    interview_stage: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 音频和文本数据
    audio_url: Mapped[str] = mapped_column(String(500), nullable=True)
    transcript: Mapped[str] = mapped_column(Text, nullable=True)
    
    # 对话历史（Advanced和Corporate模式）
    conversation_history: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 流式面试数据（Practice模式）
    session_id: Mapped[str] = mapped_column(String(50), nullable=True, unique=True, index=True)  # 面试会话ID
    timeline: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 完整timeline（包含问答和非语言数据）
    video_segments: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 视频片段URLs列表
    fast_evaluations: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 快速评估结果（每轮）
    section_evaluations: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 新增：独立评测结果（每问）
    aggregated_evaluation: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 聚合评估结果
    overall_eval: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 完整评估结果（InterviewEvalResponse.data）
    
    # 评分字段（从overall_eval中提取，便于查询和展示）
    dimension_scores: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # 六维评分 {clarity: 80, evidence: 75, ...}
    overall_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 总评分 (0-100)
    overall_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 总评语（brief）
    detailed_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 详细描述
    
    # 时间戳
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="interviews")
    evaluation: Mapped[Optional["Evaluation"]] = relationship("Evaluation", back_populates="interview", uselist=False)
    detailed_evaluation: Mapped[Optional["DetailedEvaluation"]] = relationship("DetailedEvaluation", back_populates="interview", uselist=False)
    video_recording: Mapped[Optional["VideoRecording"]] = relationship("VideoRecording", back_populates="interview", uselist=False)
    
    def __repr__(self):
        return f"<Interview {self.id} - {self.mode}>"
