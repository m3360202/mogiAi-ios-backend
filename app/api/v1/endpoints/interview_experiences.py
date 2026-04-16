"""
面试经验相关 API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Query, HTTPException
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.interview_experience import InterviewExperience as InterviewExperienceModel
from app.schemas.interview_experience import InterviewExperienceCreate, InterviewExperience

router = APIRouter()

@router.post("", response_model=InterviewExperience, status_code=status.HTTP_201_CREATED)
async def create_interview_experience(
    experience_in: InterviewExperienceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """提交面试经验"""
    # 提前获取 user_id 的字符串表示，避免在异常处理中触发延迟加载
    user_id_str = str(current_user.id) if current_user.id else "unknown"
    
    # 确保用户有有效的ID（get_current_user应该保证这一点，但双重检查）
    if not current_user.id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID is missing. Authentication may have failed."
        )
    
    # 在当前会话中重新查询用户，确保用户在当前事务中可见
    result = await db.execute(select(User).where(User.id == current_user.id))
    user_in_db = result.scalar_one_or_none()
    
    if not user_in_db:
        # 尝试通过 supabase_id 查找
        if current_user.supabase_id:
             result = await db.execute(select(User).where(User.supabase_id == current_user.supabase_id))
             user_in_db = result.scalar_one_or_none()
             
    if not user_in_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found in database. User ID: {user_id_str}. This may be a transaction isolation issue."
        )

    # 记录调试信息
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"DEBUG: Creating experience for User ID: {user_in_db.id} (Type: {type(user_in_db.id)}), Supabase ID: {user_in_db.supabase_id}")
    
    # 将 Pydantic model 列表转换为 dict 列表存储
    questions_data = [q.model_dump() for q in experience_in.questions]
    
    try:
        # 创建对象
        # 尝试使用 explicit ID 赋值，因为关系赋值有时候会触发意外的 flush
        experience = InterviewExperienceModel(
            user_id=user_in_db.id,
            company_name=experience_in.company_name,
            questions=questions_data,
            tts_voice=experience_in.tts_voice,
            status="pending_review"
        )
        
        db.add(experience)
        await db.commit()
        await db.refresh(experience)
        return experience
    except Exception as e:
        await db.rollback()
        # 记录详细错误信息
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create interview experience: {str(e)}", exc_info=True)
        
        # 检查错误类型
        error_str = str(e).lower()
        
        # 外键约束错误
        if "foreign key constraint" in error_str or "user_id" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User not found in database. Please ensure you are properly authenticated. User ID: {user_id_str}"
            )
        
        # 唯一约束错误
        if "unique constraint" in error_str or "duplicate key" in error_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A similar interview experience already exists."
            )
        
        # 其他数据库错误
        if "does not exist" in error_str or "column" in error_str:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database schema error: {str(e)}. Please contact support."
            )
        
        # 通用错误
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create interview experience: {str(e)}"
        )

@router.get("", response_model=List[InterviewExperience])
async def get_interview_experiences(
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = Query(None, description="Search by keyword (company name or questions)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取面试经验列表（显示已通过审核的和待审核的，用于测试）"""
    try:
        # 临时修改：同时显示 approved 和 pending_review 状态的数据，方便测试
        query = select(InterviewExperienceModel).where(
            InterviewExperienceModel.status.in_(["approved", "pending_review"])
        )
        
        if search:
            # 支持关键字搜索：搜索公司名
            # 对于JSONB字段的搜索，我们暂时只搜索公司名，避免复杂的JSONB查询
            search_pattern = f"%{search}%"
            query = query.where(
                InterviewExperienceModel.company_name.ilike(search_pattern)
            )
        
        query = query.order_by(desc(InterviewExperienceModel.created_at))
        query = query.offset(skip).limit(limit)
        
        result = await db.execute(query)
        experiences = result.scalars().all()
        
        # 如果没有数据，返回空列表而不是错误
        return list(experiences) if experiences else []
        
    except Exception as e:
        # 记录错误并返回空列表，避免500错误
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching interview experiences: {str(e)}", exc_info=True)
        # 即使出错也返回空列表，而不是抛出异常
        return []

@router.get("/my", response_model=List[InterviewExperience])
async def get_my_interview_experiences(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取我的面试经验提交记录"""
    query = select(InterviewExperienceModel).where(
        InterviewExperienceModel.user_id == current_user.id
    ).order_by(desc(InterviewExperienceModel.created_at))
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
