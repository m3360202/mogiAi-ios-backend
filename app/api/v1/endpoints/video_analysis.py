"""
视频内容分析API端点
提供基于LangChain的六维（实际7维）视频内容分析
"""
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.schemas.video_analysis import (
    VideoAnalysisRequest,
    VideoAnalysisResponse,
    ImprovementRoadmapRequest,
    ImprovementRoadmapResponse,
    BatchAnalysisRequest,
    BatchAnalysisResponse,
)
from app.services.video_analysis_service import video_analysis_service, _LANGCHAIN_IMPORT_ERROR
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.interview_session_manager import session_manager
from app.services.video_segment_analysis_queue import VideoSegmentJob, enqueue as enqueue_video_segment


router = APIRouter()


def _ensure_video_service():
    if video_analysis_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Video analysis service is unavailable. Install LangChain dependencies or disable this endpoint."
            + (f" Original error: {_LANGCHAIN_IMPORT_ERROR}" if _LANGCHAIN_IMPORT_ERROR else "")
        )
    return video_analysis_service


class VideoAnalysisEnqueueRequest(BaseModel):
    session_id: str = Field(..., min_length=6)
    segment_index: int = Field(..., ge=0)
    segment_url: str = Field(..., min_length=10)
    duration: float = Field(0.0, ge=0.0)
    transcript: Optional[str] = None
    language: Optional[str] = None


class VideoAnalysisEnqueueResponse(BaseModel):
    queued: bool
    status: str


@router.post("/analyze", response_model=VideoAnalysisResponse, status_code=status.HTTP_200_OK)
async def analyze_video_content(
    request: VideoAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    分析视频内容，提供七维评价
    
    ## 评估维度（7轴）
    
    ### 语言维度（6个）
    1. **clarity（清晰度/理解しやすさ）**: 句长适当、结构清晰、避免模糊
    2. **evidence（证据/根拠・具体性）**: 使用数字、案例、专有名词
    3. **delivery（表达力/表現力・伝達力）**: 语气坚定、减少犹豫词
    4. **engagement（互动性/やりとり・双方向性）**: 主动提问、双向交流
    5. **politeness（礼貌/礼儀・態度）**: 得体的问候和敬语
    6. **impact（影响力/印象・影響力）**: 突出价值、给人印象深刻
    
    ### 非语言维度（1个）
    7. **nonverbal（非语言表现）**: 音频（音量、抑扬、语速）+ 视觉（微笑、视线、姿态）
    
    ## 评分模式
    - **规则模式**: 基于关键词和语言特征的规则评估
    - **混合模式**: LLM评估（70%）+ 规则评估（30%）的融合
    
    ## 示例请求
    ```json
    {
        "transcript": "您好，我是XX大学的学生，专业是计算机科学...",
        "question": "请做一个自我介绍",
        "scenario": "self_intro",
        "language": "zh",
        "use_llm": true,
        "llm_weight": 0.7,
        "nonverbal": {
            "voice": {
                "volume_db_norm": 0.6,
                "prosody_var": 0.5,
                "speech_rate_norm": 0.5
            },
            "visual": {
                "smile_rate": 0.3,
                "eye_contact_rate": 0.7,
                "posture_stability": 0.8
            }
        }
    }
    ```
    """
    try:
        # 转换nonverbal为字典格式
        nonverbal_dict = None
        if request.nonverbal:
            nonverbal_dict = {
                "voice": request.nonverbal.voice.model_dump() if request.nonverbal.voice else {},
                "visual": request.nonverbal.visual.model_dump() if request.nonverbal.visual else {},
            }
        
        # 执行分析
        service = _ensure_video_service()

        if request.compare_with_previous and request.previous_result_id:
            # TODO: 从数据库获取历史结果
            # 暂时不支持历史对比，需要先创建存储模型
            result = await service.analyze_video_content(
                transcript=request.transcript,
                question=request.question,
                nonverbal=nonverbal_dict,
                scenario=request.scenario,
                language=request.language,
                use_llm=request.use_llm,
                use_anthropic=request.use_anthropic,
                llm_weight=request.llm_weight,
            )
        else:
            result = await service.analyze_video_content(
                transcript=request.transcript,
                question=request.question,
                nonverbal=nonverbal_dict,
                scenario=request.scenario,
                language=request.language,
                use_llm=request.use_llm,
                use_anthropic=request.use_anthropic,
                llm_weight=request.llm_weight,
            )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"视频分析失败 / Video analysis failed: {str(e)}"
        )


@router.post("/enqueue", response_model=VideoAnalysisEnqueueResponse, status_code=status.HTTP_200_OK)
async def enqueue_video_analysis(
    request: VideoAnalysisEnqueueRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Enqueue video segment analysis by Supabase URL (Solution A).
    This endpoint must be lightweight and non-blocking.
    """
    # Best-effort: attach URL into session timeline for later playback/DB persistence
    try:
        await session_manager.update_segment_video_url(
            session_id=request.session_id,
            segment_index=int(request.segment_index),
            video_url=request.segment_url,
        )
    except Exception:
        # session may not exist yet on this instance; analysis can still proceed
        pass

    job = VideoSegmentJob(
        session_id=request.session_id,
        segment_index=int(request.segment_index),
        segment_url=request.segment_url,
        duration=float(request.duration or 0.0),
        transcript=request.transcript or "",
        language=request.language or "ja",
    )
    queued, status_val = await enqueue_video_segment(job)
    return VideoAnalysisEnqueueResponse(queued=queued, status=status_val)


@router.post("/roadmap", response_model=ImprovementRoadmapResponse, status_code=status.HTTP_200_OK)
async def generate_improvement_roadmap(
    request: ImprovementRoadmapRequest,
    current_user: User = Depends(get_current_user),
):
    """
    基于分析结果生成个性化改进路线图
    
    ## 功能说明
    根据视频分析的结果，生成一个详细的2周改进计划，包括：
    - 优先改进的维度及原因
    - 具体练习方法（日常练习 + 模拟场景）
    - 每日30分钟的实践计划
    - 推荐的学习资源
    - 效果检验方法
    
    ## 示例请求
    ```json
    {
        "analysis_result": { ... },
        "user_goal": "希望在面试中更自信地表达自己的优势",
        "language": "zh"
    }
    ```
    """
    try:
        # 将VideoAnalysisResponse转换为字典
        service = _ensure_video_service()
        analysis_dict = request.analysis_result.model_dump(by_alias=True)
        
        roadmap_text = await service.generate_improvement_roadmap(
            analysis_result=analysis_dict,
            user_goal=request.user_goal,
            language=request.language
        )
        
        # 提取需要改进的维度
        scores = analysis_dict["scores"]
        dimensions = ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]
        dim_scores = [(dim, scores[dim]) for dim in dimensions if dim in scores and scores[dim] is not None]
        dim_scores.sort(key=lambda x: x[1])
        
        weak_dimensions = [
            {
                "dimension": dim,
                "score": score,
                "label": analysis_dict["labels"].get(dim, dim)
            }
            for dim, score in dim_scores[:3]
        ]
        
        return ImprovementRoadmapResponse(
            roadmap=roadmap_text,
            weak_dimensions=weak_dimensions
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"改进路线图生成失败 / Roadmap generation failed: {str(e)}"
        )


@router.post("/batch", response_model=BatchAnalysisResponse, status_code=status.HTTP_200_OK)
async def batch_analyze_videos(
    request: BatchAnalysisRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    批量分析多个视频转录
    
    ## 功能说明
    对多个视频转录文本进行批量分析，并计算平均得分。
    适用场景：
    - 分析用户的多次练习记录
    - 对比不同场景下的表现
    - 生成进步趋势报告
    
    ## 示例请求
    ```json
    {
        "transcripts": [
            "第一次练习的转录文本...",
            "第二次练习的转录文本...",
            "第三次练习的转录文本..."
        ],
        "common_settings": {
            "scenario": "self_intro",
            "language": "zh",
            "use_llm": true
        }
    }
    ```
    """
    try:
        results = []
        
        # 准备通用设置
        common_settings = request.common_settings.model_dump() if request.common_settings else {}
        use_llm = common_settings.get("use_llm", True)
        language = common_settings.get("language", "ja")
        scenario = common_settings.get("scenario")
        use_anthropic = common_settings.get("use_anthropic", False)
        llm_weight = common_settings.get("llm_weight", 0.7)
        
        # 批量分析
        service = _ensure_video_service()

        for transcript in request.transcripts:
            result = await service.analyze_video_content(
                transcript=transcript,
                question=common_settings.get("question"),
                nonverbal=None,  # 批量分析暂不支持非语言特征
                scenario=scenario,
                language=language,
                use_llm=use_llm,
                use_anthropic=use_anthropic,
                llm_weight=llm_weight,
            )
            results.append(result)
        
        # 计算平均分
        dimensions = ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]
        average_scores = {}
        
        for dim in dimensions:
            scores = [r["scores"][dim] for r in results if r["scores"].get(dim) is not None]
            if scores:
                average_scores[dim] = round(sum(scores) / len(scores), 2)
            else:
                average_scores[dim] = 0.0
        
        # 计算总分平均
        total_scores = [r["scores"]["total"] for r in results if "total" in r["scores"]]
        if total_scores:
            average_scores["total"] = round(sum(total_scores) / len(total_scores), 2)
        
        return BatchAnalysisResponse(
            results=results,
            average_scores=average_scores,
            total_count=len(results)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量分析失败 / Batch analysis failed: {str(e)}"
        )


@router.get("/dimensions", status_code=status.HTTP_200_OK)
async def get_dimension_info(
    language: str = "ja",
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取评估维度的详细说明
    
    ## 参数
    - language: 语言（ja或zh）
    
    ## 返回
    包含所有维度的详细说明，包括：
    - 维度名称
    - 评分标准
    - 典型问题
    - 改进建议
    """
    from app.services.video_evaluator import AXIS_LABELS
    
    if language == "zh":
        dimensions_info = {
            "clarity": {
                "name": "清晰度/易懂性",
                "description": "评估句子长度适当性、逻辑结构清晰度、模糊词使用情况",
                "scoring_criteria": [
                    "句长控制在40字左右",
                    "使用结构词（首先、其次、最后等）",
                    "避免模糊表达（各种、一些、等等）"
                ],
                "common_issues": ["句子过长", "缺乏逻辑连接词", "大量使用模糊词"],
                "tips": "段落开头使用结构词明确论点，控制单句长度，将模糊词具体化"
            },
            "evidence": {
                "name": "证据/具体性",
                "description": "评估是否使用数字、案例、专有名词支撑观点",
                "scoring_criteria": [
                    "使用具体数字和百分比",
                    "提供真实案例和项目名称",
                    "使用专业术语和专有名词"
                ],
                "common_issues": ["缺少数据支撑", "描述过于抽象", "没有具体案例"],
                "tips": "主张与根据（数字/事例/专有名词）配套呈现"
            },
            "delivery": {
                "name": "表达力/传达力",
                "description": "评估语气坚定程度、犹豫词和口头禅的使用",
                "scoring_criteria": [
                    "使用断定表达（能够、一定、保证）",
                    "减少犹豫词（可能、也许、感觉）",
                    "避免口头禅（呃、嗯、那个）"
                ],
                "common_issues": ["语气不够坚定", "频繁使用犹豫词", "口头禅过多"],
                "tips": "结论前置，增加断定表达，减少犹豫词和口头禅"
            },
            "engagement": {
                "name": "互动性/双向性",
                "description": "评估主动提问、确认对方意图、双向交流的能力",
                "scoring_criteria": [
                    "主动提出问题",
                    "引用对方的话语",
                    "确认理解和意图"
                ],
                "common_issues": ["单向陈述", "缺少提问", "不确认对方意图"],
                "tips": "增加开放式提问，确认对方的意图和优先级"
            },
            "politeness": {
                "name": "礼貌/态度",
                "description": "评估礼貌用语和问候的使用",
                "scoring_criteria": [
                    "适当使用问候语",
                    "使用礼貌请求",
                    "避免过度谦卑"
                ],
                "common_issues": ["缺少礼貌用语", "过度道歉", "语气过于随意"],
                "tips": "开头和结尾整理问候与请求语句，避免过度谦卑"
            },
            "impact": {
                "name": "影响力/记忆点",
                "description": "评估突出价值和结果、给人留下深刻印象的能力",
                "scoring_criteria": [
                    "先说结论和价值",
                    "强调具体成果",
                    "使用印象深刻的表达"
                ],
                "common_issues": ["埋没要点", "结论滞后", "缺少亮点"],
                "tips": "先简洁说明价值和结果，用专有名词和数字增强可信度"
            },
            "nonverbal": {
                "name": "非语言表现",
                "description": "评估音频（音量、抑扬、语速）和视觉（微笑、视线、姿态）特征",
                "scoring_criteria": [
                    "音量适中（0.4-0.7）",
                    "抑扬有变化",
                    "语速接近0.5",
                    "保持适度微笑",
                    "维持目光接触",
                    "姿态稳定自然"
                ],
                "common_issues": ["音量过小或过大", "语速过快或过慢", "缺少表情变化", "姿态不稳"],
                "tips": "保持音量、抑扬、语速的稳定，适度保持微笑、视线和姿态"
            }
        }
    else:  # ja
        dimensions_info = {
            "clarity": {
                "name": "理解のしやすさ",
                "description": "文長の適正、論理構造の明確さ、曖昧語の使用状況を評価",
                "scoring_criteria": [
                    "文長を40字程度に制御",
                    "構造語（まず、次に、最後に等）の使用",
                    "曖昧表現（いろいろ、様々、など）を避ける"
                ],
                "common_issues": ["文が長すぎる", "論理接続詞の欠如", "曖昧語の多用"],
                "tips": "段落頭に構造語を入れて論旨を明示、1文を簡潔に、曖昧語を具体化"
            },
            "evidence": {
                "name": "根拠・具体性",
                "description": "数値、事例、固有名詞を使って主張を裏付けているかを評価",
                "scoring_criteria": [
                    "具体的な数字と割合の使用",
                    "実際の事例とプロジェクト名の提示",
                    "専門用語と固有名詞の使用"
                ],
                "common_issues": ["データの裏付け不足", "抽象的な記述", "具体例がない"],
                "tips": "主張と根拠（数値/事例/固有名詞）をセットで提示"
            },
            "delivery": {
                "name": "表現力・伝達力",
                "description": "語気の断定度、ためらい語やフィラーの使用を評価",
                "scoring_criteria": [
                    "断定表現（できます、必ず、保証します）の使用",
                    "ためらい語（かもしれない、と思う）の削減",
                    "フィラー（えー、あのー）の回避"
                ],
                "common_issues": ["語気が弱い", "ためらい語の頻出", "フィラーが多い"],
                "tips": "結論先出し＋断定表現を増やし、ヘッジ・フィラーは削減"
            },
            "engagement": {
                "name": "やりとり・双方向性",
                "description": "積極的な質問、相手の意図確認、双方向コミュニケーション能力を評価",
                "scoring_criteria": [
                    "積極的に質問する",
                    "相手の発言を引用する",
                    "理解と意図を確認する"
                ],
                "common_issues": ["一方的な説明", "質問がない", "相手の意図を確認しない"],
                "tips": "オープンな問いを増やし、相手の意図・優先度を確認"
            },
            "politeness": {
                "name": "礼儀・態度",
                "description": "丁寧語と挨拶の使用を評価",
                "scoring_criteria": [
                    "適切な挨拶語の使用",
                    "丁寧な依頼表現",
                    "過度なへりくだりを避ける"
                ],
                "common_issues": ["丁寧語の不足", "過度な謝罪", "語気がカジュアルすぎる"],
                "tips": "冒頭/末尾の挨拶と依頼句を整え、過度なへりくだりは避ける"
            },
            "impact": {
                "name": "印象・影響力",
                "description": "価値と結果を強調し、印象に残る表現をする能力を評価",
                "scoring_criteria": [
                    "結論と価値を先に述べる",
                    "具体的な成果を強調",
                    "印象的な表現を使う"
                ],
                "common_issues": ["要点が埋もれる", "結論が遅い", "アピールポイントがない"],
                "tips": "先に価値・結果を端的に示し、固有名/数値で確からしさを補強"
            },
            "nonverbal": {
                "name": "非言語表現（音声＋表情/身体）",
                "description": "音声（音量、抑揚、話速）と視覚（微笑、視線、姿勢）特徴を評価",
                "scoring_criteria": [
                    "音量が適切（0.4-0.7）",
                    "抑揚に変化がある",
                    "話速が0.5前後",
                    "適度な微笑を保つ",
                    "視線接触を維持",
                    "姿勢が安定"
                ],
                "common_issues": ["音量が小さい/大きすぎる", "話速が速い/遅い", "表情変化が少ない", "姿勢が不安定"],
                "tips": "声量・抑揚・話速の安定、微笑・視線・姿勢を適度に保つ"
            }
        }
    
    return {
        "dimensions": dimensions_info,
        "scoring_range": "1-5",
        "total_dimensions": 7,
        "language_dimensions": 6,
        "nonverbal_dimensions": 1,
        "language": language
    }


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, str]:
    """
    健康检查端点
    """
    return {
        "status": "healthy",
        "service": "video_analysis",
        "version": "1.0.0"
    }

