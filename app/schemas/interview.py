"""
面试相关数据模式
"""
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class InterviewConfig(BaseModel):
    """面试配置"""
    mode: str = Field(..., pattern="^(basic|advanced|corporate)$")
    topic: Optional[str] = None
    scenario: Optional[str] = None
    duration: int = Field(default=300, ge=60, le=1800)  # 60秒-30分钟
    
    # Corporate模式特有字段
    company_name: Optional[str] = None
    position: Optional[str] = None
    interview_stage: Optional[str] = None


class InterviewCreate(BaseModel):
    """创建面试"""
    config: InterviewConfig


class InterviewResponse(BaseModel):
    """面试响应"""
    id: UUID
    user_id: UUID
    mode: str
    status: str
    topic: Optional[str]
    scenario: Optional[str]
    duration: int
    
    company_name: Optional[str]
    position: Optional[str]
    interview_stage: Optional[str]
    
    audio_url: Optional[str]
    transcript: Optional[str]
    conversation_history: Optional[Dict[str, Any]]
    
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class AudioUpload(BaseModel):
    """音频上传响应"""
    audio_url: str
    transcript: str


class ConversationMessage(BaseModel):
    """对话消息"""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

