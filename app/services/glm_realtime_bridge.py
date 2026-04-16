"""
GLM Realtime bridge (minimal): connects to BigModel GLM-Realtime WS and proxies
conversation items and response events.

Env:
- GLM_API_KEY : API key for Authorization
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, Optional, AsyncGenerator

import websockets

GLM_WSS = "wss://open.bigmodel.cn/api/paas/v4/realtime"


class GLMRealtimeBridge:
    def __init__(self, style: str = "neutral", preset_prompts: Optional[list[str]] = None) -> None:
        self.api_key = os.getenv("GLM_API_KEY", "")
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self.style = style
        self.preset_prompts = preset_prompts or []
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        if not self.api_key:
            print("[GLM] Error: API key not configured")
            return False
        try:
            print(f"[GLM] Connecting to {GLM_WSS}...")
            # Use additional_headers parameter (correct for websockets library)
            self._ws = await websockets.connect(
                GLM_WSS, 
                additional_headers={"Authorization": f"Bearer {self.api_key}"}
            )
            print("[GLM] WebSocket connected, waiting for session.created...")
            # Don't send session.update immediately - wait for session.created first
            # Then configure later if needed
            print("[GLM] Connected successfully")
            return True
        except Exception as e:
            print(f"[GLM] Connection failed: {type(e).__name__}: {e}")
            self._ws = None
            return False

    async def close(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _send(self, obj: Dict[str, Any]) -> None:
        async with self._lock:
            if not self._ws:
                return
            msg = json.dumps(obj, ensure_ascii=False)
            print(f"[GLM] Sending: {obj.get('type', 'unknown')} - {msg[:200]}")
            await self._ws.send(msg)

    async def add_user_text(self, text: str) -> None:
        if not text.strip():
            return
        await self._send({
            "type": "conversation.item.create",
            "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}
        })

    async def inject_system_directive(self, directive: str) -> None:
        await self._send({
            "type": "conversation.item.create",
            "item": {"type": "message", "role": "system", "content": [{"type": "input_text", "text": directive}]}
        })

    async def create_response(self) -> None:
        await self._send({"type": "response.create"})

    async def append_audio_pcm16(self, pcm_bytes: bytes, seq: int) -> None:
        if not pcm_bytes:
            return
        # hex encode to keep JSON safe (or use base64)
        # GLM expects 'audio' field with base64-encoded PCM16 data
        import base64
        audio_b64 = base64.b64encode(pcm_bytes).decode('utf-8')
        print(f"[GLM] Appending audio: {len(pcm_bytes)} bytes -> {len(audio_b64)} b64 chars")
        await self._send({
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        })

    async def commit_audio(self) -> None:
        print("[GLM] Committing audio buffer")
        await self._send({"type": "input_audio_buffer.commit"})

    async def events(self) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._ws:
            return
        async for raw in self._ws:
            try:
                ev = json.loads(raw)
                yield ev
            except Exception:
                continue


