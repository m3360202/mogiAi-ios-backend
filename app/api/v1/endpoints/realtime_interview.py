"""
Realtime interview endpoints (minimal skeleton):
 - POST /interview/start
 - POST /interview/params
 - GET  /interview/timeline/{session_id}
 - WS   /interview/ws/{session_id}

Notes:
- GLM realtime bridge to be plugged later; this WS currently echoes and simulates flow.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import time
from pydantic import BaseModel, Field

from app.services.interview_session_manager import session_manager
from app.services.glm_realtime_bridge import GLMRealtimeBridge


router = APIRouter()


class StartBody(BaseModel):
    role: str = Field(...)
    system_message: str = Field(...)
    persona: Optional[Dict[str, Any]] = None
    style: str = Field(default="neutral")
    preset_prompts: Optional[List[str]] = None
    thresholds: Optional[Dict[str, float]] = None


@router.post("/start")
async def start_session(body: StartBody) -> Dict[str, Any]:
    print(f"[API] POST /start called: role={body.role}")
    sess = await session_manager.start_session(
        role=body.role,
        system_message=body.system_message,
        persona=body.persona,
        style=body.style,
        preset_prompts=body.preset_prompts,
        thresholds=body.thresholds,
    )
    return {"session_id": sess.session_id}


class ParamsBody(BaseModel):
    style: Optional[str] = None
    preset_prompts: Optional[List[str]] = None
    persona_delta: Optional[Dict[str, Any]] = None
    thresholds: Optional[Dict[str, float]] = None


@router.post("/params/{session_id}")
async def update_params(session_id: str, body: ParamsBody) -> Dict[str, Any]:
    sess = await session_manager.update_params(
        session_id,
        style=body.style,
        preset_prompts=body.preset_prompts,
        persona_delta=body.persona_delta,
        thresholds=body.thresholds,
    )
    return {"ok": True, "style": sess.style}


@router.get("/timeline/{session_id}")
async def get_timeline(session_id: str) -> Dict[str, Any]:
    return await session_manager.get_timeline_doc(session_id)


@router.websocket("/ws/{session_id}")
async def ws_bridge(ws: WebSocket, session_id: str):
    print(f"[WS] Client connected: session_id={session_id}")
    await ws.accept()
    # Attach GLM realtime bridge
    glm = GLMRealtimeBridge()
    connected = await glm.connect()
    print(f"[WS] GLM connected: {connected}")
    t0 = time.time()
    chunk_count = 0  # Track chunks to commit periodically
    def now_sec() -> float:
        return max(0.0, time.time() - t0)
    try:
        async def pump_client():
            while True:
                msg = await ws.receive_json()
                mtype = msg.get("type")
                print(f"[WS] Received: {mtype}")
                if mtype == "seg_start":
                    await session_manager.seg_start(session_id, float(msg.get("t", 0.0)), msg.get("role", "user"))
                    await ws.send_json({"ack": "seg_start"})
                elif mtype == "audio_chunk":
                    # binary PCM16 hex string chunk
                    if connected:
                        data_hex = msg.get("data_hex")
                        seq = int(msg.get("seq", 0))
                        if isinstance(data_hex, str):
                            await glm.append_audio_pcm16(bytes.fromhex(data_hex), seq)
                            # Commit every 3 chunks (~4.5 seconds)
                            nonlocal chunk_count
                            chunk_count += 1
                            if chunk_count % 3 == 0:
                                await glm.commit_audio()
                                print(f"[WS] Committed audio after {chunk_count} chunks")
                            # After 5 chunks (~7.5s), create a response to trigger GLM
                            if chunk_count == 5:
                                print("[WS] Creating response after 5 chunks...")
                                await glm.create_response()
                elif mtype == "text_delta":
                    text = str(msg.get("text", ""))
                    await session_manager.seg_append_text(session_id, text)
                    if connected:
                        await glm.add_user_text(text)
                    await ws.send_json({"ack": "text_delta"})
                elif mtype == "nonverbal":
                    feat = msg.get("feat", {}) or {}
                    await session_manager.seg_append_nonverbal(session_id, feat)
                    await ws.send_json({"ack": "nonverbal"})
                elif mtype == "seg_commit":
                    item = await session_manager.seg_commit(session_id, float(msg.get("t", 0.0)))
                    await ws.send_json({"ack": "seg_commit", "item": (item.__dict__ if item else None)})
                    if connected:
                        await glm.commit_audio()
                        await glm.create_response()
                else:
                    await ws.send_json({"error": "unknown_type"})

        async def pump_glm():
            if not connected:
                print("[WS] GLM not connected, pump_glm exiting")
                return
            print("[WS] pump_glm started, waiting for GLM events...")
            async for ev in glm.events():
                # handle server VAD events for auto turn-taking
                et = ev.get("type")
                print(f"[GLM Event] {et}")
                if et == "input_audio_buffer.speech_started":
                    print("[GLM Event] Speech started detected by Server VAD")
                    await session_manager.seg_start(session_id, now_sec(), role="user")
                elif et == "input_audio_buffer.speech_stopped":
                    print("[GLM Event] Speech stopped detected by Server VAD, creating response...")
                    item = await session_manager.seg_commit(session_id, now_sec())
                    await ws.send_json({"ack": "seg_auto", "item": (item.__dict__ if item else None)})
                    await glm.create_response()
                elif et == "response.text.delta":
                    print(f"[GLM Event] Text delta: {ev.get('delta', '')[:50]}")
                elif et == "response.audio.delta":
                    print(f"[GLM Event] Audio delta received")
                elif et == "error":
                    print(f"[GLM Event] ERROR: {ev}")
                # forward glm event to client for real-time drafting
                await ws.send_json({"type": "glm", "data": ev})

        await asyncio.gather(pump_client(), pump_glm())
    except WebSocketDisconnect:
        print("[WS] Client disconnected")
        await glm.close()
    except Exception as e:
        print(f"[WS] Error: {e}")
        await glm.close()
    finally:
        try:
            await ws.close()
        except:
            pass


