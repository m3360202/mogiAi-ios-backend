"""
评估相关API端点
"""
from uuid import UUID
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.schemas.evaluation import EvaluationResponse, EvaluationRequest, InterviewEvalRequest, InterviewEvalResponse
from app.services.evaluation_service import EvaluationService
from app.services.interview_service import InterviewService
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.evaluation.public import get_evaluation_api, EvaluationAPI
from app.services.evaluation.business.entities import EvaluationRecord
from app.services.evaluation.services.adapters import parse_eval_request, pack_eval_response
from app.services.fast_interview_evaluator import get_fast_evaluator, FastEvaluationResult

router = APIRouter()


# 快速评估请求/响应模型
class FastEvalRequest(BaseModel):
    """快速评估请求"""
    interview: List[Dict[str, Any]]  # 面试对话数据
    position: str = "候选人"  # 应聘职位（可选）


class FastEvalResponse(BaseModel):
    """快速评估响应"""
    overall_score: int
    overall_brief: str
    dimensions: Dict[str, Dict[str, Any]]


@router.post("/fast-eval", response_model=FastEvalResponse)
async def fast_evaluate_interview(
    request: FastEvalRequest,
    current_user: User = Depends(get_current_user),
):
    """
    快速评估面试表现（推荐使用）
    
    **特点**：
    - ⚡ 只调用一次LLM，速度快（3-8秒）
    - 📊 返回6个维度的评分和评语
    - 💰 成本低，适合实时评估
    
    **请求示例**：
    ```json
    {
      "interview": [
        {"role": "system", "content": "请介绍一下你自己", "timestamp": 1234567890},
        {"role": "user", "content": "我叫张三，有3年开发经验...", "timestamp": 1234567895}
      ],
      "position": "后端开发工程师"
    }
    ```
    
    **返回示例**：
    ```json
    {
      "overall_score": 4,
      "overall_brief": "候选人表现良好，回答完整清晰",
      "dimensions": {
        "content": {"score": 4, "brief": "回答完整充分", "description": "..."},
        "logic": {"score": 4, "brief": "逻辑清晰", "description": "..."},
        ...
      }
    }
    ```
    """
    try:
        print(f"[API] 🚀 Fast evaluation requested by user {current_user.id}")
        
        # 获取快速评估器
        evaluator = get_fast_evaluator()
        
        # 执行评估
        result: FastEvaluationResult = await evaluator.evaluate(
            interview_data=request.interview,
            position=request.position
        )
        
        # 转换为响应格式（v3格式）
        response = FastEvalResponse(
            overall_score=int(result.overall_score),  # 转换为int以保持兼容
            overall_brief=result.overall_brief,
            dimensions={
                key: {
                    "score": dim.score,
                    "brief_feedback": dim.brief_feedback,
                    "detailed_feedback": dim.detailed_feedback
                }
                for key, dim in result.dimensions.items()
            }
        )
        
        print(f"[API] ✅ Fast evaluation completed: {result.overall_score}/5")
        return response
        
    except Exception as e:
        print(f"[API] ❌ Fast evaluation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fast evaluation failed: {str(e)}"
        )


@router.post("", response_model=EvaluationResponse, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    evaluation_request: EvaluationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建面试评估"""
    interview_service = InterviewService(db)
    evaluation_service = EvaluationService(db)
    
    # 验证面试归属
    interview = await interview_service.get_interview(evaluation_request.interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    if interview.status != "completed":
        raise HTTPException(status_code=400, detail="Interview must be completed before evaluation")
    
    # 执行评估
    evaluation = await evaluation_service.evaluate_interview(interview)
    
    return evaluation

# Lazy singleton EvaluationAPI instance (avoid import-time heavy init / missing asset crashes)
_evaluation_api_instance: Optional[EvaluationAPI] = None


def _get_evaluation_api() -> EvaluationAPI:
    global _evaluation_api_instance
    if _evaluation_api_instance is None:
        _evaluation_api_instance = get_evaluation_api()
    return _evaluation_api_instance

@router.post("/eval", response_model=InterviewEvalResponse)
async def evaluate_interview_dialog(
    request: InterviewEvalRequest,
    current_user: User = Depends(get_current_user),
):  
    try:
        # parse request data
        raw_dialog_info = parse_eval_request(request)
        
        # call the evaluation API
        evaluation_api = _get_evaluation_api()
        evaluation: EvaluationRecord = await evaluation_api.evaluate(raw_dialog_info)

        # pack response
        return pack_eval_response(evaluation, language=request.language)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Evaluation failed: {str(e)}"
        )

@router.get("/interview/{interview_id}", response_model=EvaluationResponse)
async def get_evaluation_by_interview(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """根据面试ID获取评估结果"""
    interview_service = InterviewService(db)
    evaluation_service = EvaluationService(db)
    
    # 验证面试归属
    interview = await interview_service.get_interview(interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    # 获取评估结果
    evaluation = await evaluation_service.get_evaluation_by_interview(interview_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    return evaluation


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(
    evaluation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取评估详情"""
    evaluation_service = EvaluationService(db)
    evaluation = await evaluation_service.get_evaluation(evaluation_id)
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    # 验证所属权限
    interview_service = InterviewService(db)
    interview = await interview_service.get_interview(evaluation.interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return evaluation

