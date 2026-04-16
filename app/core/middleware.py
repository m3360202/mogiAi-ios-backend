"""
自定义中间件
"""
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from app.core.redis import redis_client
from app.core.config import settings


logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 记录请求信息
        logger.info(
            "request_started",
            method=request.method,
            url=str(request.url),
            client=request.client.host if request.client else None,
            headers=dict(request.headers)
        )
        
        # 处理请求
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 记录响应信息
        logger.info(
            "request_completed",
            method=request.method,
            url=str(request.url),
            status_code=response.status_code,
            process_time=f"{process_time:.3f}s"
        )
        
        # 添加处理时间头
        response.headers["X-Process-Time"] = str(process_time)
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过健康检查和文档路由
        if request.url.path in ["/health", "/", f"{settings.API_V1_STR}/docs", f"{settings.API_V1_STR}/openapi.json"]:
            return await call_next(request)
        
        # 获取客户端IP
        client_ip = request.client.host if request.client else "unknown"
        
        # 检查速率限制
        rate_limit_key = f"rate_limit:{client_ip}:minute"
        
        try:
            # 获取当前请求计数
            current_requests = await redis_client.get(rate_limit_key)
            
            if current_requests:
                if int(current_requests) >= settings.RATE_LIMIT_PER_MINUTE:
                    return Response(
                        content="Rate limit exceeded",
                        status_code=429,
                        headers={"Retry-After": "60"}
                    )
            
            # 增加请求计数
            if current_requests:
                await redis_client.redis.incr(rate_limit_key)
            else:
                await redis_client.set(rate_limit_key, "1", expire=60)
        
        except Exception as e:
            logger.error("rate_limit_error", error=str(e))
            # 如果Redis出错，允许请求通过
            pass
        
        return await call_next(request)

