"""
用户相关的 Pydantic Schemas
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID


# ==================== 基础 Schemas ====================

class UserBase(BaseModel):
    """用户基础信息"""
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_language: str = "ja"
    user_level: str = "beginner"


class UserCreate(BaseModel):
    """创建用户 (传统注册)"""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    phone: Optional[str] = None


class UserOAuthCreate(BaseModel):
    """创建用户 (OAuth 登录)"""
    supabase_id: str = Field(..., description="Supabase Auth UID")
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    oauth_provider: str = Field(..., description="OAuth 提供商: google, github, etc.")
    oauth_id: str = Field(..., description="OAuth 提供商的用户 ID")


class UserUpdate(BaseModel):
    """更新用户信息"""
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_language: Optional[str] = None
    user_level: Optional[str] = None
    # 用户偏好设置
    preferred_industries: Optional[str] = Field(None, description="偏好行业，逗号分隔")
    preferred_positions: Optional[str] = Field(None, description="偏好职位，逗号分隔")
    work_status: Optional[str] = Field(None, description="工作状态")
    
    # 性格和就业倾向
    personalities: Optional[str] = Field(None, description="性格特征，JSON 数组格式")
    career_tendencies: Optional[str] = Field(None, description="就业倾向，JSON 数组格式")


class UserProfileUpdateRequest(BaseModel):
    """更新个人资料请求 - 包含敏感信息"""
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = Field(None, max_length=500)
    preferred_language: Optional[str] = Field(None, max_length=10)
    user_level: Optional[str] = Field(None, max_length=20)


class EmailUpdateRequest(BaseModel):
    """更新邮箱请求"""
    new_email: EmailStr = Field(..., description="新邮箱地址")
    password: Optional[str] = Field(None, description="当前密码 (非OAuth用户必需)")


class PasswordUpdateRequest(BaseModel):
    """更新密码请求"""
    current_password: str = Field(..., description="当前密码")
    new_password: str = Field(..., min_length=8, description="新密码 (至少8位)")


class SupabaseUpdateRequest(BaseModel):
    """Supabase更新同步请求"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


# 别名，保持向后兼容
UserProfileUpdate = UserUpdate


class UserResponse(BaseModel):
    """用户响应"""
    id: UUID
    supabase_id: Optional[str]
    email: str
    full_name: Optional[str]
    phone: Optional[str]
    avatar_url: Optional[str]
    oauth_provider: Optional[str]
    oauth_id: Optional[str]
    
    is_active: bool
    is_verified: bool
    
    preferred_language: str
    user_level: str
    
    # 用户偏好
    preferred_industries: Optional[str] = None
    preferred_positions: Optional[str] = None
    work_status: Optional[str] = None
    
    # 性格和就业倾向
    personalities: Optional[str] = None
    career_tendencies: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


class UserProfile(BaseModel):
    """用户个人资料（包含统计信息）"""
    id: UUID
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    oauth_provider: Optional[str]
    
    is_active: bool
    is_verified: bool
    
    preferred_language: str
    user_level: str
    
    # 统计信息
    total_interviews: int = 0
    total_practice_sessions: int = 0
    consecutive_days: int = 0
    total_points: int = 0
    total_achievements: int = 0
    
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True


# ==================== 认证相关 Schemas ====================

class Token(BaseModel):
    """JWT Token"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """Token 解码后的数据"""
    supabase_id: Optional[str] = None
    email: Optional[str] = None


class LoginRequest(BaseModel):
    """传统登录请求"""
    email: EmailStr
    password: str


# 别名，保持向后兼容
UserLogin = LoginRequest


class LoginResponse(BaseModel):
    """登录响应"""
    user: UserResponse
    token: Token


class GoogleOAuthRequest(BaseModel):
    """Google OAuth 登录请求"""
    id_token: str = Field(..., description="Google ID Token")


class SupabaseAuthRequest(BaseModel):
    """Supabase 认证请求"""
    supabase_token: str = Field(..., description="Supabase JWT Token")


# ==================== 用户统计 Schemas ====================

class UserStats(BaseModel):
    """用户统计信息"""
    user_id: UUID
    
    # 面试统计
    total_interviews: int
    practice_count: int
    real_count: int
    
    # 练习统计
    today_practice_count: int
    week_practice_count: int
    total_practice_count: int
    
    # 成就统计
    total_achievements: int
    total_points: int
    consecutive_days: int
    
    # 平均分数
    average_score: float
    
    # 六维度统计
    fluency_avg: float
    logic_avg: float
    expression_avg: float
    question_handling_avg: float
    professional_avg: float
    enthusiasm_avg: float
    
    class Config:
        from_attributes = True


# ==================== 验证码相关 Schemas ====================

class EmailVerificationRequest(BaseModel):
    """邮箱验证请求"""
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    """邮箱验证确认"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class PasswordResetRequest(BaseModel):
    """密码重置请求"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """密码重置确认"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)


class PasswordChange(BaseModel):
    """修改密码"""
    old_password: str
    new_password: str = Field(..., min_length=8)
