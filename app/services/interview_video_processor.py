"""
Interview Video Processor Service
处理面试视频的异步分析（使用LLM分析表情和语气）
"""
import asyncio
import os
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from app.services.video_nonverbal_analyzer import video_nonverbal_analyzer
from app.services.langchain_service import langchain_service
from app.services.interview_session_manager import session_manager
from app.services.interview_evaluation_orchestrator import fallback_full_evaluation, get_previous_scores_for_user
from app.services.unified_evaluation_service import UnifiedEvaluationService


def log(message: str) -> None:
    """打印日志"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")


async def process_video_async(
    session_id: str,
    video_path: str,
    user_text: str,
    duration: float,
    segment_index: int,
    realtime_hint: Optional[Dict[str, Any]] = None,
    language: str = "ja",
) -> None:
    """
    异步处理视频：使用LLM分析表情和语气（不上传）
    1. 视频分析获取视觉信息（表情、眼神等）
    2. 使用LangChain LLM分析语气（基于文本和音频特征）
    3. 结合两者生成完整的非语言分析
    
    Args:
        session_id: 会话ID
        video_path: 视频文件路径
        user_text: 用户回答文本
        duration: 视频时长
        segment_index: 片段索引
        realtime_hint: 实时非语言特征提示（包含音频特征）
        language: 语言代码 (ja/en/zh)
    """
    try:
        log(f"[VideoProcessor] 🎥 Background: Analyzing video segment {segment_index} (lang: {language})...")
        
        # ⚠️ 检测用户未回答的情况，跳过分析，提供标准格式的"未回答"数据
        if user_text == "ユーザーはこの質問に回答していません":
            log(f"[VideoProcessor] ℹ️ User did not answer, providing default non-answer analysis")
            
            # 提供标准格式的未回答分析数据
            no_answer_analysis = {
                "voice": {
                    "speed": "回答なし",
                    "tone": "回答がありませんでした",
                    "volume": "N/A",
                    "pronunciation": "N/A",
                    "pause": "N/A",
                    "summary": "応募者はこの質問に回答しませんでした。",
                },
                "visual": {
                    "eye_contact": "評価不可",
                    "facial_expression": "回答がないため評価できません",
                    "body_posture": "N/A",
                    "appearance": "N/A",
                },
                "overall_impression": "応募者は回答を控えました。",
            }
            
            # 更新 timeline 中的 nonverbal 数据
            merged_nonverbal = {
                "analysis": no_answer_analysis,
            }
            if realtime_hint:
                merged_nonverbal.setdefault("realtime", realtime_hint)
            
            await session_manager.update_segment_nonverbal(
                session_id=session_id,
                segment_index=segment_index,
                nonverbal_data=merged_nonverbal,
            )
            log(f"[VideoProcessor] ✓ Timeline updated with no-answer analysis")
            
            # 清理临时视频文件
            if video_path and os.path.exists(video_path):
                try:
                    os.unlink(video_path)
                    log(f"[VideoProcessor] ✓ Cleaned up temp video (no-answer case)")
                except Exception as cleanup_err:
                    log(f"[VideoProcessor] ✗ Cleanup error: {cleanup_err}")
            
            return  # 直接返回，不进行实际分析
        
        # ⚡ 使用统一评估服务：一次性完成视觉分析、语音分析和语气分析
        # 这样可以减少LLM调用次数（从3次减少到1次）
        use_unified_evaluation = True  # 可以通过配置控制是否启用
        
        video_analysis = None
        llm_analysis = None
        
        if use_unified_evaluation:
            try:
                log(f"[VideoProcessor] 🚀 Using unified evaluation service (single LLM call)...")
                
                # 1. 提取视频帧
                if video_nonverbal_analyzer is None:
                    log(f"[VideoProcessor] ⚠️ Video analyzer not available, skipping unified evaluation")
                    use_unified_evaluation = False
                else:
                    # 使用 video_nonverbal_analyzer 的方法提取和编码帧
                    frames = await asyncio.to_thread(
                        video_nonverbal_analyzer._extract_key_frames,
                        video_path,
                        video_nonverbal_analyzer.max_frames,
                    )
                    
                    if not frames:
                        log(f"[VideoProcessor] ⚠️ No frames extracted, falling back to legacy method")
                        use_unified_evaluation = False
                    else:
                        encoded_results = await asyncio.to_thread(
                            video_nonverbal_analyzer._encode_frames,
                            frames
                        )
                        frame_images = [item["base64"] for item in encoded_results]
                        
                        if not frame_images:
                            log(f"[VideoProcessor] ⚠️ Failed to encode frames, falling back to legacy method")
                            use_unified_evaluation = False
                        else:
                            # 2. 获取当前问题
                            session = await session_manager.get_session(session_id)
                            timeline = await session_manager.get_timeline_doc(session_id)
                            current_question = ""
                            for msg in reversed(timeline.get("conversation", [])):
                                if msg.get("role") == "system":
                                    current_question = msg.get("content", "")
                                    break
                            
                            # 3. 提取音频特征
                            audio_features = None
                            # 优先从前端获取
                            if realtime_hint:
                                audio_features = {
                                    "speaking_rate": realtime_hint.get("speaking_rate"),
                                    "average_volume": realtime_hint.get("average_volume"),
                                    "pitch_variation": realtime_hint.get("pitch_variation"),
                                }
                                audio_features = {k: v for k, v in audio_features.items() if v is not None}
                            
                            # 后端补充计算语速 (CPM/WPM)
                            if not audio_features:
                                audio_features = {}
                            
                            if not audio_features.get("speaking_rate") and user_text and duration > 0:
                                # 简单计算逻辑：中文/日文按字符数，其他按单词数
                                # 假设 user_text 是ASR结果
                                if language in ["zh", "ja"]:
                                    count = len(user_text.replace(" ", "").replace("\n", ""))
                                    cpm = int(count / (duration / 60))
                                    audio_features["speaking_rate"] = f"{cpm} CPM (Characters Per Minute)"
                                    # 将数值也放入以便 LLM 理解
                                    audio_features["speaking_rate_numeric"] = cpm
                                else:
                                    count = len(user_text.split())
                                    wpm = int(count / (duration / 60))
                                    audio_features["speaking_rate"] = f"{wpm} WPM (Words Per Minute)"
                                    audio_features["speaking_rate_numeric"] = wpm
                                log(f"[VideoProcessor] 📊 Calculated speaking speed: {audio_features['speaking_rate']}")

                            if not audio_features:
                                audio_features = None
                            
                            # 4. 获取上一次测试得分（用于反馈对比）
                            previous_scores = None
                            try:
                                if session and session.metadata:
                                    user_id_str = session.metadata.get("user_id")
                                    if user_id_str:
                                        try:
                                            user_id = UUID(user_id_str)
                                            previous_scores = await get_previous_scores_for_user(
                                                user_id=user_id,
                                                current_time=datetime.utcnow()
                                            )
                                            if previous_scores:
                                                log(f"[VideoProcessor] ✓ Loaded previous scores: {list(previous_scores.keys())}")
                                        except Exception as uid_err:
                                            log(f"[VideoProcessor] ⚠️ Failed to get user_id: {uid_err}")
                            except Exception as ps_err:
                                log(f"[VideoProcessor] ⚠️ Failed to get previous scores: {ps_err}")
                            
                            # 5. 调用统一评估服务
                            unified_service = UnifiedEvaluationService()
                            unified_result = await unified_service.evaluate_unified(
                                frame_images=frame_images,
                                transcript=user_text,
                                question=current_question or "",
                                duration=duration,
                                audio_features=audio_features,
                                previous_scores=previous_scores,
                                language=language
                            )
                            
                            log(f"[VideoProcessor] ✅ Unified evaluation completed")
                            
                            # 6. 转换统一评估结果为现有数据结构
                            # 视觉分析
                            if "visual_analysis" in unified_result:
                                visual_data = unified_result["visual_analysis"]
                                video_analysis = {
                                    "visual": {
                                        "face_visibility": visual_data.get("face_visibility", {}).get("description", ""),
                                        "eye_contact": visual_data.get("eye_contact", {}).get("description", ""),
                                        "facial_expression": visual_data.get("facial_expression", {}).get("description", ""),
                                        "body_posture": visual_data.get("body_posture", {}).get("description", ""),
                                        "appearance": visual_data.get("appearance", {}).get("description", ""),
                                        "summary": visual_data.get("summary", ""),
                                        "face_visibility_score_label": visual_data.get("face_visibility", {}).get("score_label", "Fair"),
                                        "eye_contact_score_label": visual_data.get("eye_contact", {}).get("score_label", "Fair"),
                                        "facial_expression_score_label": visual_data.get("facial_expression", {}).get("score_label", "Fair"),
                                        "body_posture_score_label": visual_data.get("body_posture", {}).get("score_label", "Fair"),
                                        "appearance_score_label": visual_data.get("appearance", {}).get("score_label", "Fair"),
                                        "metadata": visual_data.get("face_visibility", {}).get("metadata", {})
                                    },
                                    "overall_impression": unified_result.get("overall_impression", "")
                                }
                            
                            # 语音分析
                            if "voice_analysis" in unified_result:
                                voice_data = unified_result["voice_analysis"]
                                video_analysis = video_analysis or {}
                                video_analysis["voice"] = {
                                    "speed": voice_data.get("speed", {}).get("description", ""),
                                    "tone": voice_data.get("tone", {}).get("description", ""),
                                    "volume": voice_data.get("volume", {}).get("description", ""),
                                    "pronunciation": voice_data.get("pronunciation", {}).get("description", ""),
                                    "pause": voice_data.get("pause", {}).get("description", ""),
                                    "summary": voice_data.get("summary", ""),
                                    "speed_score_label": voice_data.get("speed", {}).get("score_label", "Fair"),
                                    "tone_score_label": voice_data.get("tone", {}).get("score_label", "Fair"),
                                    "volume_score_label": voice_data.get("volume", {}).get("score_label", "Fair"),
                                    "pronunciation_score_label": voice_data.get("pronunciation", {}).get("score_label", "Fair"),
                                    "pause_score_label": voice_data.get("pause", {}).get("score_label", "Fair"),
                                }
                            
                            # 语气分析
                            if "tone_analysis" in unified_result:
                                tone_data = unified_result["tone_analysis"]
                                llm_analysis = {
                                    "tone": tone_data.get("emotional_expression", {}).get("description", ""),
                                    "tone_score": tone_data.get("emotional_expression", {}).get("score", 50),
                                    "tone_score_label": "Good" if tone_data.get("emotional_expression", {}).get("score", 50) >= 70 else ("Fair" if tone_data.get("emotional_expression", {}).get("score", 50) >= 50 else "Poor"),
                                    "engagement_score": tone_data.get("engagement_level", {}).get("score", 50),
                                }
                                log(f"[VideoProcessor] ✓ Tone analysis from unified evaluation (score: {llm_analysis.get('tone_score', 50)})")
                            
                            # 7. 保存统一评估生成的反馈，供后续 evaluate_section_async 复用
                            if "feedback" in unified_result:
                                feedback_data = unified_result["feedback"]
                                
                                # ⚡ 将计算出的语速数值追加到 VERBAL_PERFORMANCE 的反馈中
                                if audio_features and audio_features.get("speaking_rate"):
                                    cpm_info = audio_features["speaking_rate"]
                                    # 处理多语言标签
                                    label = "📊 平均話速："
                                    if language.startswith("zh"):
                                        label = "📊 平均语速："
                                    elif language.startswith("en"):
                                        label = "📊 Average Speaking Rate: "
                                    
                                    # 查找 verbal_performance 的详细反馈字段
                                    verbal_fb = feedback_data.get("verbal_performance", {})
                                    if isinstance(verbal_fb, dict):
                                        original_detail = verbal_fb.get("detailed_feedback", "")
                                        # 追加到最后
                                        if original_detail:
                                            verbal_fb["detailed_feedback"] = f"{original_detail}\n\n{label}{cpm_info}"
                                        else:
                                            verbal_fb["detailed_feedback"] = f"{label}{cpm_info}"
                                        log(f"[VideoProcessor] 📊 Appended speaking rate to verbal feedback: {cpm_info}")

                                log(f"[VideoProcessor] 💾 Saving unified feedback to metadata for segment {segment_index}")
                                await session_manager.update_unified_feedback(
                                    session_id=session_id,
                                    segment_index=segment_index,
                                    feedback_data=feedback_data
                                )
                            else:
                                log(f"[VideoProcessor] ⚠️ No feedback found in unified result")
                            
                            # 注意：统一评估服务返回的 feedback 部分暂不在此处使用
                            # 反馈生成仍在评估阶段（evaluate_section_async）进行
                            # 未来可以进一步优化，直接使用统一评估的反馈结果
                            
            except Exception as e:
                log(f"[VideoProcessor] ⚠️ Unified evaluation failed, falling back to legacy method: {e}")
                import traceback
                traceback.print_exc()
                use_unified_evaluation = False
        
        # 回退到旧方法（如果统一评估失败或未启用）
        if not use_unified_evaluation:
            log(f"[VideoProcessor] 🔄 Using legacy evaluation method (multiple LLM calls)...")
            
            # 1. 视频分析获取视觉信息（表情、眼神、姿势等）
            if video_nonverbal_analyzer is not None:
                log(f"[VideoProcessor] 🎬 Starting video analysis...")
                try:
                    video_analysis = await video_nonverbal_analyzer.analyze_video(
                        video_path=video_path,
                        transcript=user_text,
                        duration=duration,
                        language=language,
                    )
                    log(f"[VideoProcessor] ✓ Video visual analysis completed")
                except Exception as e:
                    log(f"[VideoProcessor] ⚠️  Video analysis failed: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 2. 使用LangChain LLM分析语气（基于文本和音频特征）
            if langchain_service is not None:
                try:
                    # 获取当前问题
                    session = await session_manager.get_session(session_id)
                    timeline = await session_manager.get_timeline_doc(session_id)
                    current_question = ""
                    for msg in reversed(timeline.get("conversation", [])):
                        if msg.get("role") == "system":
                            current_question = msg.get("content", "")
                            break
                    
                    # 提取音频特征（从realtime_hint）
                    audio_features = None
                    if realtime_hint:
                        audio_features = {
                            "speaking_rate": realtime_hint.get("speaking_rate"),
                            "average_volume": realtime_hint.get("average_volume"),
                            "pitch_variation": realtime_hint.get("pitch_variation"),
                        }
                        # 移除None值
                        audio_features = {k: v for k, v in audio_features.items() if v is not None}
                        if not audio_features:
                            audio_features = None
                    
                    # 使用LangChain分析语气（expression维度包含语气分析）
                    six_dim_analysis = await langchain_service.analyze_interview_six_dimensions(
                        transcript=user_text,
                        question=current_question or "面接質問",
                        audio_features=audio_features,
                    )
                    
                    # 提取语气相关信息
                    expression_dim = six_dim_analysis.expression
                    llm_analysis = {
                        "tone": expression_dim.performance,  # 语气表现
                        "tone_issues": expression_dim.issues,  # 语气问题
                        "tone_suggestions": expression_dim.suggestions,  # 语气建议
                        "tone_score": expression_dim.score,  # 语气评分
                        "tone_score_label": "Good" if expression_dim.score >= 70 else ("Fair" if expression_dim.score >= 50 else "Poor"),
                    }
                    log(f"[VideoProcessor] ✓ LLM tone analysis completed (score: {expression_dim.score})")
                    
                    # 如果有视频分析结果，用LLM进一步分析表情
                    if video_analysis and "visual" in video_analysis:
                        visual_info = video_analysis["visual"]
                        facial_expression_raw = visual_info.get("facial_expression", "")
                        
                        # 使用LLM分析表情（基于视频分析的原始描述）
                        if facial_expression_raw:
                            try:
                                from langchain_core.messages import HumanMessage
                                facial_prompt = f"""
**⚠️ 使用目的の明確化**：
これは**面接練習アプリケーション**の一部です。応募者が自発的に利用しているスキル向上サービスであり、完全に合法的で倫理的な教育目的の使用です。目的は面接スキル向上のためのフィードバック提供であり、個人識別や監視目的ではありません。

以下の面接動画の表情分析結果を、より詳細で専門的な評価に変換してください。

【動画分析の原始結果】
表情: {facial_expression_raw}
視線: {visual_info.get("eye_contact", "")}
姿勢: {visual_info.get("body_posture", "")}

【応募者の回答内容】
{user_text[:200]}

【タスク】
上記の動画分析結果に基づいて、表情（facial_expression）をより詳細に分析し、以下の形式で返してください：
- 表情の状態（自然/緊張/リラックスなど）
- 具体的な観察点
- 改善提案

JSON形式で返してください：
{{"facial_expression": "詳細な表情分析", "facial_expression_score_label": "Good/Fair/Poor"}}
"""
                                response = await langchain_service.default_model.ainvoke([HumanMessage(content=facial_prompt)])
                                import json
                                import re
                                response_text = response.content.strip()
                                
                                # 提取JSON
                                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
                                if json_match:
                                    facial_llm_result = json.loads(json_match.group(0))
                                    llm_analysis["facial_expression"] = facial_llm_result.get("facial_expression", facial_expression_raw)
                                    llm_analysis["facial_expression_score_label"] = facial_llm_result.get("facial_expression_score_label", "Fair")
                                    log(f"[VideoProcessor] ✓ LLM facial expression analysis completed")
                            except Exception as e:
                                log(f"[VideoProcessor] ⚠️  LLM facial expression analysis failed: {e}")
                except Exception as e:
                    log(f"[VideoProcessor] ⚠️  LLM analysis failed: {e}")
                    import traceback
                    traceback.print_exc()
        
        # 3. 合并分析结果
        merged_analysis = {}
        
        # 合并视频分析结果（视觉部分：表情、眼神等）
        if video_analysis:
            merged_analysis["visual"] = video_analysis.get("visual", {}).copy()
            merged_analysis["overall_impression"] = video_analysis.get("overall_impression", "")
            
            # 如果LLM分析了表情，用LLM的结果覆盖
            if llm_analysis and "facial_expression" in llm_analysis:
                merged_analysis["visual"]["facial_expression"] = llm_analysis["facial_expression"]
                if "facial_expression_score_label" in llm_analysis:
                    merged_analysis["visual"]["facial_expression_score_label"] = llm_analysis["facial_expression_score_label"]
        
        # 合并LLM分析结果（语气部分）
        if llm_analysis:
            # 如果已有voice部分，合并；否则创建新的
            if "voice" not in merged_analysis:
                merged_analysis["voice"] = {}
            
            # 从视频分析中保留其他语音指标（speed, volume等），但用LLM的语气分析覆盖tone
            if video_analysis and "voice" in video_analysis:
                merged_analysis["voice"].update(video_analysis["voice"])
            
            # 用LLM的语气分析覆盖/补充tone相关字段
            merged_analysis["voice"]["tone"] = llm_analysis["tone"]
            merged_analysis["voice"]["tone_issues"] = llm_analysis.get("tone_issues", "")
            merged_analysis["voice"]["tone_suggestions"] = llm_analysis.get("tone_suggestions", "")
            merged_analysis["voice"]["tone_score"] = llm_analysis.get("tone_score", 50)
            merged_analysis["voice"]["tone_score_label"] = llm_analysis.get("tone_score_label", "Fair")
        
        # 如果没有LLM分析，使用视频分析的结果
        if not llm_analysis and video_analysis:
            merged_analysis = video_analysis
        
        # 4. 注入元数据标记（仅保留基础结构，不进行硬编码警告注入）
        # 这个逻辑应该对所有情况都执行（只要有 visual 分析结果）
        if merged_analysis.get("visual"):
            if merged_analysis["visual"].get("metadata"):
                meta = merged_analysis["visual"]["metadata"]
            else:
                log(f"[VideoProcessor] ⚠️  WARNING: Visual analysis exists but metadata is missing!")
                log(f"[VideoProcessor]    Visual keys: {list(merged_analysis['visual'].keys())}")
                # 如果没有metadata，创建一个默认的
                meta = {
                    "face_frames_count": 0,
                    "total_frames": 0,
                    "face_off_screen_detected": False,
                    "analysis_failed": True,
                    "bad_habit_detected": False,
                    "bad_habit_details": None,
                    "smile_detected": False,
                    "smile_frames_count": 0
                }
                merged_analysis["visual"]["metadata"] = meta
                log(f"[VideoProcessor] 🔧 Created default metadata")
            
            # ⚡ 移除硬编码警告逻辑，完全依赖 Unified Evaluation Service 的输出结果
            # 所有的视觉分析规则（人脸检测、不当行为、微笑等）现在都由 prompt_unified_evaluation_system_msg_zh.md 控制
            log(f"[VideoProcessor] ✓ Visual analysis metadata processed (no hardcoded warnings injected)")

        # 5. 更新 timeline 中的 nonverbal 数据（不包含 video_url）
        # 确保 merged_nonverbal 在所有情况下都被初始化
        if not merged_analysis:
            # 如果没有任何分析结果，创建空的默认结构
            merged_analysis = {
                "voice": {"summary": "分析データがありません"},
                "visual": {"facial_expression": "分析データがありません"},
            }
        
        merged_nonverbal = {
            "analysis": merged_analysis,
        }
        if realtime_hint:
            merged_nonverbal.setdefault("realtime", realtime_hint)
        await session_manager.update_segment_nonverbal(
            session_id=session_id,
            segment_index=segment_index,
            nonverbal_data=merged_nonverbal,
        )
        log(f"[VideoProcessor] ✓ Timeline updated with combined analysis (no video_url)")
        await _refresh_full_report_if_ready(session_id)
        
    except Exception as e:
        log(f"[VideoProcessor] ✗ Video processing error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理临时视频文件
        if video_path and os.path.exists(video_path):
            try:
                os.unlink(video_path)
                log(f"[VideoProcessor] ✓ Cleaned up temp video")
            except Exception as cleanup_err:
                print(f"[VideoProcessor] ✗ Cleanup error: {cleanup_err}")


async def _refresh_full_report_if_ready(session_id: str) -> None:
    """
    Once every segment has a completed nonverbal analysis, re-run the full evaluation
    if a "completed" full report already exists so that new video insights are reflected.
    """
    try:
        analysis_status = await session_manager.check_analysis_complete(session_id)
        if not analysis_status.get("complete"):
            return

        session = await session_manager.get_session(session_id)
        if session.full_report_status != "completed":
            return

        log(f"[VideoProcessor] ♻ All segments analyzed post-report; rebuilding evaluation for session {session_id}")
        await session_manager.set_full_report_status(session_id, "processing")
        asyncio.create_task(fallback_full_evaluation(session_id))
    except Exception as refresh_err:  # pragma: no cover
        log(f"[VideoProcessor] ⚠️ Full report refresh skipped due to error: {refresh_err}")


async def analyze_chunk_async(
    session_id: str,
    chunk_path: str,
    chunk_index: int,
    duration: float
) -> None:
    """
    异步分析视频片段（用于录制过程中的实时分析）
    
    Args:
        session_id: 会话ID
        chunk_path: 视频片段路径
        chunk_index: 片段索引
        duration: 片段时长
    """
    try:
        log(f"[VideoProcessor] 🎥 Analyzing chunk {chunk_index}...")
        
        # 使用 GLM-4.5V 快速分析
        analysis = await video_nonverbal_analyzer.analyze_video(
            video_path=chunk_path,
            transcript="",  # 录制中还没有转写文本
            duration=duration
        )
        
        # 存储临时分析结果（可以用 Redis 或内存缓存）
        # 这里简化处理，只打印日志
        log(f"[VideoProcessor] ✓ Chunk {chunk_index} analysis: {analysis.get('overall_impression', '')}")
        
    except Exception as e:
        log(f"[VideoProcessor] ✗ Chunk analysis error: {e}")
    
    finally:
        if chunk_path and os.path.exists(chunk_path):
            os.unlink(chunk_path)


