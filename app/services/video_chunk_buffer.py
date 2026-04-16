"""
视频分片缓冲服务
录制过程中分片上传视频，服务器端拼接成完整视频
"""
import os
import tempfile
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class VideoChunkState:
    """视频分片状态"""
    session_id: str
    temp_file_path: str
    bytes_written: int = 0
    chunk_count: int = 0
    is_finalized: bool = False


class VideoChunkBuffer:
    """视频分片缓冲管理器"""
    
    def __init__(self):
        # Keyed by "{session_id}:{segment_index}" so multiple segments can be buffered independently.
        self._states: Dict[str, VideoChunkState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _key(self, session_id: str, segment_index: int) -> str:
        return f"{session_id}:{int(segment_index)}"
    
    def _get_lock(self, key: str) -> asyncio.Lock:
        """获取或创建会话锁"""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
    
    async def append_chunk(
        self,
        session_id: str,
        segment_index: int,
        chunk_data: bytes,
        suffix: str = ".mp4"
    ) -> VideoChunkState:
        """
        追加视频分片到缓冲区
        
        Args:
            session_id: 会话ID
            chunk_data: 视频分片数据
            suffix: 文件后缀
            
        Returns:
            当前状态
        """
        key = self._key(session_id, segment_index)
        lock = self._get_lock(key)
        async with lock:
            # 如果是新会话，创建临时文件
            if key not in self._states:
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=suffix,
                    prefix=f"video_{session_id}_{int(segment_index)}_"
                )
                temp_file.close()
                
                self._states[key] = VideoChunkState(
                    session_id=session_id,
                    temp_file_path=temp_file.name
                )
                print(f"[VideoChunkBuffer] Created temp file for session {session_id} seg={int(segment_index)}: {temp_file.name}")
            
            state = self._states[key]
            
            # 追加数据到文件
            with open(state.temp_file_path, "ab") as f:
                f.write(chunk_data)
            
            state.bytes_written += len(chunk_data)
            state.chunk_count += 1
            
            print(f"[VideoChunkBuffer] Session {session_id} seg={int(segment_index)}: chunk #{state.chunk_count}, "
                  f"size={len(chunk_data)} bytes, total={state.bytes_written} bytes")
            
            return state
    
    async def finalize(self, session_id: str, segment_index: int) -> Optional[str]:
        """
        完成视频拼接，返回完整视频文件路径
        
        Args:
            session_id: 会话ID
            
        Returns:
            完整视频文件路径，如果不存在则返回 None
        """
        key = self._key(session_id, segment_index)
        lock = self._get_lock(key)
        async with lock:
            if key not in self._states:
                print(f"[VideoChunkBuffer] ✗ Session {session_id} seg={int(segment_index)} not found")
                return None
            
            state = self._states[key]
            state.is_finalized = True
            
            print(f"[VideoChunkBuffer] ✓ Finalized session {session_id} seg={int(segment_index)}: "
                  f"{state.chunk_count} chunks, {state.bytes_written} bytes total")
            
            return state.temp_file_path
    
    async def consume(self, session_id: str, segment_index: int) -> Optional[str]:
        """
        消费并返回完整视频文件路径（调用后状态会被清理）
        
        Args:
            session_id: 会话ID
            
        Returns:
            完整视频文件路径，如果不存在则返回 None
        """
        key = self._key(session_id, segment_index)
        lock = self._get_lock(key)
        async with lock:
            if key not in self._states:
                return None
            
            state = self._states[key]
            video_path = state.temp_file_path
            
            # 从状态中移除（但不删除文件，由调用者负责）
            del self._states[key]
            
            print(f"[VideoChunkBuffer] Consumed session {session_id} seg={int(segment_index)}, path: {video_path}")
            
            return video_path
    
    async def discard(self, session_id: str, segment_index: int) -> None:
        """
        丢弃会话的视频缓冲（删除临时文件）
        
        Args:
            session_id: 会话ID
        """
        key = self._key(session_id, segment_index)
        lock = self._get_lock(key)
        async with lock:
            if key not in self._states:
                return
            
            state = self._states[key]
            
            # 删除临时文件
            if os.path.exists(state.temp_file_path):
                try:
                    os.unlink(state.temp_file_path)
                    print(f"[VideoChunkBuffer] Deleted temp file: {state.temp_file_path}")
                except Exception as e:
                    print(f"[VideoChunkBuffer] ✗ Failed to delete temp file: {e}")
            
            # 从状态中移除
            del self._states[key]
            print(f"[VideoChunkBuffer] Discarded session {session_id} seg={int(segment_index)}")
    
    async def get_state(self, session_id: str, segment_index: int) -> Optional[VideoChunkState]:
        """
        获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态，如果不存在则返回 None
        """
        return self._states.get(self._key(session_id, segment_index))


# 全局单例
video_chunk_buffer = VideoChunkBuffer()

