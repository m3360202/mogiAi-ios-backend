"""
数据库连接和会话管理
"""
from typing import AsyncGenerator, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.orm import declarative_base

from app.core.config import settings


# 延迟创建引擎，避免在 DATABASE_URL 缺失时立即失败
engine: Optional[AsyncEngine] = None
async_session_maker: Optional[async_sessionmaker] = None

def _create_engine_if_needed() -> Optional[AsyncEngine]:
    """如果需要且可能，创建数据库引擎"""
    global engine, async_session_maker
    
    if engine is not None:
        return engine
    
    if not settings.DATABASE_URL:
        print("[Database] ⚠️ DATABASE_URL not set, database features will be unavailable")
        return None
    
    try:
        engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=20,
            max_overflow=10,
            echo=settings.ENVIRONMENT == "development",
            pool_pre_ping=True,  # 检查连接健康状态
        )
        
        # 创建会话工厂
        async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        return engine
    except Exception as e:
        print(f"[Database] ⚠️ Failed to create database engine: {e}")
        return None

# 创建基础模型类
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话"""
    _create_engine_if_needed()
    
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. DATABASE_URL may be missing or invalid.")
    
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库"""
    print("[Database] 🚀 Initializing database...")
    try:
        # 创建引擎（如果可能）
        db_engine = _create_engine_if_needed()
        
        if db_engine is None:
            print("[Database] ⚠️ DATABASE_URL not set, skipping database initialization")
            return
        
        async with db_engine.begin() as conn:
            # 创建所有表
            await conn.run_sync(Base.metadata.create_all)
            print("[Database] ✅ Tables created/verified successfully")
        
        # 预热连接池：执行一个简单的查询
        if async_session_maker is not None:
            try:
                async with async_session_maker() as session:
                    await session.execute(text("SELECT 1"))
                    print("[Database] ✅ Connection pool warmed up successfully")
            except Exception as e:
                print(f"[Database] ⚠️ Connection pool warmup failed: {e}")
                # 不抛出异常，继续启动
    except Exception as e:
        print(f"[Database] ⚠️ Database initialization failed: {e}")
        print("[Database] ⚠️ Application will continue to start, but database features may not work")
        # 不抛出异常，允许应用继续启动（健康检查端点应该仍然可用）


async def close_db() -> None:
    """关闭数据库连接"""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None

