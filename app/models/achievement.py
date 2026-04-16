"""
成就系统数据模型
"""
from datetime import datetime
from typing import List
from uuid import uuid4
from sqlalchemy import String, DateTime, Integer, Boolean, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import enum

from app.core.database import Base


class AchievementCategory(str, enum.Enum):
    """成就类别"""
    PRACTICE = "practice"  # 练习相关
    SCORE = "score"  # 分数相关
    STREAK = "streak"  # 连续练习
    MASTERY = "mastery"  # 精通相关
    SPECIAL = "special"  # 特殊成就


class AchievementRarity(str, enum.Enum):
    """成就稀有度"""
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class Achievement(Base):
    """成就模型"""
    __tablename__ = "achievements"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # 成就信息
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=True)
    category: Mapped[AchievementCategory] = mapped_column(SQLEnum(AchievementCategory), nullable=False)
    rarity: Mapped[AchievementRarity] = mapped_column(SQLEnum(AchievementRarity), default=AchievementRarity.COMMON)
    
    # 解锁条件
    unlock_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # {
    #   "type": "practice_count" | "score_threshold" | "streak_days" | "topic_mastery",
    #   "value": 10,
    #   "dimension": "content" (可选)
    # }
    
    # 奖励点数
    reward_points: Mapped[int] = mapped_column(Integer, default=10)
    
    # 排序和状态
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # 隐藏成就，解锁前不显示
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 关系
    user_achievements: Mapped[List["UserAchievement"]] = relationship("UserAchievement", back_populates="achievement")
    
    def __repr__(self):
        return f"<Achievement {self.title} - {self.category}>"


class UserAchievement(Base):
    """用户成就"""
    __tablename__ = "user_achievements"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    achievement_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("achievements.id"), nullable=False)
    
    # 解锁信息
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    progress: Mapped[int] = mapped_column(Integer, default=100)  # 解锁进度百分比
    
    # 相关面试ID（如果适用）
    interview_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="achievements")
    achievement: Mapped["Achievement"] = relationship("Achievement", back_populates="user_achievements")
    
    def __repr__(self):
        return f"<UserAchievement {self.user_id} - {self.achievement_id}>"


class UserPoints(Base):
    """用户积分"""
    __tablename__ = "user_points"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    
    # 积分信息
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    current_level: Mapped[int] = mapped_column(Integer, default=1)
    
    # 排名信息
    rank: Mapped[int] = mapped_column(Integer, nullable=True)
    
    # 积分历史
    points_history: Mapped[dict] = mapped_column(JSONB, nullable=True)
    # [{date: "2024-01-01", points: 10, reason: "achievement_unlocked"}, ...]
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="points")
    
    def __repr__(self):
        return f"<UserPoints {self.user_id} - Points: {self.total_points}>"

