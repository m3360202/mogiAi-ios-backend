"""
应用配置管理 (参考 BackendForSupabase 项目)
"""
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置 - 从环境变量加载"""
    
    # 核心应用配置
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Mogi - AI模擬面接アプリ Interview API"
    
    # 认证配置
    ALGORITHM: str = "HS256"
    JWT_SECRET: str = "your-secret-key"  # 默认值，应该被 .env 覆盖
    SECRET_KEY: str = "your-secret-key"  # 兼容旧代码
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8天
    
    # Supabase 配置
    SUPABASE_URL: str = ""  # 添加默认值
    SUPABASE_KEY: str = ""  # 添加默认值
    SUPABASE_JWT_SECRET: str = ""  # JWT secret for verifying Supabase tokens，添加默认值
    SUPABASE_EMAIL: Optional[str] = None
    SUPABASE_PASSWORD: Optional[str] = None
    
    # 数据库配置
    DATABASE_URL: Optional[str] = None
    
    # 环境配置
    ENVIRONMENT: str = "development"

    # Redis 配置（Cloud Run 多实例下用于 session / rate limit 等）
    # Example: redis://localhost:6379/0  or  redis://10.x.x.x:6379/0 (Memorystore via VPC)
    REDIS_URL: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 20
    RATE_LIMIT_PER_MINUTE: int = 240

    # Interview Session Store 配置
    # - memory: 仅进程内（Cloud Run 多实例会丢 session）
    # - redis: Redis 持久化（推荐用于 Cloud Run）
    SESSION_STORE: str = "memory"  # memory | redis
    SESSION_TTL_SECONDS: int = 60 * 60 * 2  # 2 hours
    SESSION_KEY_PREFIX: str = "careerface:interview_session:"
    
    # Google OAuth 配置
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    
    # OpenAI 配置
    OPENAI_API_KEY: Optional[str] = None
    openai_api_key: Optional[str] = None  # 小写版本，向后兼容
    
    # DeepSeek 配置
    DEEPSEEK_API_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # 允许不区分大小写
        extra = "ignore"  # 忽略额外字段
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保大小写版本都存在
        if self.OPENAI_API_KEY and not self.openai_api_key:
            self.openai_api_key = self.OPENAI_API_KEY
        elif self.openai_api_key and not self.OPENAI_API_KEY:
            self.OPENAI_API_KEY = self.openai_api_key


settings = Settings()
