"""
Mogi - AI模擬面接アプリ Interview API
主应用入口
"""
from dotenv import load_dotenv
from pathlib import Path

# Load backend/.env reliably even when running from repo root.
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)  # Load .env before importing settings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import init_db, close_db
from app.api.v1.api import api_router
from app.core.middleware import LoggingMiddleware, RateLimitMiddleware
from app.services.evaluation.loggers import LogIdMiddleware
from app.core.redis import redis_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    await init_db()

    # 连接 Redis（若未配置 REDIS_URL 或连接失败，则自动降级）
    try:
        await redis_client.connect()
    except Exception as e:
        # 不阻塞服务启动（rate limit / redis-backed session 会自行降级）
        print(f"[Lifespan] ⚠️ Redis connect failed (continuing without Redis): {e}")
    
    # 配置 LiteLLM 日志级别，减少控制台输出
    import logging
    litellm_logger = logging.getLogger("LiteLLM")
    litellm_logger.setLevel(logging.WARNING)  # 只显示 WARNING 及以上级别
    litellm_logger.propagate = False  # 防止传播到根 logger
    
    yield
    # 关闭时清理
    try:
        await redis_client.disconnect()
    except Exception as e:
        print(f"[Lifespan] ⚠️ Redis disconnect failed: {e}")
    await close_db()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# CORS中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有源，生产环境需要限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 压缩中间件
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 自定义中间件
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(LogIdMiddleware) # Add LogIdMiddleware last (middlewares execution order is LIFO)

# 注册API路由
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Welcome to Mogi - AI模擬面接アプリ Interview API",
        "version": "1.0.0",
        "docs": f"{settings.API_V1_STR}/docs",
        "environment": settings.ENVIRONMENT
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level="info"
    )

