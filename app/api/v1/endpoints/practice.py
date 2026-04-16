"""
练习模式API端点
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta

from app.core.database import get_db
from app.api.dependencies import get_current_user
from app.models.user import User
from app.models.practice import (
    PracticeTopic, 
    UserTopicProgress, 
    PracticeStatistics,
    DetailedEvaluation,
    VideoRecording,
    TopicCategory,
    ProficiencyLevel
)
from app.models.interview import Interview
from app.services.interview_service import InterviewService
from app.schemas.practice import (
    PracticeTopicResponse,
    PracticeTopicListResponse,
    UserTopicProgressResponse,
    UserTopicProgressUpdate,
    PracticeStatisticsResponse,
    DetailedEvaluationResponse,
    DetailedEvaluationCreate,
    VideoRecordingResponse,
    VideoRecordingCreate,
    PracticeResultResponse,
    StartPracticeRequest,
    SubmitPracticeRequest,
)
from app.services.speech_service import SpeechService
from app.services.interview_service import InterviewService
from app.services.interview_params_service import interview_params_service
from fastapi import UploadFile, File
from typing import Dict, Any

router = APIRouter()


# ==================== Practice Topics ====================

@router.get("/topics", response_model=PracticeTopicListResponse)
async def get_practice_topics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取所有练习题目（包含用户进度）"""
    
    # 获取所有active的题目
    result = await db.execute(
        select(PracticeTopic)
        .where(PracticeTopic.is_active == True)
        .order_by(PracticeTopic.sort_order)
    )
    topics = result.scalars().all()
    
    # 获取用户进度
    progress_result = await db.execute(
        select(UserTopicProgress)
        .where(UserTopicProgress.user_id == current_user.id)
    )
    user_progress = {p.topic_id: p for p in progress_result.scalars().all()}
    
    # 分类组织题目
    beginner = []
    advanced = []
    
    for topic in topics:
        topic_dict = {
            "id": topic.id,
            "title": topic.title,
            "category": topic.category.value,
            "icon": topic.icon,
            "dimension": topic.dimension,
            "min_duration": topic.min_duration,
            "max_duration": topic.max_duration,
            "recommended_duration": topic.recommended_duration,
            "description": topic.description,
            "hints": topic.hints,
            "evaluation_criteria": topic.evaluation_criteria,
            "sort_order": topic.sort_order,
            "is_active": topic.is_active,
            "created_at": topic.created_at,
            "proficiency": user_progress[topic.id].proficiency_level.value if topic.id in user_progress else "none"
        }
        
        if topic.category == TopicCategory.BEGINNER:
            beginner.append(PracticeTopicResponse(**topic_dict))
        else:
            advanced.append(PracticeTopicResponse(**topic_dict))
    
    return PracticeTopicListResponse(beginner=beginner, advanced=advanced)


@router.get("/topics/{topic_id}", response_model=PracticeTopicResponse)
async def get_topic(
    topic_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个题目详情"""
    
    result = await db.execute(
        select(PracticeTopic).where(PracticeTopic.id == topic_id)
    )
    topic = result.scalar_one_or_none()
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # 获取用户进度
    progress_result = await db.execute(
        select(UserTopicProgress).where(
            and_(
                UserTopicProgress.user_id == current_user.id,
                UserTopicProgress.topic_id == topic_id
            )
        )
    )
    progress = progress_result.scalar_one_or_none()
    
    return PracticeTopicResponse(
        **topic.__dict__,
        proficiency=progress.proficiency_level.value if progress else "none"
    )


# ==================== User Topic Progress ====================

@router.get("/progress", response_model=List[UserTopicProgressResponse])
async def get_user_progress(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取用户所有题目进度"""
    
    result = await db.execute(
        select(UserTopicProgress)
        .where(UserTopicProgress.user_id == current_user.id)
    )
    progress_list = result.scalars().all()
    
    return [UserTopicProgressResponse.model_validate(p) for p in progress_list]


@router.put("/progress/{topic_id}", response_model=UserTopicProgressResponse)
async def update_topic_progress(
    topic_id: UUID,
    progress_data: UserTopicProgressUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新题目进度（熟练度等级）"""
    
    # 查找或创建进度记录
    result = await db.execute(
        select(UserTopicProgress).where(
            and_(
                UserTopicProgress.user_id == current_user.id,
                UserTopicProgress.topic_id == topic_id
            )
        )
    )
    progress = result.scalar_one_or_none()
    
    if not progress:
        progress = UserTopicProgress(
            user_id=current_user.id,
            topic_id=topic_id,
            proficiency_level=ProficiencyLevel(progress_data.proficiency_level)
        )
        db.add(progress)
    else:
        progress.proficiency_level = ProficiencyLevel(progress_data.proficiency_level)
    
    await db.commit()
    await db.refresh(progress)
    
    return UserTopicProgressResponse.model_validate(progress)


# ==================== Practice Statistics ====================

@router.get("/statistics", response_model=PracticeStatisticsResponse)
async def get_practice_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取练习统计（实时聚合计算）"""
    try:
        # 1. 计算总练习次数 (Completed Interviews)
        # 使用 func.count() 聚合
        count_query = select(func.count(Interview.id)).where(
            and_(
                Interview.user_id == current_user.id,
                Interview.status == "completed"
            )
        )
        total_practices = (await db.execute(count_query)).scalar() or 0
        
        # 2. 计算平均综合得分 (Average Overall Score)
        # 排除 score 为 0 或 null 的情况（避免未评分数据拉低平均分）
        avg_query = select(func.avg(Interview.overall_score)).where(
            and_(
                Interview.user_id == current_user.id,
                Interview.status == "completed",
                Interview.overall_score > 0
            )
        )
        average_score = (await db.execute(avg_query)).scalar() or 0.0
        
        # 3. 计算今日练习次数
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_query = select(func.count(Interview.id)).where(
            and_(
                Interview.user_id == current_user.id,
                Interview.status == "completed",
                Interview.completed_at >= today_start
            )
        )
        practices_today = (await db.execute(today_query)).scalar() or 0
        
        # 4. 计算本周练习次数
        week_start = today_start - timedelta(days=today_start.weekday()) # Assuming Monday is start
        week_query = select(func.count(Interview.id)).where(
            and_(
                Interview.user_id == current_user.id,
                Interview.status == "completed",
                Interview.completed_at >= week_start
            )
        )
        practices_this_week = (await db.execute(week_query)).scalar() or 0
        
        # 5. 计算本月练习次数
        month_start = today_start.replace(day=1)
        month_query = select(func.count(Interview.id)).where(
            and_(
                Interview.user_id == current_user.id,
                Interview.status == "completed",
                Interview.completed_at >= month_start
            )
        )
        practices_this_month = (await db.execute(month_query)).scalar() or 0
        
        # 6. 获取最后一次练习时间
        last_practice_query = select(Interview.completed_at).where(
            and_(
                Interview.user_id == current_user.id,
                Interview.status == "completed"
            )
        ).order_by(Interview.completed_at.desc()).limit(1)
        last_practice_date = (await db.execute(last_practice_query)).scalar_one_or_none()

        # 构造返回对象
        return PracticeStatisticsResponse(
            id=UUID('00000000-0000-0000-0000-000000000000'), 
            user_id=current_user.id,
            total_practices=total_practices,
            average_overall_score=round(float(average_score), 1),
            practices_today=practices_today,
            practices_this_week=practices_this_week,
            practices_this_month=practices_this_month,
            current_streak=0,
            max_streak=0,
            last_practice_date=last_practice_date
        )
    except Exception as e:
        # 如果聚合计算失败（如数据库超时、类型错误等），打印日志并返回空数据，避免前端500报错
        print(f"[PracticeAPI] ❌ Error calculating statistics: {e}")
        import traceback
        traceback.print_exc()
        
        return PracticeStatisticsResponse(
            id=UUID('00000000-0000-0000-0000-000000000000'), 
            user_id=current_user.id,
            total_practices=0,
            average_overall_score=0.0,
            practices_today=0,
            practices_this_week=0,
            practices_this_month=0,
            current_streak=0,
            max_streak=0
        )


# ==================== Practice Session ====================

@router.post("/start", response_model=dict)
async def start_practice(
    request: StartPracticeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """开始练习"""
    
    # 获取题目信息
    topic_result = await db.execute(
        select(PracticeTopic).where(PracticeTopic.id == request.topic_id)
    )
    topic = topic_result.scalar_one_or_none()
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # 创建面试记录
    interview = Interview(
        user_id=current_user.id,
        mode=request.mode,
        topic=topic.title,
        status="recording",
        started_at=datetime.utcnow()
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)
    
    # 生成第一个问题
    interview_service = InterviewService(db)
    first_question = await _generate_first_practice_question(interview)
    
    # 保存第一个问题到对话历史
    await interview_service.add_conversation_message(interview.id, "assistant", first_question)
    
    return {
        "interview_id": interview.id,
        "topic": topic.title,
        "recommended_duration": topic.recommended_duration,
        "started_at": interview.started_at,
        "first_question": first_question
    }


@router.post("/submit", response_model=PracticeResultResponse)
async def submit_practice(
    request: SubmitPracticeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """提交练习并生成评价"""
    
    # 更新面试记录
    interview_result = await db.execute(
        select(Interview).where(
            and_(
                Interview.id == request.interview_id,
                Interview.user_id == current_user.id
            )
        )
    )
    interview = interview_result.scalar_one_or_none()
    
    if not interview:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found"
        )
    
    interview.status = "completed"
    interview.completed_at = datetime.utcnow()
    interview.audio_url = request.audio_url
    interview.transcript = request.transcript
    interview.duration = request.duration
    
    # TODO: 调用AI服务生成评价
    # 这里使用mock数据
    mock_evaluation = _generate_mock_evaluation(interview.id)
    
    detailed_eval = DetailedEvaluation(
        interview_id=interview.id,
        **mock_evaluation
    )
    db.add(detailed_eval)
    
    # 保存视频（如果有）
    if request.video_url:
        video = VideoRecording(
            interview_id=interview.id,
            user_id=current_user.id,
            video_url=request.video_url,
            duration=request.duration,
            status="ready"
        )
        db.add(video)
    
    # 更新统计数据
    await _update_practice_statistics(db, current_user.id, mock_evaluation["overall_score"])
    
    await db.commit()
    await db.refresh(detailed_eval)
    
    # 构建返回数据
    return await _build_practice_result(db, interview, detailed_eval)


# ==================== Practice Interview Session ====================

@router.post("/interview/{interview_id}/audio", response_model=dict)
async def practice_interview_upload_audio(
    interview_id: UUID,
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """练习模式：上传音频并生成基于参数的智能问题"""
    interview_service = InterviewService(db)
    speech_service = SpeechService()
    
    # 验证面试归属
    interview = await interview_service.get_interview(interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    # 验证是否为练习模式
    if interview.mode not in ["basic", "advanced"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is for practice mode only"
        )
    
    # 读取音频数据
    audio_data = await audio_file.read()
    
    # 语音识别
    transcript = await speech_service.transcribe_audio(audio_data)
    
    # 保存音频和文本
    audio_url = await interview_service.save_audio(interview_id, audio_data, audio_file.filename)
    await interview_service.update_transcript(interview_id, transcript)
    
    # 检查面试是否应该结束（在生成问题之前）
    conversation_history = interview.conversation_history or {}
    messages = conversation_history.get("messages", [])
    current_round = len([m for m in messages if m.get("role") == "user"])
    
    # 获取最大轮次
    if interview.mode == "basic":
        max_rounds = interview_params_service.get_basic_rounds()
    else:
        rounds_config = interview_params_service.get_advanced_rounds()
        max_rounds = rounds_config.get("default", 18)
    
    # 如果当前轮次+1已经达到或超过最大轮次，直接结束
    # 因为用户即将回答当前问题，回答后轮次会变成 current_round + 1
    if current_round + 1 >= max_rounds:
        interview_status = "completed"
        interview.status = "completed"
        await db.commit()
        
        # 添加用户回答到对话历史
        await interview_service.add_conversation_message(interview_id, "user", transcript)
        
        # 返回结束消息
        if interview.mode == "basic":
            end_message = "今回の練習面接はこれで終了です。ご参加いただきありがとうございました。結果画面で詳細な評価をご確認ください。"
        else:
            end_message = "今回の練習面接はこれで終了です。最後に、何か質問はありますか？"
        
        await interview_service.add_conversation_message(interview_id, "assistant", end_message)
        
        return {
            "audio_url": audio_url,
            "transcript": transcript,
            "next_question": end_message,
            "interview_status": interview_status,
            "current_round": current_round + 1,
            "max_rounds": max_rounds
        }
    
    # 生成基于练习参数的智能问题
    next_question = await _generate_practice_question(interview, transcript)
    
    # 检查生成的问题是否包含结束信息
    interview_status = "recording"
    if "終了" in next_question:
        interview_status = "completed"
        interview.status = "completed"
        await db.commit()
    
    # 添加对话历史
    await interview_service.add_conversation_message(interview_id, "user", transcript)
    await interview_service.add_conversation_message(interview_id, "assistant", next_question)
    
    return {
        "audio_url": audio_url,
        "transcript": transcript,
        "next_question": next_question,
        "interview_status": interview_status,
        "current_round": current_round + 1,
        "max_rounds": max_rounds
    }

@router.get("/interview/{interview_id}/progress")
async def get_practice_interview_progress(
    interview_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取练习面试进度"""
    interview_service = InterviewService(db)
    
    interview = await interview_service.get_interview(interview_id, current_user.id)
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    
    conversation_history = interview.conversation_history or {}
    messages = conversation_history.get("messages", [])
    current_round = len([m for m in messages if m.get("role") == "user"])
    
    # 获取最大轮次
    if interview.mode == "basic":
        max_rounds = interview_params_service.get_basic_rounds()
    else:
        rounds_config = interview_params_service.get_advanced_rounds()
        max_rounds = rounds_config.get("default", 18)
    
    return {
        "current_round": current_round,
        "max_rounds": max_rounds,
        "progress_percentage": min(100, int((current_round / max_rounds) * 100)),
        "interview_status": interview.status
    }

async def _generate_first_practice_question(interview: Interview) -> str:
    """生成练习模式的第一个问题"""
    mode = interview.mode
    
    if mode == "basic":
        # 基础模式：使用第一个维度
        dimensions = interview_params_service.get_basic_dimensions()
        if not dimensions:
            return "自己紹介をお願いします。"
        
        current_dimension = dimensions[0]
        dimension_key = current_dimension.get("key", "content")
        dimension_name = current_dimension.get("name", "内容")
        
        # 返回第一个问题（针对维度）
        return f"{dimension_name}に関して、あなたの経験を教えてください。"
    else:
        # 高级模式：使用第一个场景
        scenarios = interview_params_service.get_advanced_scenarios()
        if not scenarios:
            return "自己紹介をお願いします。"
        
        current_scenario = scenarios[0]
        scenario_name = current_scenario.get("name", "team_difficulty")
        
        return f"{scenario_name}について、具体的な経験を教えてください。"

async def _generate_practice_question(interview: Interview, user_answer: str) -> str:
    """生成基于练习参数的智能问题"""
    mode = interview.mode
    scenario = interview.scenario or ""
    conversation_history = interview.conversation_history or {}
    messages = conversation_history.get("messages", [])
    current_round = len([m for m in messages if m.get("role") == "user"])
    
    # 获取最大轮次
    if mode == "basic":
        max_rounds = interview_params_service.get_basic_rounds()
    else:
        rounds_config = interview_params_service.get_advanced_rounds()
        max_rounds = rounds_config.get("default", 18)
    
    # 检查是否应该结束面试
    if current_round >= max_rounds:
        if mode == "basic":
            return "今回の練習面接はこれで終了です。ご参加いただきありがとうございました。結果画面で詳細な評価をご確認ください。"
        else:
            return "今回の練習面接はこれで終了です。最後に、何か質問はありますか？"
    
    # 检查用户回答质量（仅在轮次较多时提前结束）
    answer_quality = _assess_answer_quality(user_answer)
    if answer_quality < 30 and current_round > 3 and max_rounds > 5:
        if mode == "basic":
            return "今回の練習面接はこれで終了です。ご参加いただきありがとうございました。結果画面で詳細な評価をご確認ください。"
        else:
            return "今回の練習面接はこれで終了です。最後に、何か質問はありますか？"
    
    # 构建基于JSON配置的提示词
    if mode == "basic":
        # 基础模式：轮流使用维度
        dimensions = interview_params_service.get_basic_dimensions()
        if not dimensions:
            return "次の質問について教えてください。"
        
        current_dimension_config = dimensions[current_round % len(dimensions)]
        dimension_key = current_dimension_config.get("key", "content")
        
        # 使用配置服务构建详细提示词
        system_prompt = interview_params_service.build_dimension_prompt(dimension_key, user_answer)
        
    else:  # advanced mode
        # 高级模式：基于场景
        scenarios = interview_params_service.get_advanced_scenarios()
        if not scenarios:
            return "次の質問について教えてください。"
        
        current_scenario_config = scenarios[min(current_round, len(scenarios) - 1)]
        scenario_key = current_scenario_config.get("key", "team_difficulty")
        
        # 使用配置服务构建详细提示词
        system_prompt = interview_params_service.build_scenario_prompt(scenario_key, user_answer)
    
    # 根据用户回答质量添加提示
    if answer_quality < 50 and current_round > 0:
        system_prompt += "\n\n注意: 応募者の回答が簡潔すぎるか不十分です。もう少し詳しく説明を求める質問をしてください。"
    
    # TODO: 这里应该调用AI服务（如DeepSeek）来根据system_prompt生成问题
    # 暂时返回简化版本
    if mode == "basic":
        dimension_name = current_dimension_config.get("name", "content")
        return f"{dimension_name}について、もう少し詳しく教えてください。具体的な例があれば教えてください。"
    else:
        scenario_name = current_scenario_config.get("name", "team_difficulty")
        return f"{scenario_name}について、もう少し詳しく教えてください。どのように対応しましたか？"

def _assess_answer_quality(answer: str) -> float:
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


# ==================== Video Playback ====================

@router.get("/video/{interview_id}", response_model=VideoRecordingResponse)
async def get_video_recording(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取录像"""
    
    result = await db.execute(
        select(VideoRecording).where(
            and_(
                VideoRecording.interview_id == interview_id,
                VideoRecording.user_id == current_user.id
            )
        )
    )
    video = result.scalar_one_or_none()
    
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found"
        )
    
    return VideoRecordingResponse.model_validate(video)


# ==================== Helper Functions ====================

def _generate_mock_evaluation(interview_id: UUID) -> dict:
    """生成mock评价数据"""
    return {
        "content_score": 85.0,
        "expression_score": 90.0,
        "logic_score": 82.0,
        "attitude_score": 92.0,
        "professionalism_score": 86.0,
        "fluency_score": 89.0,
        "overall_score": 87.3,
        "content_analysis": {
            "performance": "自己紹介では、経歴と強みを簡潔に説明できていました。",
            "issues": "話の構成が時折散漫になり、聞き手が要点を掴みにくい場面がありました。",
            "last_comparison": {
                "improvements": "前回より具体例が20%増え、説得力が向上しました。",
                "weaknesses": "ただし、結論を先に述べる癖がまだ定着していません。"
            },
            "suggestions": "PREP法を意識して練習しましょう。"
        },
        # ... 其他维度的分析
        "comparison_data": {
            "average_scores": {
                "content": 75, "expression": 78, "logic": 72,
                "attitude": 80, "professionalism": 74, "fluency": 76
            },
            "passing_scores": {
                "content": 70, "expression": 70, "logic": 70,
                "attitude": 70, "professionalism": 70, "fluency": 70
            }
        }
    }


async def _update_practice_statistics(db: AsyncSession, user_id: UUID, score: float):
    """更新练习统计"""
    result = await db.execute(
        select(PracticeStatistics).where(PracticeStatistics.user_id == user_id)
    )
    stats = result.scalar_one_or_none()
    
    if not stats:
        stats = PracticeStatistics(user_id=user_id)
        db.add(stats)
    
    today = datetime.utcnow().date()
    stats.total_practices += 1
    
    # 更新今日练习次数
    if stats.last_practice_date and stats.last_practice_date.date() == today:
        stats.practices_today += 1
    else:
        stats.practices_today = 1
    
    # 更新本周练习次数（简化实现）
    stats.practices_this_week += 1
    
    # 更新平均分
    if stats.average_overall_score:
        stats.average_overall_score = (
            (stats.average_overall_score * (stats.total_practices - 1) + score) /
            stats.total_practices
        )
    else:
        stats.average_overall_score = score
    
    stats.last_practice_date = datetime.utcnow()


async def _build_practice_result(
    db: AsyncSession,
    interview: Interview,
    evaluation: DetailedEvaluation
) -> PracticeResultResponse:
    """构建练习结果响应"""
    
    # 获取统计数据
    stats_result = await db.execute(
        select(PracticeStatistics).where(PracticeStatistics.user_id == interview.user_id)
    )
    stats = stats_result.scalar_one_or_none()
    
    # 获取视频URL
    video_result = await db.execute(
        select(VideoRecording).where(VideoRecording.interview_id == interview.id)
    )
    video = video_result.scalar_one_or_none()
    
    return PracticeResultResponse(
        interview_id=interview.id,
        topic=interview.topic,
        duration=interview.duration,
        overall_score=evaluation.overall_score,
        scores={
            "content": evaluation.content_score,
            "expression": evaluation.expression_score,
            "logic": evaluation.logic_score,
            "attitude": evaluation.attitude_score,
            "professionalism": evaluation.professionalism_score,
            "fluency": evaluation.fluency_score,
            "overall": evaluation.overall_score
        },
        detailed_analysis={
            "content": evaluation.content_analysis,
            "expression": evaluation.expression_analysis,
            "logic": evaluation.logic_analysis,
            "attitude": evaluation.attitude_analysis,
            "professionalism": evaluation.professionalism_analysis,
            "fluency": evaluation.fluency_analysis
        },
        average_scores=evaluation.comparison_data.get("average_scores", {}),
        passing_scores=evaluation.comparison_data.get("passing_scores", {}),
        practice_stats={
            "today": stats.practices_today if stats else 0,
            "this_week": stats.practices_this_week if stats else 0,
            "total": stats.total_practices if stats else 0
        },
        video_url=video.video_url if video else None,
        created_at=evaluation.created_at
    )

