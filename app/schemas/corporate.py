"""
企业模板相关数据模式
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


class CorporateTemplateCreate(BaseModel):
    """创建企业模板"""
    company_name: str = Field(..., min_length=1, max_length=100)
    company_website: Optional[str] = None
    company_description: Optional[str] = None
    
    position_title: str = Field(..., min_length=1, max_length=100)
    position_description: Optional[str] = None
    required_skills: Optional[List[str]] = None
    
    interview_stages: Optional[List[str]] = None
    custom_questions: Optional[List[str]] = None
    evaluation_criteria: Optional[Dict[str, Any]] = None
    
    is_public: bool = False


class CorporateTemplateUpdate(BaseModel):
    """更新企业模板"""
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_description: Optional[str] = None
    
    position_title: Optional[str] = None
    position_description: Optional[str] = None
    required_skills: Optional[List[str]] = None
    
    interview_stages: Optional[List[str]] = None
    custom_questions: Optional[List[str]] = None
    evaluation_criteria: Optional[Dict[str, Any]] = None
    
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None


class CorporateTemplateResponse(BaseModel):
    """企业模板响应"""
    id: UUID
    user_id: UUID
    
    company_name: str
    company_website: Optional[str]
    company_description: Optional[str]
    
    position_title: str
    position_description: Optional[str]
    required_skills: Optional[Dict[str, Any]]
    
    interview_stages: Optional[Dict[str, Any]]
    custom_questions: Optional[Dict[str, Any]]
    evaluation_criteria: Optional[Dict[str, Any]]
    
    is_active: bool
    is_public: bool
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

