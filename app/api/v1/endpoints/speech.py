"""
语音处理相关API端点
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.services.speech_service import SpeechService


router = APIRouter()


@router.post("/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    language: str = "ja"
):
    """语音转文字"""
    speech_service = SpeechService()
    
    # 验证文件类型
    if not audio_file.content_type or not audio_file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid audio file")
    
    # 读取音频数据
    audio_data = await audio_file.read()
    
    # 语音识别
    transcript = await speech_service.transcribe_audio(audio_data, language)
    
    return {
        "transcript": transcript,
        "language": language
    }


@router.post("/synthesize")
async def synthesize_speech(
    text: str,
    language: str = "ja",
    voice: str = "alloy"
):
    """文字转语音"""
    speech_service = SpeechService()
    
    # 生成语音
    audio_data = await speech_service.text_to_speech(text, language, voice)
    
    return StreamingResponse(
        iter([audio_data]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"attachment; filename=speech.mp3"}
    )


@router.post("/analyze")
async def analyze_audio(
    audio_file: UploadFile = File(...)
):
    """分析音频特征"""
    speech_service = SpeechService()
    
    # 读取音频数据
    audio_data = await audio_file.read()
    
    # 分析音频特征
    audio_features = await speech_service.analyze_audio_features(audio_data)
    
    return audio_features

