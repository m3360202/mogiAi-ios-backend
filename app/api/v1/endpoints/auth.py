"""
Authentication API Endpoints with Supabase Support
与前端 Supabase 登录配合
"""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.auth import decode_supabase_token, get_user_by_supabase_id, get_user_by_email
from app.models.user import User
from app.schemas.user import (
    UserResponse, 
    UserUpdate, 
    UserProfileUpdateRequest, 
    EmailUpdateRequest,
    PasswordUpdateRequest,
    SupabaseUpdateRequest
)
from pydantic import BaseModel, EmailStr

router = APIRouter()


# ==================== Schemas ====================

class SyncUserRequest(BaseModel):
    """同步用户请求"""
    supabase_id: str
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_language: str = "ja"


# ==================== Helper Functions ====================

async def get_current_user_from_token(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
) -> User:
    """从 Authorization header 获取当前用户"""
    
    # 提取 Bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌格式"
        )
    
    token = authorization.replace("Bearer ", "")
    
    # 解码 Supabase Token
    token_data = decode_supabase_token(token)
    
    # 从数据库获取用户
    user = await get_user_by_supabase_id(db, token_data.supabase_id)
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在，请先同步用户信息"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    
    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    
    return user


# ==================== API Endpoints ====================

@router.post("/sync", response_model=UserResponse, summary="同步用户信息")
async def sync_user(
    user_data: SyncUserRequest,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    """
    同步 Supabase 用户到后端数据库
    
    前端在用户注册/登录后调用此接口，将 Supabase 用户信息同步到后端数据库
    
    **流程：**
    1. 前端通过 Supabase 注册/登录
    2. 获取 Supabase access_token
    3. 调用此接口同步用户信息
    """
    
    # 验证 token（确保 supabase_id 与 token 一致）
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌格式"
        )
    
    token = authorization.replace("Bearer ", "")
    token_data = decode_supabase_token(token)
    
    # 验证 supabase_id 是否匹配
    if token_data.supabase_id != user_data.supabase_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token 与用户信息不匹配"
        )
    
    # 检查用户是否已存在
    existing_user = await get_user_by_supabase_id(db, user_data.supabase_id)
    
    if existing_user:
        # 更新现有用户信息
        existing_user.email = user_data.email
        existing_user.full_name = user_data.full_name
        existing_user.phone = user_data.phone
        existing_user.avatar_url = user_data.avatar_url
        existing_user.preferred_language = user_data.preferred_language
        existing_user.is_verified = True  # Supabase 用户已验证
        existing_user.last_login = datetime.utcnow()
        
        await db.commit()
        await db.refresh(existing_user)
        
        return existing_user
    
    # 创建新用户
    new_user = User(
        supabase_id=user_data.supabase_id,
        email=user_data.email,
        full_name=user_data.full_name,
        phone=user_data.phone,
        avatar_url=user_data.avatar_url,
        preferred_language=user_data.preferred_language,
        is_verified=True,  # Supabase 用户自动验证
        is_active=True,
        last_login=datetime.utcnow()
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return new_user


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_profile(
    current_user: User = Depends(get_current_user_from_token)
):
    """
    获取当前登录用户的个人信息
    
    **需要认证**: 是  
    **Headers**: Authorization: Bearer {access_token}
    """
    return current_user


@router.put("/me", response_model=UserResponse, summary="更新用户信息")
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    更新当前用户的个人信息
    
    **需要认证**: 是  
    **Headers**: Authorization: Bearer {access_token}
    
    **注意**: 
    - Email 和密码修改需要通过 Supabase 客户端完成
    - 此接口仅更新后端数据库中的用户信息
    """
    
    # 更新字段
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    
    if user_update.phone is not None:
        current_user.phone = user_update.phone
    
    if user_update.avatar_url is not None:
        current_user.avatar_url = user_update.avatar_url
    
    if user_update.preferred_language is not None:
        current_user.preferred_language = user_update.preferred_language
    
    if user_update.user_level is not None:
        current_user.user_level = user_update.user_level
    
    # 更新用户偏好设置
    if user_update.preferred_industries is not None:
        current_user.preferred_industries = user_update.preferred_industries
    
    if user_update.preferred_positions is not None:
        current_user.preferred_positions = user_update.preferred_positions
    
    if user_update.work_status is not None:
        current_user.work_status = user_update.work_status
    
    # 更新性格和就业倾向
    if user_update.personalities is not None:
        current_user.personalities = user_update.personalities
    
    if user_update.career_tendencies is not None:
        current_user.career_tendencies = user_update.career_tendencies
    
    await db.commit()
    await db.refresh(current_user)
    
    return current_user


@router.post("/logout", summary="登出")
async def logout(
    current_user: User = Depends(get_current_user_from_token)
):
    """
    用户登出
    
    **需要认证**: 是  
    **Headers**: Authorization: Bearer {access_token}
    
    **注意**: 
    - 实际的登出操作由前端 Supabase 客户端处理
    - 此接口可用于服务端清理工作（如需要）
    """
    return {
        "message": "ログアウトしました",
        "user_id": str(current_user.id),
        "email": current_user.email
    }


@router.get("/verify", response_model=UserResponse, summary="验证 Token")
async def verify_token(
    current_user: User = Depends(get_current_user_from_token)
):
    """
    验证 Supabase Token 是否有效
    
    **需要认证**: 是  
    **Headers**: Authorization: Bearer {access_token}
    
    **用途**: 
    - 检查 Token 是否过期
    - 获取最新的用户信息
    """
    return current_user


@router.post("/me/update-from-supabase", response_model=UserResponse, summary="同步 Supabase 更新")
async def sync_supabase_update(
    update_data: SupabaseUpdateRequest,
    current_user: User = Depends(get_current_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    从 Supabase 同步用户信息更新
    
    **需要认证**: 是  
    **Headers**: Authorization: Bearer {access_token}
    
    **说明**:
    - 当用户在 Supabase 中更新邮箱或密码后，调用此接口同步到后端
    - 仅更新允许的字段（email, full_name）
    """
    
    # 更新邮箱（如果提供）
    if update_data.email is not None:
        # 检查邮箱是否已被其他用户使用
        existing_user = await get_user_by_email(db, update_data.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="このメールアドレスは既に使用されています"
            )
        current_user.email = update_data.email
    
    # 更新姓名（如果提供）
    if update_data.full_name is not None:
        current_user.full_name = update_data.full_name
    
    await db.commit()
    await db.refresh(current_user)
    
    return current_user


@router.get("/me/oauth-status", summary="获取 OAuth 状态")
async def get_oauth_status(
    current_user: User = Depends(get_current_user_from_token)
):
    """
    获取当前用户的 OAuth 登录状态
    
    **需要认证**: 是  
    **Headers**: Authorization: Bearer {access_token}
    
    **返回**:
    - is_oauth: 是否为 OAuth 登录
    - provider: OAuth 提供商 (google, github 等)
    - can_change_password: 是否可以修改密码
    - can_change_email: 是否可以修改邮箱
    """
    is_oauth = current_user.oauth_provider is not None
    
    return {
        "is_oauth": is_oauth,
        "provider": current_user.oauth_provider,
        "oauth_id": current_user.oauth_id,
        "can_change_password": not is_oauth,  # OAuth 用户不能在后端修改密码
        "can_change_email": True,  # 所有用户都可以修改邮箱（通过 Supabase）
        "email": current_user.email,
        "full_name": current_user.full_name
    }
