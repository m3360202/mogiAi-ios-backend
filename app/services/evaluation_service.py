"""
评估服务
"""
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.interview import Interview
from app.models.evaluation import Evaluation
from app.services.ai_service import AIService


class EvaluationService:
    """评估服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.ai_service = AIService()
    
    async def evaluate_interview(self, interview: Interview) -> Evaluation:
        """评估面试表现"""
        # 使用AI服务进行评估
        evaluation_result = await self.ai_service.evaluate_interview(
            transcript=interview.transcript or "",
            mode=interview.mode,
            conversation_history=interview.conversation_history or {}
        )
        
        # 创建评估记录
        evaluation = Evaluation(
            interview_id=interview.id,
            clarity_score=evaluation_result["scores"]["clarity"],
            evidence_score=evaluation_result["scores"]["evidence"],
            expression_score=evaluation_result["scores"]["expression"],
            engagement_score=evaluation_result["scores"]["engagement"],
            etiquette_score=evaluation_result["scores"]["etiquette"],
            impression_score=evaluation_result["scores"]["impression"],
            overall_score=evaluation_result["scores"]["overall"],
            detailed_feedback=evaluation_result.get("feedback", ""),
            improvement_suggestions=evaluation_result.get("suggestions", {}),
            strengths=evaluation_result.get("strengths", {}),
            weaknesses=evaluation_result.get("weaknesses", {}),
            audio_features=evaluation_result.get("audio_features", {}),
            radar_chart_data=evaluation_result.get("radar_chart_data", {})
        )
        
        self.db.add(evaluation)
        
        # 更新面试状态
        interview.status = "evaluated"
        
        await self.db.commit()
        await self.db.refresh(evaluation)
        
        return evaluation
    
    async def get_evaluation(self, evaluation_id: UUID) -> Optional[Evaluation]:
        """获取评估详情"""
        result = await self.db.execute(
            select(Evaluation).where(Evaluation.id == evaluation_id)
        )
        return result.scalar_one_or_none()
    
    async def get_evaluation_by_interview(self, interview_id: UUID) -> Optional[Evaluation]:
        """根据面试ID获取评估"""
        result = await self.db.execute(
            select(Evaluation).where(Evaluation.interview_id == interview_id)
        )
        return result.scalar_one_or_none()

