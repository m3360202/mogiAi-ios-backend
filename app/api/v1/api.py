"""
API v1 路由配置
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    interviews,
    evaluations,
    corporate,
    speech,
    practice,
    achievements,
    analysis,
    video_analysis,
    realtime_interview,
    segmented_interview,
    stream_interview,
    generate_interview_params,
    google_tts,
    interview_experiences,
    careerjet
)

api_router = APIRouter()

# 认证相关
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# 面试经验
api_router.include_router(interview_experiences.router, prefix="/interview-experiences", tags=["interview-experiences"])

# 面试相关
api_router.include_router(interviews.router, prefix="/interviews", tags=["interviews"])
api_router.include_router(evaluations.router, prefix="/evaluations", tags=["evaluations"])

# 企业模式
api_router.include_router(corporate.router, prefix="/corporate", tags=["corporate"])

# 语音相关
api_router.include_router(speech.router, prefix="/speech", tags=["speech"])

# Google Cloud TTS
api_router.include_router(google_tts.router, prefix="/google-tts", tags=["google-tts", "speech"])

# 练习模式
api_router.include_router(practice.router, prefix="/practice", tags=["practice"])

# 成就系统
api_router.include_router(achievements.router, prefix="/achievements", tags=["achievements"])

# AI分析（LangChain）
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis", "AI"])

# 视频内容分析（七轴评估）
api_router.include_router(video_analysis.router, prefix="/video-analysis", tags=["video-analysis", "AI", "LangChain"])

# Realtime Interview (deprecated)
api_router.include_router(realtime_interview.router, prefix="/interview-realtime", tags=["interview", "realtime"])

# Segmented Interview (new button-based approach)
api_router.include_router(segmented_interview.router, prefix="/interview", tags=["interview", "segmented"])

# Stream Interview (optimized stream-based approach)
api_router.include_router(stream_interview.router, prefix="/interview-stream", tags=["interview", "stream"])

# Generate Interview Params (Deepseek)
api_router.include_router(generate_interview_params.router, prefix="/interview", tags=["interview", "generation"])

# CareerJet API Proxy
api_router.include_router(careerjet.router, prefix="/careerjet", tags=["careerjet", "jobs"]) 
