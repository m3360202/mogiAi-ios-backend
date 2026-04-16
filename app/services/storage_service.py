"""
Supabase Storage Service
用于管理面试录音、录像等文件的上传、下载和删除
"""
import os
import uuid
from datetime import datetime
from typing import BinaryIO, Optional
from io import BytesIO

from app.core.supabase import supabase_admin
from app.core.config import settings


class StorageService:
    """Supabase Storage文件存储服务"""
    
    def __init__(self):
        # 存储桶名称，从环境变量获取或使用默认值
        self.bucket = getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'interview-recordings')
        
    async def upload_audio(
        self,
        file: BinaryIO,
        user_id: str,
        interview_id: Optional[str] = None,
        file_extension: str = "webm"
    ) -> dict:
        """
        上传音频文件到 Supabase Storage
        
        Args:
            file: 文件对象（二进制流）
            user_id: 用户ID
            interview_id: 面试ID（可选）
            file_extension: 文件扩展名，默认webm
            
        Returns:
            dict: 包含url和path的字典
        """
        try:
            # 生成唯一文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{timestamp}_{unique_id}.{file_extension}"
            
            # 构建路径：audios/{user_id}/{interview_id}/{filename}
            if interview_id:
                path = f"audios/{user_id}/{interview_id}/{filename}"
            else:
                path = f"audios/{user_id}/{filename}"
            
            # 读取文件内容
            if isinstance(file, BytesIO):
                file_content = file.getvalue()
            else:
                file_content = file.read()
            
            # 上传文件
            response = supabase_admin.storage.from_(self.bucket).upload(
                path,
                file_content,
                file_options={
                    "content-type": f"audio/{file_extension}",
                    "cache-control": "3600",
                    "upsert": "false"  # 不覆盖已存在的文件
                }
            )
            
            # 获取公开URL
            public_url = supabase_admin.storage.from_(self.bucket).get_public_url(path)
            
            return {
                "success": True,
                "url": public_url,
                "path": path,
                "filename": filename
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def upload_video(
        self,
        file: BinaryIO,
        user_id: str,
        interview_id: Optional[str] = None,
        file_extension: str = "mp4"
    ) -> dict:
        """
        上传视频文件到 Supabase Storage
        
        Args:
            file: 文件对象（二进制流）
            user_id: 用户ID
            interview_id: 面试ID（可选）
            file_extension: 文件扩展名，默认mp4
            
        Returns:
            dict: 包含url和path的字典
        """
        try:
            # 生成唯一文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{timestamp}_{unique_id}.{file_extension}"
            
            # 构建路径：videos/{user_id}/{interview_id}/{filename}
            if interview_id:
                path = f"videos/{user_id}/{interview_id}/{filename}"
            else:
                path = f"videos/{user_id}/{filename}"
            
            # 读取文件内容
            if isinstance(file, BytesIO):
                file_content = file.getvalue()
            else:
                file_content = file.read()
            
            # 上传文件
            response = supabase_admin.storage.from_(self.bucket).upload(
                path,
                file_content,
                file_options={
                    "content-type": f"video/{file_extension}",
                    "cache-control": "3600",
                    "upsert": "false"
                }
            )
            
            # 获取公开URL
            public_url = supabase_admin.storage.from_(self.bucket).get_public_url(path)
            
            return {
                "success": True,
                "url": public_url,
                "path": path,
                "filename": filename
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def upload_transcript(
        self,
        content: str,
        user_id: str,
        interview_id: str,
        filename: Optional[str] = None
    ) -> dict:
        """
        上传转录文本文件到 Supabase Storage
        
        Args:
            content: 文本内容
            user_id: 用户ID
            interview_id: 面试ID
            filename: 文件名（可选）
            
        Returns:
            dict: 包含url和path的字典
        """
        try:
            # 生成文件名
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"transcript_{timestamp}.txt"
            
            # 构建路径
            path = f"transcripts/{user_id}/{interview_id}/{filename}"
            
            # 将文本转为字节
            file_content = content.encode('utf-8')
            
            # 上传文件
            response = supabase_admin.storage.from_(self.bucket).upload(
                path,
                file_content,
                file_options={
                    "content-type": "text/plain; charset=utf-8",
                    "cache-control": "3600",
                    "upsert": "true"  # 允许覆盖转录文件
                }
            )
            
            # 获取公开URL
            public_url = supabase_admin.storage.from_(self.bucket).get_public_url(path)
            
            return {
                "success": True,
                "url": public_url,
                "path": path,
                "filename": filename
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def delete_file(self, path: str) -> dict:
        """
        删除文件
        
        Args:
            path: 文件路径
            
        Returns:
            dict: 删除结果
        """
        try:
            response = supabase_admin.storage.from_(self.bucket).remove([path])
            return {
                "success": True,
                "message": "File deleted successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_file_url(self, path: str) -> Optional[str]:
        """
        获取文件的公开URL
        
        Args:
            path: 文件路径
            
        Returns:
            str: 公开URL，如果失败返回None
        """
        try:
            public_url = supabase_admin.storage.from_(self.bucket).get_public_url(path)
            return public_url
        except Exception as e:
            return None
    
    async def download_file(self, path: str) -> Optional[bytes]:
        """
        下载文件内容
        
        Args:
            path: 文件路径
            
        Returns:
            bytes: 文件内容，如果失败返回None
        """
        try:
            response = supabase_admin.storage.from_(self.bucket).download(path)
            return response
        except Exception as e:
            return None


# 创建单例实例
storage_service = StorageService()

