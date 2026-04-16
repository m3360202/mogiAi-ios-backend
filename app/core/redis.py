"""
Redis连接管理
"""
from typing import Optional
import redis.asyncio as redis
from app.core.config import settings


class RedisClient:
    """Redis客户端"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def connect(self):
        """连接Redis"""
        if not getattr(settings, "REDIS_URL", None):
            # Redis 未配置：保持 None（调用方应自行降级/放行）
            self.redis = None
            return
        self.redis = await redis.from_url(
            settings.REDIS_URL,
            max_connections=getattr(settings, "REDIS_MAX_CONNECTIONS", 20),
            decode_responses=True,
        )
    
    async def disconnect(self):
        """断开连接"""
        if self.redis:
            await self.redis.close()
            self.redis = None
    
    async def get(self, key: str) -> Optional[str]:
        """获取值"""
        if self.redis:
            return await self.redis.get(key)
        return None
    
    async def set(self, key: str, value: str, expire: int = 3600):
        """设置值"""
        if self.redis:
            await self.redis.set(key, value, ex=expire)

    async def set_if_not_exists(self, key: str, value: str, expire: int = 3600) -> bool:
        """
        原子写入（仅当 key 不存在）。用于分布式锁/幂等。
        Returns:
            True if set succeeded, False otherwise.
        """
        if not self.redis:
            return False
        res = await self.redis.set(key, value, ex=expire, nx=True)
        return bool(res)

    async def delete_if_value_matches(self, key: str, expected_value: str) -> bool:
        """
        安全释放锁：仅当 key 的值匹配 expected_value 时删除。
        Returns:
            True if deleted, False otherwise.
        """
        if not self.redis:
            return False
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        deleted = await self.redis.eval(script, 1, key, expected_value)
        return bool(deleted)
    
    async def delete(self, key: str):
        """删除键"""
        if self.redis:
            await self.redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if self.redis:
            return await self.redis.exists(key) > 0
        return False


# 全局Redis客户端实例
redis_client = RedisClient()

