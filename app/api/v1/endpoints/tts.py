"""Endpoints for Gemini TTS"""

from __future__ import annotations

import base64
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.gemini_tts import synthesize_speech


class TTSRequest(BaseModel):
    text: str
    language_code: Optional[str] = None
    style: Optional[str] = None
    voice: Optional[str] = None
    speaking_rate: Optional[float] = None


class TTSResponse(BaseModel):
    audioBase64: str
    mimeType: str


router = APIRouter(prefix="/tts", tags=["tts"])


@router.post("/gemini", response_model=TTSResponse)
async def create_gemini_tts(request: TTSRequest) -> TTSResponse:
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    audio_bytes, mime_type = await synthesize_speech(
        text=request.text,
        language_code=request.language_code,
        style=request.style,
        voice=request.voice,
        speaking_rate=request.speaking_rate,
    )

    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

    return TTSResponse(audioBase64=audio_base64, mimeType=mime_type)


