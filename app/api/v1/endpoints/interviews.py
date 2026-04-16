"""
面试相关API端点
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.interview import InterviewCreate, InterviewResponse, ConversationMessage, AudioUpload
from app.services.interview_service import InterviewService
from app.services.speech_service import SpeechService
from app.api.dependencies import get_current_user
from app.models.user import User


router = APIRouter()


@router.post("", response_model=InterviewResponse, status_code=status.HTTP_201_CREATED)
async def create_interview(
    interview_data: InterviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建新的面试会话"""
    interview_service = InterviewService(db)
    interview = await interview_service.create_interview(
        user_id=current_user.id,
        config=interview_data.config
    )
    return interview


@router.get("", response_model=List[InterviewResponse])
async def list_interviews(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的面试记录列表"""
    interview_service = InterviewService(db)
    interviews = await interview_service.get_user_interviews(
        user_id=current_user.id,
        skip=skip,
        limit=limit
    )
    return interviews


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取指定面试详情"""
    interview_service = InterviewService(db)
    interview = await interview_service.get_interview(interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.post("/{interview_id}/start")
async def start_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """开始面试"""
    interview_service = InterviewService(db)
    interview = await interview_service.start_interview(interview_id, current_user.id)
    return {"message": "Interview started", "interview": interview}


@router.post("/{interview_id}/audio", response_model=dict)
async def upload_audio(
    interview_id: UUID,
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """上传面试音频并生成下一个问题"""
    interview_service = InterviewService(db)
    speech_service = SpeechService()
    
    # 验证面试归属
    interview = await interview_service.get_interview(interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    # 读取音频数据
    audio_data = await audio_file.read()
    
    # 语音识别
    transcript = await speech_service.transcribe_audio(audio_data)
    
    # 保存音频和文本
    audio_url = await interview_service.save_audio(interview_id, audio_data, audio_file.filename)
    await interview_service.update_transcript(interview_id, transcript)
    
    # 生成下一个问题
    next_question = await interview_service.generate_ai_response(interview, transcript)
    
    # 检查面试是否应该结束
    interview_status = "recording"
    if interview.status == "completed" or "終了" in next_question:
        interview_status = "completed"
    
    # 添加对话历史
    await interview_service.add_conversation_message(interview_id, "user", transcript)
    await interview_service.add_conversation_message(interview_id, "assistant", next_question)
    
    return {
        "audio_url": audio_url,
        "transcript": transcript,
        "next_question": next_question,
        "interview_status": interview_status
    }


@router.post("/{interview_id}/message")
async def send_message(
    interview_id: UUID,
    message: ConversationMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """发送对话消息（Advanced/Corporate模式）"""
    interview_service = InterviewService(db)
    
    # 验证面试归属
    interview = await interview_service.get_interview(interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    if interview.mode not in ["advanced", "corporate"]:
        raise HTTPException(status_code=400, detail="This mode does not support conversation")
    
    # 生成AI回复
    ai_response = await interview_service.generate_ai_response(interview, message.content)
    
    # 保存对话历史
    await interview_service.add_conversation_message(interview_id, message.role, message.content)
    await interview_service.add_conversation_message(interview_id, "assistant", ai_response)
    
    return {
        "user_message": message.content,
        "ai_response": ai_response
    }


@router.post("/{interview_id}/complete")
async def complete_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """完成面试"""
    interview_service = InterviewService(db)
    interview = await interview_service.complete_interview(interview_id, current_user.id)
    return {"message": "Interview completed", "interview": interview}


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除面试记录"""
    interview_service = InterviewService(db)
    await interview_service.delete_interview(interview_id, current_user.id)
    return None

