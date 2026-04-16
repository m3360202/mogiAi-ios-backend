"""语音处理服务"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import AsyncGenerator, Dict, Optional

from openai import AsyncOpenAI

from app.core.config import settings


class SpeechService:
    """语音处理服务，支持流式与非流式 TTS/ASR，自动选择 OpenAI 或 Google TTS"""

    def __init__(self):
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.client = AsyncOpenAI(api_key=api_key)
        self.whisper_model = os.getenv("WHISPER_MODEL", getattr(settings, "WHISPER_MODEL", "whisper-1"))
        self.tts_model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        self.tts_stream_model = os.getenv("OPENAI_TTS_STREAM_MODEL", self.tts_model)
        self.tts_format = os.getenv("OPENAI_TTS_FORMAT", "mp3")
        
        # 尝试初始化 Google TTS（可选）
        self.google_tts = None
        try:
            from app.services.google_tts_service import GoogleTTSService
            self.google_tts = GoogleTTSService()
        except Exception:
            # Google TTS 不可用，将只使用 OpenAI TTS
            pass

    async def transcribe_audio(self, audio_data: bytes, language: str = "ja") -> str:
        """语音转文字，使用 Whisper 异步接口"""
        try:
            temp_audio_path = await asyncio.to_thread(self._write_temp_audio, audio_data)

            try:
                with open(temp_audio_path, "rb") as audio_file:
                    transcript = await self.client.audio.transcriptions.create(
                        model=self.whisper_model,
                        file=audio_file,
                        language=language,
                        response_format="text",
                    )
                return str(transcript)
            finally:
                await asyncio.to_thread(self._safe_remove, temp_audio_path)
        except Exception as exc:  # pragma: no cover - 仅用于日志
            raise Exception(f"Speech recognition failed: {exc}") from exc

    def _should_use_google_tts(self, voice: str) -> bool:
        """判断是否应该使用 Google TTS（基于语音名称）"""
        if not self.google_tts:
            return False
        # Google TTS 的语音名称格式：ja-JP-Wavenet-D, cmn-CN-Standard-A 等
        google_voice_prefixes = ['ja-JP-', 'cmn-CN-', 'zh-CN-', 'en-US-Neural', 'en-GB-Neural', 'ko-KR-']
        return any(voice.startswith(prefix) for prefix in google_voice_prefixes)
    
    def _extract_language_code(self, voice: str) -> str:
        """从 Google 语音名称提取语言代码"""
        # ja-JP-Wavenet-D -> ja-JP
        if '-' in voice:
            parts = voice.split('-')
            if len(parts) >= 2:
                return f"{parts[0]}-{parts[1]}"
        return "ja-JP"

    async def text_to_speech(
        self,
        text: str,
        language: str = "ja",
        voice: str = "alloy",
        *,
        format: Optional[str] = None,
    ) -> bytes:
        """文字转语音（一次性返回整段音频）- 自动选择 OpenAI 或 Google TTS"""
        try:
            # 如果语音名称是 Google TTS 格式，使用 Google TTS
            if self._should_use_google_tts(voice):
                language_code = self._extract_language_code(voice)
                return await self.google_tts.synthesize(
                    text=text,
                    language_code=language_code,
                    voice_name=voice,
                    audio_encoding="MP3"
                )
            
            # 否则使用 OpenAI TTS
            response = await self.client.audio.speech.create(
                model=self.tts_model,
                voice=voice,
                input=text,
                response_format=format or self.tts_format,  # OpenAI API 参数名是 response_format
            )
            return response.content  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - 仅用于日志
            raise Exception(f"Text to speech failed: {exc}") from exc

    async def stream_text_to_speech(
        self,
        text: str,
        language: str = "ja",
        voice: str = "alloy",
        *,
        format: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """流式文字转语音 - 自动选择 OpenAI 或 Google TTS"""

        stream_format = format or self.tts_format

        # 如果是 Google TTS，直接返回完整音频（Google TTS 不支持流式）
        if self._should_use_google_tts(voice):
            try:
                audio_blob = await self.text_to_speech(
                    text,
                    language=language,
                    voice=voice,
                    format=stream_format,
                )
                yield audio_blob
                return
            except Exception as exc:
                raise Exception(f"Google TTS failed: {exc}") from exc

        # OpenAI TTS 支持流式
        stream_model = self.tts_stream_model
        try:
            response_ctx = await self.client.audio.speech.with_streaming_response.create(
                model=stream_model,
                voice=voice,
                input=text,
                response_format=stream_format,
            )

            async with response_ctx as stream:
                async for chunk in stream.iter_bytes():  # type: ignore[attr-defined]
                    if chunk:
                        yield bytes(chunk)
            return
        except Exception as exc:
            # 回退到整段音频，仍保持生成器接口
            try:
                audio_blob = await self.text_to_speech(
                    text,
                    language=language,
                    voice=voice,
                    format=stream_format,
                )
                yield audio_blob
                return
            except Exception as nested_exc:  # pragma: no cover - 仅用于日志
                raise Exception(
                    f"Streaming text to speech failed: {exc}; fallback also failed: {nested_exc}"
                ) from nested_exc

    async def analyze_audio_features(self, audio_data: bytes) -> Dict:
        """分析音频特征 - 当前返回模拟数据，可后续接入真实模型"""
        return {
            "speech_rate": 150.0,
            "pause_frequency": 0.15,
            "volume_variation": 0.3,
            "pitch_variation": 0.25,
            "clarity_score": 85.0,
            "confidence_indicator": 78.0,
        }

    @staticmethod
    def _write_temp_audio(audio_data: bytes) -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_data)
            return temp_audio.name

    @staticmethod
    def _safe_remove(path: str) -> None:
        if path and os.path.exists(path):
            os.remove(path)

