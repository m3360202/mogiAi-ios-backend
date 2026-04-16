"""
用户数据模型
"""
from datetime import datetime
from typing import List
from uuid import uuid4
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    supabase_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=True)  # Optional for OAuth users
    full_name: Mapped[str] = mapped_column(String(100), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)  # For OAuth profile pictures
    
    # OAuth 相关字段
    oauth_provider: Mapped[str] = mapped_column(String(50), nullable=True)  # google, github, etc.
    oauth_id: Mapped[str] = mapped_column(String(255), nullable=True)  # OAuth provider's user ID
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # OAuth users are auto-verified
    
    # 用户偏好设置
    preferred_language: Mapped[str] = mapped_column(String(10), default="ja")
    user_level: Mapped[str] = mapped_column(String(20), default="beginner")  # beginner, intermediate, advanced
    
    # 用户偏好（逗号分隔）
    preferred_industries: Mapped[str] = mapped_column(String(500), nullable=True)
    preferred_positions: Mapped[str] = mapped_column(String(500), nullable=True)
    work_status: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 性格和就业倾向（JSON 数组格式存储）
    personalities: Mapped[str] = mapped_column(String(1000), nullable=True)  # JSON array
    career_tendencies: Mapped[str] = mapped_column(String(1000), nullable=True)  # JSON array
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    # 关系
    interviews: Mapped[List["Interview"]] = relationship("Interview", back_populates="user")
    corporate_templates: Mapped[List["CorporateTemplate"]] = relationship("CorporateTemplate", back_populates="user")
    topic_progress: Mapped[List["UserTopicProgress"]] = relationship("UserTopicProgress", back_populates="user")
    practice_statistics: Mapped["PracticeStatistics"] = relationship("PracticeStatistics", back_populates="user", uselist=False)
    achievements: Mapped[List["UserAchievement"]] = relationship("UserAchievement", back_populates="user")
    points: Mapped["UserPoints"] = relationship("UserPoints", back_populates="user", uselist=False)
    video_recordings: Mapped[List["VideoRecording"]] = relationship("VideoRecording", back_populates="user")
    
    def __repr__(self):
        return f"<User {self.email}>"

