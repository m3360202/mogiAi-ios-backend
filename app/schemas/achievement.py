"""
成就系统Schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


# ==================== Achievement Schemas ====================

class AchievementBase(BaseModel):
    title: str
    description: str
    icon: Optional[str] = None
    category: str  # practice | score | streak | mastery | special
    rarity: str = "common"  # common | rare | epic | legendary
    unlock_criteria: Dict[str, Any]
    reward_points: int = 10


class AchievementCreate(AchievementBase):
    pass


class AchievementResponse(AchievementBase):
    id: UUID
    sort_order: int
    is_active: bool
    is_hidden: bool
    created_at: datetime
    
    # 用户相关信息（如果有）
    is_unlocked: Optional[bool] = None
    unlocked_at: Optional[datetime] = None
    progress: Optional[int] = None
    
    class Config:
        from_attributes = True


# ==================== User Achievement Schemas ====================

class UserAchievementBase(BaseModel):
    achievement_id: UUID


class UserAchievementCreate(UserAchievementBase):
    user_id: UUID
    interview_id: Optional[UUID] = None


class UserAchievementResponse(UserAchievementBase):
    id: UUID
    user_id: UUID
    unlocked_at: datetime
    progress: int
    interview_id: Optional[UUID] = None
    
    # 成就详细信息
    achievement: Optional[AchievementResponse] = None
    
    class Config:
        from_attributes = True


# ==================== User Points Schemas ====================

class UserPointsBase(BaseModel):
    total_points: int = 0
    current_level: int = 1


class UserPointsResponse(UserPointsBase):
    id: UUID
    user_id: UUID
    rank: Optional[int] = None
    points_history: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AddPointsRequest(BaseModel):
    user_id: UUID
    points: int
    reason: str


# ==================== Achievement Progress Schemas ====================

class AchievementProgressResponse(BaseModel):
    """成就进度响应"""
    category: str
    achievements: List[AchievementResponse]


class UserAchievementSummary(BaseModel):
    """用户成就总览"""
    total_achievements: int
    unlocked_achievements: int
    total_points: int
    current_level: int
    rank: Optional[int] = None
    
    # 按类别分组的成就
    by_category: Dict[str, AchievementProgressResponse]
    
    # 最近解锁的成就
    recent_unlocked: List[UserAchievementResponse]

