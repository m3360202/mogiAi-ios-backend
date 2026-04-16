"""
Interview Streaming Helper Service
提供流式面试相关的辅助函数：日志、格式化、TTS、数据提取等
"""
import base64
import json
import time
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict, Any, List

from app.services.speech_service import SpeechService


# 全局 TTS 服务缓存
_speech_service: Optional[SpeechService] = None
_speech_service_failed: bool = False


def ndj(d: dict) -> bytes:
    """转换为 NDJSON 格式"""
    return (json.dumps(d, ensure_ascii=False) + "\n").encode("utf-8")


def log(message: str) -> None:
    """打印带时间戳的日志（毫秒级）"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")


def get_speech_service() -> Optional[SpeechService]:
    """获取或初始化 TTS 服务"""
    global _speech_service, _speech_service_failed

    if _speech_service_failed:
        return None

    if _speech_service is None:
        try:
            _speech_service = SpeechService()
        except Exception as exc:
            print(f"[StreamInterview] ⚠️ SpeechService init failed: {exc}")
            _speech_service_failed = True
            return None

    return _speech_service


async def stream_question_tts(question: str, voice: Optional[str]) -> AsyncGenerator[bytes, None]:
    """流式生成问题的TTS音频"""
    normalized = question.strip()
    if not normalized:
        yield ndj({"tts_status": "skipped"})
        return

    service = get_speech_service()
    if not service:
        yield ndj({"tts_status": "unavailable"})
        return

    resolved_voice = voice or "alloy"

    try:
        # 明确指定日语语言参数，确保TTS使用日语发音
        async for audio_bytes in service.stream_text_to_speech(
            normalized, 
            language="ja",  # 强制使用日语
            voice=resolved_voice
        ):
            yield ndj({
                "tts_chunk_b64": base64.b64encode(audio_bytes).decode("utf-8"),
                "tts_voice": resolved_voice,
                "tts_format": service.tts_format,
            })
        yield ndj({"tts_status": "completed"})
    except Exception as exc:
        print(f"[StreamInterview] ✗ TTS stream error: {exc}")
        yield ndj({
            "tts_status": "error",
            "message": str(exc),
        })


def extract_latest_question(conversation: List[Dict[str, Any]]) -> Optional[str]:
    """从对话历史中提取最新的问题"""
    for item in reversed(conversation):
        if item.get("role") == "system" and item.get("content"):
            return str(item.get("content"))
    return None


def compose_nonverbal_snapshot(
    *,
    realtime: Optional[Dict[str, Any]],
    conversation: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """组合非语言特征快照（从实时数据和对话历史中提取）"""
    snapshot: Dict[str, Any] = {}
    if isinstance(realtime, dict):
        snapshot.update({k: v for k, v in realtime.items() if isinstance(v, (int, float))})

    for item in reversed(conversation):
        if item.get("role") != "user":
            continue

        nonverbal = item.get("nonverbal") or {}
        candidates = [nonverbal.get("realtime"), nonverbal.get("analysis"), nonverbal]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            snapshot.setdefault("eye_contact_rate", extract_numeric(candidate, "eye_contact_rate", "eye_contact"))
            snapshot.setdefault("smile_rate", extract_numeric(candidate, "smile_rate", "smile"))
            snapshot.setdefault("pose_stability", extract_numeric(candidate, "pose_stability", "posture_stability"))
            snapshot.setdefault("confidence", extract_numeric(candidate, "confidence"))
        break

    return {k: v for k, v in snapshot.items() if v is not None}


def extract_numeric(data: Dict[str, Any], *keys: str) -> Optional[float]:
    """从字典中提取数值（支持多个候选键）"""
    for key in keys:
        value = data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def get_tts_format() -> Optional[str]:
    """获取TTS音频格式"""
    service = get_speech_service()
    return getattr(service, "tts_format", "mp3") if service else None





