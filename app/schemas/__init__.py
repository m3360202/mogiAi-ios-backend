"""
Pydantic数据模式
"""
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.schemas.interview import InterviewCreate, InterviewResponse, InterviewConfig
from app.schemas.evaluation import EvaluationResponse, EvaluationScores
from app.schemas.corporate import CorporateTemplateCreate, CorporateTemplateResponse

__all__ = [
    "UserCreate", "UserLogin", "UserResponse", "Token",
    "InterviewCreate", "InterviewResponse", "InterviewConfig",
    "EvaluationResponse", "EvaluationScores",
    "CorporateTemplateCreate", "CorporateTemplateResponse"
]

