"""Google Cloud Text-to-Speech API 端点"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.google_tts_service import GoogleTTSService


router = APIRouter()


class TTSRequest(BaseModel):
    """TTS 请求模型"""
    text: str = Field(..., description="要合成的文本")
    language_code: str = Field(default="ja-JP", description="语言代码 (如 'ja-JP', 'zh-CN', 'en-US')")
    voice_name: str | None = Field(default=None, description="语音名称 (如 'ja-JP-Neural2-B')，为空则使用默认语音")
    speaking_rate: float = Field(default=1.0, ge=0.25, le=4.0, description="语速 (0.25-4.0)")
    pitch: float = Field(default=0.0, ge=-20.0, le=20.0, description="音调 (-20.0 到 20.0)")
    audio_encoding: str = Field(default="MP3", description="音频编码 (MP3, LINEAR16, OGG_OPUS)")


class VoicesRequest(BaseModel):
    """获取语音列表请求"""
    language_code: str | None = Field(default=None, description="可选的语言代码过滤器")


@router.post("/synthesize")
async def synthesize_speech(request: TTSRequest):
    """
    使用 Google Cloud TTS 合成语音
    
    Args:
        request: TTS 请求参数
    
    Returns:
        音频文件流 (MP3 格式)
    """
    try:
        tts_service = GoogleTTSService()
        
        audio_content = await tts_service.synthesize(
            text=request.text,
            language_code=request.language_code,
            voice_name=request.voice_name,
            speaking_rate=request.speaking_rate,
            pitch=request.pitch,
            audio_encoding=request.audio_encoding
        )
        
        # 根据编码类型设置 MIME 类型
        media_type_map = {
            "MP3": "audio/mpeg",
            "LINEAR16": "audio/wav",
            "OGG_OPUS": "audio/ogg"
        }
        media_type = media_type_map.get(request.audio_encoding.upper(), "audio/mpeg")
        
        return Response(
            content=audio_content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=speech.{request.audio_encoding.lower()}"
            }
        )
        
    except RuntimeError as e:
        # 配置错误
        raise HTTPException(
            status_code=500,
            detail=f"Google TTS configuration error: {str(e)}"
        )
    except Exception as e:
        # 其他错误
        raise HTTPException(
            status_code=500,
            detail=f"Text to speech synthesis failed: {str(e)}"
        )


@router.post("/voices")
async def list_voices(request: VoicesRequest):
    """
    获取 Google Cloud TTS 可用的语音列表
    
    Args:
        request: 语音列表请求参数
    
    Returns:
        可用的语音列表
    """
    try:
        tts_service = GoogleTTSService()
        voices = tts_service.get_available_voices(language_code=request.language_code)
        
        return {
            "voices": voices,
            "count": len(voices)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch voices: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    检查 Google TTS 服务是否正常
    
    Returns:
        健康状态
    """
    try:
        tts_service = GoogleTTSService()
        # 尝试合成一个简单的测试文本
        await tts_service.synthesize(
            text="Test",
            language_code="en-US"
        )
        return {
            "status": "healthy",
            "service": "Google Cloud Text-to-Speech"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "Google Cloud Text-to-Speech",
            "error": str(e)
        }

