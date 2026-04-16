"""
面试AI分析 API端点
使用LangChain进行六维分析
"""
from typing import Optional, TYPE_CHECKING
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.storage_service import storage_service

if TYPE_CHECKING:  # pragma: no cover
    from app.services.langchain_service import SixDimensionAnalysis, TranscriptAnalysis


router = APIRouter()


# ========= Internal Helpers =========

def _get_langchain_components():
    try:
        from app.services import langchain_service as lc_module
        service = getattr(lc_module, "langchain_service", None)
        if service is None:
            error = getattr(lc_module, "LANGCHAIN_IMPORT_ERROR", None)
            raise RuntimeError(
                "LangChain analysis service is unavailable. Install optional dependencies "
                "or disable the analysis endpoints."
                + (f" Original error: {error}" if error else "")
            )
        return service, lc_module.SixDimensionAnalysis, lc_module.TranscriptAnalysis
    except Exception as exc:  # pragma: no cover - runtime dependency issues
        raise RuntimeError(
            "LangChain analysis service is unavailable. Please install the required "
            f"dependencies or disable the analysis endpoint. Original error: {exc}"
        ) from exc


# ========== Request/Response Schemas ==========

class AnalyzeInterviewRequest(BaseModel):
    """面试分析请求"""
    transcript: str = Field(..., description="面试转录文本（日语）")
    question: str = Field(..., description="面试问题")
    interview_id: Optional[str] = Field(None, description="面试ID")
    audio_features: Optional[dict] = Field(None, description="音频特征数据")
    use_anthropic: bool = Field(False, description="是否使用Anthropic模型")


class AnalyzeTranscriptRequest(BaseModel):
    """转录文本基础分析请求"""
    transcript: str = Field(..., description="转录文本（日语）")


class ImprovementPlanRequest(BaseModel):
    """改进计划请求"""
    analysis_result: dict = Field(..., description="六维分析结果")
    user_goal: Optional[str] = Field(None, description="用户目标")


class UploadAudioRequest(BaseModel):
    """音频上传响应"""
    success: bool
    url: Optional[str] = None
    path: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None


class AnalysisResponse(BaseModel):
    """分析响应"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


# ========== API Endpoints ==========

@router.post("/interview/six-dimensions", response_model=AnalysisResponse)
async def analyze_interview_six_dimensions(
    request: AnalyzeInterviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    分析面试的六维表现
    
    - **transcript**: 面试转录文本（日语）
    - **question**: 面试问题
    - **interview_id**: 面试ID（可选）
    - **audio_features**: 音频特征（可选）
    - **use_anthropic**: 是否使用Anthropic模型
    
    Returns:
        六维分析结果：内容、表现力、逻辑性、态度、专业性、流畅度
    """
    try:
        langchain_service, _, _ = _get_langchain_components()
        # 调用LangChain服务进行分析
        analysis = await langchain_service.analyze_interview_six_dimensions(
            transcript=request.transcript,
            question=request.question,
            audio_features=request.audio_features,
            use_anthropic=request.use_anthropic
        )
        
        # 将Pydantic模型转为字典
        result = analysis.model_dump()
        
        return AnalysisResponse(
            success=True,
            data=result
        )
        
    except RuntimeError as exc:
        return AnalysisResponse(success=False, error=str(exc))
    except Exception as e:
        return AnalysisResponse(
            success=False,
            error=str(e)
        )


@router.post("/transcript/basic", response_model=AnalysisResponse)
async def analyze_transcript_basic(
    request: AnalyzeTranscriptRequest,
    current_user: User = Depends(get_current_user),
):
    """
    基础转录文本分析
    
    - **transcript**: 转录文本（日语）
    
    Returns:
        基础分析结果：字数、填充词数量、平均句子长度、复杂度、清晰度
    """
    try:
        langchain_service, _, TranscriptAnalysis = _get_langchain_components()
        analysis = await langchain_service.analyze_transcript_basic(
            transcript=request.transcript
        )
        
        return AnalysisResponse(
            success=True,
            data=analysis.model_dump()
        )
        
    except RuntimeError as exc:
        return AnalysisResponse(success=False, error=str(exc))
    except Exception as e:
        return AnalysisResponse(
            success=False,
            error=str(e)
        )


@router.post("/improvement-plan", response_model=AnalysisResponse)
async def generate_improvement_plan(
    request: ImprovementPlanRequest,
    current_user: User = Depends(get_current_user),
):
    """
    根据六维分析结果生成改进计划
    
    - **analysis_result**: 六维分析结果（dict）
    - **user_goal**: 用户目标（可选）
    
    Returns:
        个性化改进计划文本
    """
    try:
        langchain_service, SixDimensionAnalysis, _ = _get_langchain_components()
        # 将dict转回SixDimensionAnalysis对象
        analysis = SixDimensionAnalysis(**request.analysis_result)
        
        plan = await langchain_service.generate_improvement_plan(
            analysis=analysis,
            user_goal=request.user_goal
        )
        
        return AnalysisResponse(
            success=True,
            data={"improvement_plan": plan}
        )
        
    except RuntimeError as exc:
        return AnalysisResponse(success=False, error=str(exc))
    except Exception as e:
        return AnalysisResponse(
            success=False,
            error=str(e)
        )


@router.post("/upload-audio", response_model=UploadAudioRequest)
async def upload_audio_file(
    file: UploadFile = File(...),
    interview_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    上传音频文件到Supabase Storage
    
    - **file**: 音频文件（webm, mp3, wav等）
    - **interview_id**: 面试ID（可选）
    
    Returns:
        上传结果，包含文件URL和路径
    """
    try:
        # 验证文件类型
        allowed_types = ['audio/webm', 'audio/mp3', 'audio/wav', 'audio/mpeg']
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型: {file.content_type}"
            )
        
        # 获取文件扩展名
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'webm'
        
        # 读取文件内容
        file_content = await file.read()
        
        # 上传到Supabase Storage
        from io import BytesIO
        result = await storage_service.upload_audio(
            file=BytesIO(file_content),
            user_id=str(current_user.id),
            interview_id=interview_id,
            file_extension=file_extension
        )
        
        return UploadAudioRequest(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        return UploadAudioRequest(
            success=False,
            error=str(e)
        )


@router.post("/upload-video", response_model=UploadAudioRequest)
async def upload_video_file(
    file: UploadFile = File(...),
    interview_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
):
    """
    上传视频文件到Supabase Storage
    
    - **file**: 视频文件（mp4, webm等）
    - **interview_id**: 面试ID（可选）
    
    Returns:
        上传结果，包含文件URL和路径
    """
    try:
        # 验证文件类型
        allowed_types = ['video/mp4', 'video/webm', 'video/quicktime']
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型: {file.content_type}"
            )
        
        # 获取文件扩展名
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'mp4'
        
        # 读取文件内容
        file_content = await file.read()
        
        # 上传到Supabase Storage
        from io import BytesIO
        result = await storage_service.upload_video(
            file=BytesIO(file_content),
            user_id=str(current_user.id),
            interview_id=interview_id,
            file_extension=file_extension
        )
        
        return UploadAudioRequest(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        return UploadAudioRequest(
            success=False,
            error=str(e)
        )


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "AI Analysis API",
        "features": [
            "六维面试分析",
            "转录文本分析",
            "改进计划生成",
            "音频/视频上传"
        ]
    }

