"""
面试经验 Schema
"""
from typing import List, Optional, Union, Dict, Any
from uuid import UUID
from pydantic import BaseModel, field_validator
from datetime import datetime

class QuestionBase(BaseModel):
    content: str

class InterviewExperienceBase(BaseModel):
    company_name: str
    questions: List[QuestionBase]
    tts_voice: Optional[str] = None  # 语音风格，例如: 'ja-JP-Wavenet-A'

    @field_validator('questions', mode='before')
    @classmethod
    def validate_questions(cls, v):
        """将dict列表转换为QuestionBase列表"""
        if isinstance(v, list):
            return [QuestionBase(**item) if isinstance(item, dict) else item for item in v]
        return v

class InterviewExperienceCreate(InterviewExperienceBase):
    pass

class InterviewExperienceUpdate(BaseModel):
    company_name: Optional[str] = None
    questions: Optional[List[QuestionBase]] = None
    status: Optional[str] = None

class InterviewExperienceInDBBase(InterviewExperienceBase):
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class InterviewExperience(InterviewExperienceInDBBase):
    pass

