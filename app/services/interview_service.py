"""
面试服务
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
import os
import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.interview import Interview
from app.schemas.interview import InterviewConfig
from app.services.ai_service import AIService


class InterviewService:
    """面试服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIService()
    
    async def create_interview(self, user_id: UUID, config: InterviewConfig) -> Interview:
        """创建新的面试会话"""
        interview = Interview(
            user_id=user_id,
            mode=config.mode,
            topic=config.topic,
            scenario=config.scenario,
            duration=config.duration,
            company_name=config.company_name,
            position=config.position,
            interview_stage=config.interview_stage,
            status="created"
        )
        
        self.db.add(interview)
        await self.db.commit()
        await self.db.refresh(interview)
        
        return interview
    
    async def get_interview(self, interview_id: UUID, user_id: UUID) -> Optional[Interview]:
        """获取指定面试"""
        result = await self.db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
    
    async def get_user_interviews(
        self, 
        user_id: UUID, 
        skip: int = 0, 
        limit: int = 20
    ) -> List[Interview]:
        """获取用户的面试列表"""
        result = await self.db.execute(
            select(Interview)
            .where(Interview.user_id == user_id)
            .order_by(Interview.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def start_interview(self, interview_id: UUID, user_id: UUID) -> Interview:
        """开始面试"""
        interview = await self.get_interview(interview_id, user_id)
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        
        interview.status = "recording"
        interview.started_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(interview)
        
        return interview
    
    async def save_audio(self, interview_id: UUID, audio_data: bytes, filename: str) -> str:
        """保存音频文件"""
        # 确保上传目录存在
        upload_dir = settings.FILE_UPLOAD_PATH
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成文件路径
        file_extension = os.path.splitext(filename)[1]
        audio_filename = f"{interview_id}{file_extension}"
        audio_path = os.path.join(upload_dir, audio_filename)
        
        # 异步写入文件
        async with aiofiles.open(audio_path, 'wb') as f:
            await f.write(audio_data)
        
        # 返回相对路径或URL
        audio_url = f"/uploads/{audio_filename}"
        
        # 更新数据库
        result = await self.db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        if interview:
            interview.audio_url = audio_url
            await self.db.commit()
        
        return audio_url
    
    async def update_transcript(self, interview_id: UUID, transcript: str):
        """更新转录文本"""
        result = await self.db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        if interview:
            interview.transcript = transcript
            await self.db.commit()
    
    async def generate_ai_response(self, interview: Interview, user_message: str) -> str:
        """生成AI回复（Advanced和Corporate模式）"""
        context = {
            "mode": interview.mode,
            "scenario": interview.scenario,
            "company_name": interview.company_name,
            "position": interview.position,
            "interview_stage": interview.interview_stage,
            "conversation_history": interview.conversation_history or {}
        }
        
        # 检查是否应该结束面试
        if await self._should_end_interview(interview, user_message):
            interview.status = "completed"
            interview.completed_at = datetime.utcnow()
            await self.db.commit()
            return "今回の面接はこれで終了です。最後に、弊社について何かご質問はありますか？"
        
        ai_response = await self.ai_service.generate_interview_response(user_message, context)
        return ai_response
    
    async def _should_end_interview(self, interview: Interview, user_message: str) -> bool:
        """判断是否应该结束面试"""
        conversation_history = interview.conversation_history or {}
        messages = conversation_history.get("messages", [])
        
        # 计算当前轮次（每2条消息为一轮：用户回答 + AI提问）
        current_round = len([m for m in messages if m.get("role") == "user"])
        
        # 根据模式确定最大轮次
        if interview.mode == "basic":
            max_rounds = 10
        elif interview.mode == "advanced":
            max_rounds = 18  # 15-20轮，默认18轮
        else:  # corporate
            max_rounds = 12
        
        # 检查是否达到最大轮次
        if current_round >= max_rounds:
            return True
        
        # 检查用户回答质量，决定是否提前结束（表现很差时）
        if current_round > 3:  # 至少进行3轮后才考虑提前结束
            answer_quality = self._assess_user_answer_quality(user_message)
            if answer_quality < 30:  # 质量很差
                return True
        
        return False
    
    def _assess_user_answer_quality(self, answer: str) -> float:
        """评估用户回答质量（0-100分）"""
        if not answer or len(answer.strip()) == 0:
            return 0
        
        # 简单的质量评估规则
        score = 50  # 基础分
        
        # 长度加分（适中的长度）
        length = len(answer)
        if 50 <= length <= 300:  # 50-300字符为理想长度
            score += 20
        elif length > 50:  # 超过50字符但不太长
            score += 10
        elif length > 20:  # 超过20字符
            score += 5
        
        # 内容质量检查
        if "。" in answer or "、" in answer:  # 有标点符号
            score += 10
        
        if "例" in answer or "経験" in answer or "具体" in answer:  # 包含具体内容
            score += 15
        
        if "思います" in answer or "考えます" in answer:  # 包含个人观点
            score += 10
        
        return min(score, 100)
    
    async def add_conversation_message(self, interview_id: UUID, role: str, content: str):
        """添加对话消息到历史记录"""
        result = await self.db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        
        if interview:
            if not interview.conversation_history:
                interview.conversation_history = {"messages": []}
            
            interview.conversation_history["messages"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await self.db.commit()
    
    async def complete_interview(self, interview_id: UUID, user_id: UUID) -> Interview:
        """完成面试"""
        interview = await self.get_interview(interview_id, user_id)
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        
        interview.status = "completed"
        interview.completed_at = datetime.utcnow()
        
        await self.db.commit()
        await self.db.refresh(interview)
        
        return interview
    
    async def delete_interview(self, interview_id: UUID, user_id: UUID):
        """删除面试记录"""
        interview = await self.get_interview(interview_id, user_id)
        if not interview:
            raise HTTPException(status_code=404, detail="Interview not found")
        
        await self.db.delete(interview)
        await self.db.commit()

