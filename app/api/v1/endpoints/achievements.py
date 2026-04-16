"""
成就系统API端点
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.achievement import (
    Achievement,
    UserAchievement,
    UserPoints,
    AchievementCategory,
    AchievementRarity
)
from app.schemas.achievement import (
    AchievementResponse,
    UserAchievementResponse,
    UserAchievementCreate,
    UserPointsResponse,
    AddPointsRequest,
    UserAchievementSummary,
    AchievementProgressResponse
)

router = APIRouter()


# ==================== Achievements ====================

@router.get("/", response_model=List[AchievementResponse])
async def get_all_achievements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取所有成就（包含用户解锁状态）"""
    
    # 获取所有active成就
    result = await db.execute(
        select(Achievement)
        .where(Achievement.is_active == True)
        .order_by(Achievement.sort_order)
    )
    achievements = result.scalars().all()
    
    # 获取用户已解锁的成就
    user_achievements_result = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == current_user.id)
    )
    user_achievements = {
        ua.achievement_id: ua 
        for ua in user_achievements_result.scalars().all()
    }
    
    # 组合数据
    response = []
    for achievement in achievements:
        # 如果是隐藏成就且未解锁，跳过
        if achievement.is_hidden and achievement.id not in user_achievements:
            continue
        
        user_achievement = user_achievements.get(achievement.id)
        
        response.append(AchievementResponse(
            **achievement.__dict__,
            is_unlocked=user_achievement is not None,
            unlocked_at=user_achievement.unlocked_at if user_achievement else None,
            progress=user_achievement.progress if user_achievement else 0
        ))
    
    return response


@router.get("/summary", response_model=UserAchievementSummary)
async def get_achievement_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户成就总览"""
    
    # 获取所有成就
    all_achievements_result = await db.execute(
        select(Achievement).where(Achievement.is_active == True)
    )
    all_achievements = all_achievements_result.scalars().all()
    
    # 获取用户已解锁成就
    user_achievements_result = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == current_user.id)
        .order_by(UserAchievement.unlocked_at.desc())
    )
    user_achievements = user_achievements_result.scalars().all()
    unlocked_ids = {ua.achievement_id for ua in user_achievements}
    
    # 获取用户积分
    points_result = await db.execute(
        select(UserPoints).where(UserPoints.user_id == current_user.id)
    )
    points = points_result.scalar_one_or_none()
    
    # 按类别组织成就
    by_category = {}
    for achievement in all_achievements:
        # 跳过隐藏且未解锁的成就
        if achievement.is_hidden and achievement.id not in unlocked_ids:
            continue
        
        category = achievement.category.value
        if category not in by_category:
            by_category[category] = []
        
        user_achievement = next(
            (ua for ua in user_achievements if ua.achievement_id == achievement.id),
            None
        )
        
        by_category[category].append(AchievementResponse(
            **achievement.__dict__,
            is_unlocked=achievement.id in unlocked_ids,
            unlocked_at=user_achievement.unlocked_at if user_achievement else None,
            progress=user_achievement.progress if user_achievement else 0
        ))
    
    # 格式化按类别分组的数据
    category_progress = {
        category: AchievementProgressResponse(
            category=category,
            achievements=achievements
        )
        for category, achievements in by_category.items()
    }
    
    # 最近解锁的成就（最多5个）
    recent_unlocked = []
    for ua in user_achievements[:5]:
        achievement = next(
            (a for a in all_achievements if a.id == ua.achievement_id),
            None
        )
        if achievement:
            recent_unlocked.append(UserAchievementResponse(
                id=ua.id,
                user_id=ua.user_id,
                achievement_id=ua.achievement_id,
                unlocked_at=ua.unlocked_at,
                progress=ua.progress,
                interview_id=ua.interview_id,
                achievement=AchievementResponse(**achievement.__dict__)
            ))
    
    return UserAchievementSummary(
        total_achievements=len(all_achievements),
        unlocked_achievements=len(user_achievements),
        total_points=points.total_points if points else 0,
        current_level=points.current_level if points else 1,
        rank=points.rank if points else None,
        by_category=category_progress,
        recent_unlocked=recent_unlocked
    )


@router.get("/category/{category}", response_model=List[AchievementResponse])
async def get_achievements_by_category(
    category: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """按类别获取成就"""
    
    try:
        category_enum = AchievementCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category"
        )
    
    # 获取该类别的成就
    result = await db.execute(
        select(Achievement)
        .where(
            and_(
                Achievement.category == category_enum,
                Achievement.is_active == True
            )
        )
        .order_by(Achievement.sort_order)
    )
    achievements = result.scalars().all()
    
    # 获取用户解锁状态
    user_achievements_result = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == current_user.id)
    )
    user_achievements = {
        ua.achievement_id: ua 
        for ua in user_achievements_result.scalars().all()
    }
    
    response = []
    for achievement in achievements:
        if achievement.is_hidden and achievement.id not in user_achievements:
            continue
        
        user_achievement = user_achievements.get(achievement.id)
        
        response.append(AchievementResponse(
            **achievement.__dict__,
            is_unlocked=user_achievement is not None,
            unlocked_at=user_achievement.unlocked_at if user_achievement else None,
            progress=user_achievement.progress if user_achievement else 0
        ))
    
    return response


# ==================== User Achievements ====================

@router.get("/user", response_model=List[UserAchievementResponse])
async def get_user_achievements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户已解锁的成就"""
    
    result = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == current_user.id)
        .order_by(UserAchievement.unlocked_at.desc())
    )
    user_achievements = result.scalars().all()
    
    # 加载成就详情
    response = []
    for ua in user_achievements:
        achievement_result = await db.execute(
            select(Achievement).where(Achievement.id == ua.achievement_id)
        )
        achievement = achievement_result.scalar_one_or_none()
        
        if achievement:
            response.append(UserAchievementResponse(
                id=ua.id,
                user_id=ua.user_id,
                achievement_id=ua.achievement_id,
                unlocked_at=ua.unlocked_at,
                progress=ua.progress,
                interview_id=ua.interview_id,
                achievement=AchievementResponse(**achievement.__dict__)
            ))
    
    return response


@router.post("/unlock", response_model=UserAchievementResponse)
async def unlock_achievement(
    achievement_create: UserAchievementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """解锁成就"""
    
    # 检查成就是否存在
    achievement_result = await db.execute(
        select(Achievement).where(Achievement.id == achievement_create.achievement_id)
    )
    achievement = achievement_result.scalar_one_or_none()
    
    if not achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Achievement not found"
        )
    
    # 检查是否已解锁
    existing_result = await db.execute(
        select(UserAchievement).where(
            and_(
                UserAchievement.user_id == current_user.id,
                UserAchievement.achievement_id == achievement_create.achievement_id
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Achievement already unlocked"
        )
    
    # 创建解锁记录
    user_achievement = UserAchievement(
        user_id=current_user.id,
        achievement_id=achievement_create.achievement_id,
        interview_id=achievement_create.interview_id,
        unlocked_at=datetime.utcnow(),
        progress=100
    )
    db.add(user_achievement)
    
    # 添加积分
    await _add_points_to_user(db, current_user.id, achievement.reward_points, "achievement_unlocked")
    
    await db.commit()
    await db.refresh(user_achievement)
    
    return UserAchievementResponse(
        **user_achievement.__dict__,
        achievement=AchievementResponse(**achievement.__dict__)
    )


# ==================== User Points ====================

@router.get("/points", response_model=UserPointsResponse)
async def get_user_points(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户积分"""
    
    result = await db.execute(
        select(UserPoints).where(UserPoints.user_id == current_user.id)
    )
    points = result.scalar_one_or_none()
    
    if not points:
        # 创建初始积分记录
        points = UserPoints(user_id=current_user.id)
        db.add(points)
        await db.commit()
        await db.refresh(points)
    
    return UserPointsResponse.model_validate(points)


@router.post("/points/add", response_model=UserPointsResponse)
async def add_points(
    request: AddPointsRequest,
    db: AsyncSession = Depends(get_db)
):
    """添加积分（内部API）"""
    
    await _add_points_to_user(db, request.user_id, request.points, request.reason)
    await db.commit()
    
    result = await db.execute(
        select(UserPoints).where(UserPoints.user_id == request.user_id)
    )
    points = result.scalar_one()
    
    return UserPointsResponse.model_validate(points)


# ==================== Helper Functions ====================

async def _add_points_to_user(db: AsyncSession, user_id: UUID, points: int, reason: str):
    """添加积分到用户"""
    
    result = await db.execute(
        select(UserPoints).where(UserPoints.user_id == user_id)
    )
    user_points = result.scalar_one_or_none()
    
    if not user_points:
        user_points = UserPoints(user_id=user_id)
        db.add(user_points)
    
    # 添加积分
    user_points.total_points += points
    
    # 计算等级（简单实现：每1000分升一级）
    user_points.current_level = (user_points.total_points // 1000) + 1
    
    # 添加到历史记录
    if not user_points.points_history:
        user_points.points_history = []
    
    user_points.points_history.append({
        "date": datetime.utcnow().isoformat(),
        "points": points,
        "reason": reason
    })


async def check_and_unlock_achievements(db: AsyncSession, user_id: UUID, interview_id: UUID):
    """检查并解锁成就（在面试完成后调用）"""
    
    # TODO: 实现成就检查逻辑
    # 1. 获取用户统计数据
    # 2. 检查所有未解锁的成就条件
    # 3. 解锁符合条件的成就
    pass

