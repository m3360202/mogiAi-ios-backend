"""
Supabase 客户端管理 (参考 BackendForSupabase 项目)
"""
import logging
import time
from supabase import create_client, Client

from app.core.config import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Supabase 客户端单例"""
    
    def __init__(self):
        self.client: Client | None = None
        self.last_refresh = 0
        self.refresh_interval = 3600  # 每小时刷新一次
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化或重新初始化 Supabase 客户端"""
        try:
            # ✅ Allow app to boot in dev/CI even when Supabase is not configured.
            if not getattr(settings, "SUPABASE_URL", None) or not getattr(settings, "SUPABASE_KEY", None):
                self.client = None
                logger.warning("Supabase client not configured (SUPABASE_URL/SUPABASE_KEY missing)")
                return

            self.client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY,
            )
            
            # 如果提供了用户凭据，则登录获取 JWT
            supabase_email = settings.SUPABASE_EMAIL
            supabase_password = settings.SUPABASE_PASSWORD
            
            if supabase_email and supabase_password:
                try:
                    response = self.client.auth.sign_in_with_password({
                        "email": supabase_email,
                        "password": supabase_password
                    })
                    
                    if response.user and response.session:
                        access_token = response.session.access_token
                        refresh_token = response.session.refresh_token
                        self.client.auth.set_session(access_token, refresh_token)
                        self.last_refresh = time.time()
                        logger.info("Supabase 客户端已成功初始化（用户认证）")
                    else:
                        logger.warning("认证响应缺少用户或会话信息")
                        
                except Exception as auth_error:
                    logger.warning(f"用户认证失败，继续使用服务角色：{auth_error}")
            else:
                logger.info("未提供用户凭据，使用服务角色认证")
                
        except Exception as e:
            # Do not crash module import; fail only when actually used.
            logger.error(f"初始化 Supabase 客户端失败：{e}")
            self.client = None
            return
    
    def get_client(self) -> Client:
        """获取 Supabase 客户端，必要时刷新"""
        if self.client is None:
            raise RuntimeError("Supabase client is not configured. Set SUPABASE_URL and SUPABASE_KEY.")

        current_time = time.time()
        if current_time - self.last_refresh > self.refresh_interval:
            logger.info("刷新 Supabase 连接")
            try:
                self._refresh_session()
            except Exception as e:
                logger.warning(f"刷新会话失败，重新初始化：{e}")
                self._initialize_client()
        
        if self.client is None:
            raise RuntimeError("Supabase client is not configured. Set SUPABASE_URL and SUPABASE_KEY.")
        return self.client
    
    def _refresh_session(self):
        """刷新当前会话"""
        if self.client and self.client.auth.get_session():
            session = self.client.auth.get_session()
            if session and session.refresh_token:
                response = self.client.auth.refresh_session(session.refresh_token)
                if response.session:
                    self.last_refresh = time.time()
                    logger.info("会话刷新成功")
                else:
                    raise Exception("刷新会话失败")
            else:
                raise Exception("没有有效的会话可刷新")
        else:
            raise Exception("没有可用的客户端或会话")


# 创建全局实例（但不要在 import 时强制 get_client()）
_supabase_instance = SupabaseClient()

# 导出全局客户端（兼容性）：未配置时为 None，调用方应使用 get_supabase_client()
supabase = _supabase_instance.client
supabase_admin = _supabase_instance.client  # 管理员客户端别名

def get_supabase_client() -> Client:
    """获取 Supabase 客户端实例"""
    return _supabase_instance.get_client()
