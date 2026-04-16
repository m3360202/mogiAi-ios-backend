"""
Supabase视频存储服务
处理视频文件的上传和管理
"""
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Dict
from app.core.supabase import get_supabase_client

class SupabaseVideoService:
    """Supabase视频存储服务"""
    
    def __init__(self):
        self.bucket_name = "interview-videos"  # Supabase存储桶名称
        self.supabase = get_supabase_client()
    
    def _upload_sync(self, video_path: str, file_name: str) -> Optional[str]:
        """同步上传逻辑，将在线程池中执行"""
        try:
            print(f"[SupabaseVideo] Uploading video: {file_name}")
            
            # 读取视频文件
            with open(video_path, 'rb') as f:
                video_data = f.read()
            
            # 上传到Supabase Storage
            response = self.supabase.storage.from_(self.bucket_name).upload(
                path=file_name,
                file=video_data,
                file_options={
                    "content-type": "video/mp4",
                    "cache-control": "3600",
                    "upsert": "false"
                }
            )
            
            print(f"[SupabaseVideo] Upload response: {response}")
            
            # 获取公开URL
            public_url = self.supabase.storage.from_(self.bucket_name).get_public_url(file_name)
            
            print(f"[SupabaseVideo] Video uploaded successfully: {public_url}")
            return public_url
            
        except Exception as e:
            print(f"[SupabaseVideo] Error uploading video: {e}")
            return None

    async def upload_video(
        self, 
        video_path: str,
        session_id: str,
        segment_index: int
    ) -> Optional[str]:
        """
        上传视频到Supabase Storage (异步非阻塞)
        增加超时保护 + 重试，提升长视频/弱网稳定性
        """
        # 生成唯一文件名
        file_ext = Path(video_path).suffix or '.mp4'
        file_name = f"{session_id}/segment_{segment_index}_{uuid.uuid4().hex[:8]}{file_ext}"
        
        loop = asyncio.get_running_loop()
        max_attempts = 3
        timeout_seconds = 180.0
        for attempt in range(1, max_attempts + 1):
            try:
                # 在线程池中执行阻塞的IO操作，并设置超时
                return await asyncio.wait_for(
                    loop.run_in_executor(None, self._upload_sync, video_path, file_name),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                print(f"[SupabaseVideo] ⚠️ Upload timed out (attempt {attempt}/{max_attempts}) seg={segment_index}")
            except Exception as e:
                print(f"[SupabaseVideo] ⚠️ Upload failed (attempt {attempt}/{max_attempts}) seg={segment_index}: {e}")
            if attempt < max_attempts:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
        return None
    
    def _delete_sync(self, video_url: str) -> bool:
        """同步删除逻辑"""
        try:
            parts = video_url.split(f"/storage/v1/object/public/{self.bucket_name}/")
            if len(parts) < 2:
                print(f"[SupabaseVideo] Invalid video URL format: {video_url}")
                return False
            
            file_path = parts[1]
            self.supabase.storage.from_(self.bucket_name).remove([file_path])
            print(f"[SupabaseVideo] Video deleted: {file_path}")
            return True
        except Exception as e:
            print(f"[SupabaseVideo] Error deleting video: {e}")
            return False

    async def delete_video(self, video_url: str) -> bool:
        """删除视频 (异步非阻塞)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._delete_sync, video_url)
    
    def _get_url_sync(self, session_id: str, segment_index: int) -> Optional[str]:
        """同步获取URL逻辑"""
        try:
            response = self.supabase.storage.from_(self.bucket_name).list(path=f"{session_id}/")
            for file in response:
                if f"segment_{segment_index}_" in file['name']:
                    file_path = f"{session_id}/{file['name']}"
                    return self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
            return None
        except Exception as e:
            print(f"[SupabaseVideo] Error getting video URL: {e}")
            return None

    async def get_video_url(self, session_id: str, segment_index: int) -> Optional[str]:
        """获取视频URL (异步非阻塞)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_url_sync, session_id, segment_index)

    def _list_urls_sync(self, session_id: str) -> Dict[int, str]:
        """
        List all uploaded segment URLs for a session in a single call.
        Returns: {segment_index: public_url}
        """
        urls: Dict[int, str] = {}
        try:
            response = self.supabase.storage.from_(self.bucket_name).list(path=f"{session_id}/")
            for file in response or []:
                name = file.get("name")
                if not isinstance(name, str):
                    continue
                # filename example: segment_1_92c17bfd.mp4
                if not name.startswith("segment_"):
                    continue
                parts = name.split("_")
                if len(parts) < 3:
                    continue
                try:
                    idx = int(parts[1])
                except Exception:
                    continue
                if idx in urls:
                    # keep the first seen; names include random uuid so order is not guaranteed
                    continue
                file_path = f"{session_id}/{name}"
                urls[idx] = self.supabase.storage.from_(self.bucket_name).get_public_url(file_path)
        except Exception as e:
            print(f"[SupabaseVideo] Error listing video URLs: {e}")
        return urls

    async def list_video_urls(self, session_id: str) -> Dict[int, str]:
        """List all segment URLs for a session (异步非阻塞)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._list_urls_sync, session_id)


# 创建单例实例
supabase_video_service = SupabaseVideoService()

