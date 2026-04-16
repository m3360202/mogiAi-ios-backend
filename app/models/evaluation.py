"""
评估结果数据模型
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class Evaluation(Base):
    """评估结果模型"""
    __tablename__ = "evaluations"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("interviews.id"), nullable=False, unique=True)
    
    # 7轴评分（0-100分）
    clarity_score: Mapped[float] = mapped_column(Float, nullable=False)  # 理解清晰度
    evidence_score: Mapped[float] = mapped_column(Float, nullable=False)  # 证据具体性
    expression_score: Mapped[float] = mapped_column(Float, nullable=False)  # 表达传达力
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False)  # 互动参与度
    etiquette_score: Mapped[float] = mapped_column(Float, nullable=False)  # 礼仪态度
    impression_score: Mapped[float] = mapped_column(Float, nullable=False)  # 印象影响力
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)  # 综合得分
    
    # 详细反馈
    detailed_feedback: Mapped[str] = mapped_column(Text, nullable=True)
    
    # 改进建议（JSON数组）
    improvement_suggestions: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 优势和劣势分析
    strengths: Mapped[dict] = mapped_column(JSONB, nullable=True)
    weaknesses: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 音频特征分析
    audio_features: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 雷达图数据
    radar_chart_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 关系
    interview: Mapped["Interview"] = relationship("Interview", back_populates="evaluation")
    
    def __repr__(self):
        return f"<Evaluation {self.id} - Score: {self.overall_score}>"

