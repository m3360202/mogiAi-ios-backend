"""Audio chunk buffering utility for streaming uploads."""

from __future__ import annotations

import asyncio
import os
import struct
import tempfile
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class AudioBufferState:
    path: str
    bytes_written: int
    suffix: str


class AudioChunkBuffer:
    """Persist audio chunks per session before final transcription."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._buffers: Dict[str, AudioBufferState] = {}

    async def append_chunk(
        self,
        session_id: str,
        chunk: bytes,
        *,
        suffix: str = ".wav",
    ) -> AudioBufferState:
        if not chunk:
            # 返回现有缓冲区状态（如果存在）
            async with self._lock:
                return self._buffers.setdefault(
                    session_id,
                    self._create_state(suffix=suffix),
                )

        async with self._lock:
            state = self._buffers.get(session_id)
            if not state:
                state = self._create_state(suffix=suffix)
                self._buffers[session_id] = state

            await asyncio.to_thread(self._append_to_file, state.path, chunk)
            state.bytes_written += len(chunk)
            return state

    async def consume(self, session_id: str) -> Optional[str]:
        async with self._lock:
            state = self._buffers.pop(session_id, None)
        if state:
            # 如果是WAV文件，修复头部
            if state.suffix == ".wav":
                await asyncio.to_thread(self._fix_wav_header, state.path)
            return state.path
        return None

    async def discard(self, session_id: str) -> None:
        path = await self.consume(session_id)
        if path and os.path.exists(path):
            os.remove(path)

    def _create_state(self, *, suffix: str) -> AudioBufferState:
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp.close()
        return AudioBufferState(path=temp.name, bytes_written=0, suffix=suffix)

    @staticmethod
    def _append_to_file(path: str, data: bytes) -> None:
        with open(path, "ab") as fp:
            fp.write(data)
    
    @staticmethod
    def _fix_wav_header(path: str) -> None:
        """
        修复WAV文件头部的大小信息
        当通过chunk拼接创建WAV文件时，头部的大小字段可能不正确
        """
        try:
            # 获取文件大小
            file_size = os.path.getsize(path)
            
            # 读取并验证是否为WAV文件
            with open(path, "r+b") as f:
                # 读取前12字节检查格式
                header = f.read(12)
                if len(header) < 12:
                    print(f"[AudioChunkBuffer] File too small to be valid WAV: {file_size} bytes")
                    return
                
                # 检查RIFF和WAVE标识
                if header[0:4] != b'RIFF' or header[8:12] != b'WAVE':
                    print(f"[AudioChunkBuffer] Not a valid WAV file (missing RIFF/WAVE headers)")
                    return
                
                # 更新文件大小（bytes 4-7）
                f.seek(4)
                f.write(struct.pack('<I', file_size - 8))
                
                # 查找data chunk并更新大小
                f.seek(12)
                while True:
                    chunk_header = f.read(8)
                    if len(chunk_header) < 8:
                        break
                    
                    chunk_id = chunk_header[0:4]
                    chunk_size = struct.unpack('<I', chunk_header[4:8])[0]
                    
                    if chunk_id == b'data':
                        # 更新data chunk大小
                        data_start = f.tell()
                        actual_data_size = file_size - data_start
                        f.seek(data_start - 4)
                        f.write(struct.pack('<I', actual_data_size))
                        print(f"[AudioChunkBuffer] ✓ Fixed WAV header: file_size={file_size}, data_size={actual_data_size}")
                        break
                    else:
                        # 跳过这个chunk
                        f.seek(chunk_size, 1)
                        
        except Exception as e:
            print(f"[AudioChunkBuffer] ⚠️ Failed to fix WAV header: {e}")
            # 不抛出异常，继续使用原文件


audio_chunk_buffer = AudioChunkBuffer()


