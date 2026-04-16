"""
用户提供的面试经验数据模型
"""
from typing import Optional
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base

class InterviewExperience(Base):
    """面试经验模型"""
    __tablename__ = "interview_experiences"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # 基本信息
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # position: Mapped[str] = mapped_column(String(100), nullable=True)  # 如果数据库表中没有此列，请注释掉
    
    # 面试问题列表 [{"content": "问题1"}, {"content": "问题2"}]
    questions: Mapped[list] = mapped_column(JSONB, default=list)
    
    # 语音风格（可选），例如: 'ja-JP-Wavenet-A', 'ja-JP-Wavenet-D' 等
    tts_voice: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # 状态: pending_review (审核中), approved (已通过), rejected (已拒绝)
    status: Mapped[str] = mapped_column(String(20), default="pending_review")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user: Mapped["User"] = relationship("User", backref="interview_experiences")
    
    def __repr__(self):
        return f"<InterviewExperience {self.id} - {self.company_name}>"

