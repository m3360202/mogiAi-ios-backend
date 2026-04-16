"""
Segmented Interview API - Non-realtime, button-based submission
"""
from fastapi import APIRouter, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import time
import os
import tempfile

from app.services.deepseek_interview_service import DeepseekInterviewService
from app.services.interview_session_manager import session_manager
from app.services.interview_params_service import interview_params_service
from app.services.video_nonverbal_analyzer import video_nonverbal_analyzer
from app.services.langchain_service import langchain_service

router = APIRouter()
deepseek_service = DeepseekInterviewService()

@router.post("/start")
async def start_segmented_interview(
    role: str = Form(default="面试官-后端开发"),
    system_message: Optional[str] = Form(default=None)
):
    """
    Start a new segmented interview session
    Returns: session_id and first question
    """
    # Default system message if not provided
    if not system_message:
        system_message = f"你是一名专业的{role}。请根据候选人的回答进行面试，提出有深度的问题。"
    
    # Start session
    session = await session_manager.start_session(role, system_message)
    session_id = session.session_id
    print(f"[Segmented] Session started: {session_id}")
    
    # Generate first question using Deepseek
    first_question = await deepseek_service.generate_first_question(role, system_message)
    
    # Add to timeline (assume first question takes ~5 seconds)
    t0 = 0.0
    t1 = 5.0
    await session_manager.seg_start(session_id, t0, "system")
    await session_manager.seg_append_text(session_id, first_question)
    await session_manager.seg_commit(session_id, t1)
    
    return JSONResponse({
        "session_id": session_id,
        "first_question": first_question,
        "timestamp": time.time()
    })


@router.post("/submit-answer/{session_id}")
async def submit_answer(
    session_id: str,
    audio_file: UploadFile = File(...),
    video_file: Optional[UploadFile] = File(None),
    duration: float = Form(...),
    nonverbal_features: Optional[str] = Form(None)  # JSON string from frontend
):
    """
    Submit user's answer (audio + optional video + nonverbal features)
    Returns: next question from AI
    """
    print(f"[Segmented] Received answer for session: {session_id}")
    print(f"[Segmented] Audio: {audio_file.filename}, Duration: {duration}s")
    print(f"[Segmented] Video file received: {video_file is not None}, Filename: {video_file.filename if video_file else 'N/A'}")
    
    # Save audio file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        audio_content = await audio_file.read()
        temp_audio.write(audio_content)
        audio_path = temp_audio.name
        print(f"[Segmented] Saved audio to: {audio_path} ({len(audio_content)} bytes)")
    
    # Video processing
    video_path = None
    nonverbal_analysis = None
    
    if video_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            video_content = await video_file.read()
            temp_video.write(video_content)
            video_path = temp_video.name
            print(f"[Segmented] Saved video to: {video_path} ({len(video_content)} bytes)")
    
    try:
        # Get session info first to determine language
        try:
            session = await session_manager.get_session(session_id)
            session_metadata = getattr(session, "metadata", {}) or {}
            session_language = session_metadata.get("language", "ja")
        except Exception:
            session_language = "ja"
            
        # Step 1: Speech-to-text (ASR)
        # TODO: Integrate ASR service (Deepseek, Whisper, or other)
        # For now, use placeholder
        user_text = await _transcribe_audio(audio_path, duration=duration, language=session_language)
        print(f"[Segmented] Transcribed text: {user_text[:100]}...")
        
        # Step 2: Extract nonverbal features (if video provided)
        nonverbal_data = {}
        
        if nonverbal_features:
            import json
            nonverbal_data = json.loads(nonverbal_features)
            print(f"[Segmented] Nonverbal features: {nonverbal_data}")
        
        # Step 2.5: Analyze video and use LLM for tone and expression (if provided)
        if video_path:
            try:
                print(f"[Segmented] Analyzing video nonverbal behavior with LLM...")
                
                # 1. 视频分析获取视觉信息
                video_analysis = None
                if video_nonverbal_analyzer is not None:
                    try:
                        video_analysis = await video_nonverbal_analyzer.analyze_video(
                            video_path=video_path,
                            transcript=user_text,
                            duration=duration,
                            language=session_language
                        )
                        print(f"[Segmented] Video visual analysis completed")
                    except Exception as e:
                        print(f"[Segmented] Video analysis failed: {e}")
                
                # 2. 使用LangChain LLM分析语气
                llm_analysis = None
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
                        
                        # 提取音频特征（从nonverbal_features）
                        audio_features = None
                        if nonverbal_features:
                            import json as json_lib
                            try:
                                features = json_lib.loads(nonverbal_features) if isinstance(nonverbal_features, str) else nonverbal_features
                                audio_features = {
                                    "speaking_rate": features.get("speaking_rate"),
                                    "average_volume": features.get("average_volume"),
                                    "pitch_variation": features.get("pitch_variation"),
                                }
                                audio_features = {k: v for k, v in audio_features.items() if v is not None}
                                if not audio_features:
                                    audio_features = None
                            except:
                                pass
                        
                        # 使用LangChain分析语气
                        six_dim_analysis = await langchain_service.analyze_interview_six_dimensions(
                            transcript=user_text,
                            question=current_question or "面接質問",
                            audio_features=audio_features,
                        )
                        
                        expression_dim = six_dim_analysis.expression
                        llm_analysis = {
                            "tone": expression_dim.performance,
                            "tone_issues": expression_dim.issues,
                            "tone_suggestions": expression_dim.suggestions,
                            "tone_score": expression_dim.score,
                            "tone_score_label": "Good" if expression_dim.score >= 70 else ("Fair" if expression_dim.score >= 50 else "Poor"),
                        }
                        print(f"[Segmented] LLM tone analysis completed (score: {expression_dim.score})")
                        
                        # 如果有视频分析，用LLM进一步分析表情
                        if video_analysis and "visual" in video_analysis:
                            visual_info = video_analysis["visual"]
                            facial_expression_raw = visual_info.get("facial_expression", "")
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

JSON形式で返してください：
{{"facial_expression": "詳細な表情分析", "facial_expression_score_label": "Good/Fair/Poor"}}
"""
                                    response = await langchain_service.default_model.ainvoke([HumanMessage(content=facial_prompt)])
                                    import json as json_lib
                                    import re
                                    response_text = response.content.strip()
                                    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
                                    if json_match:
                                        facial_llm_result = json_lib.loads(json_match.group(0))
                                        llm_analysis["facial_expression"] = facial_llm_result.get("facial_expression", facial_expression_raw)
                                        llm_analysis["facial_expression_score_label"] = facial_llm_result.get("facial_expression_score_label", "Fair")
                                        print(f"[Segmented] LLM facial expression analysis completed")
                                except Exception as e:
                                    print(f"[Segmented] LLM facial expression analysis failed: {e}")
                    except Exception as e:
                        print(f"[Segmented] LLM analysis failed: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 3. 合并分析结果
                merged_analysis = {}
                if video_analysis:
                    merged_analysis["visual"] = video_analysis.get("visual", {}).copy()
                    merged_analysis["overall_impression"] = video_analysis.get("overall_impression", "")
                
                if llm_analysis:
                    if "voice" not in merged_analysis:
                        merged_analysis["voice"] = {}
                    if video_analysis and "voice" in video_analysis:
                        merged_analysis["voice"].update(video_analysis["voice"])
                    merged_analysis["voice"]["tone"] = llm_analysis["tone"]
                    merged_analysis["voice"]["tone_issues"] = llm_analysis.get("tone_issues", "")
                    merged_analysis["voice"]["tone_suggestions"] = llm_analysis.get("tone_suggestions", "")
                    merged_analysis["voice"]["tone_score"] = llm_analysis.get("tone_score", 50)
                    merged_analysis["voice"]["tone_score_label"] = llm_analysis.get("tone_score_label", "Fair")
                    
                    if "facial_expression" in llm_analysis:
                        merged_analysis["visual"]["facial_expression"] = llm_analysis["facial_expression"]
                        if "facial_expression_score_label" in llm_analysis:
                            merged_analysis["visual"]["facial_expression_score_label"] = llm_analysis["facial_expression_score_label"]
                
                if not llm_analysis and video_analysis:
                    merged_analysis = video_analysis
                
                # Merge analysis with nonverbal data（视频不再上传）
                if merged_analysis:
                    nonverbal_data = {
                        **nonverbal_data,
                        "analysis": merged_analysis
                    }
                    print(f"[Segmented] Combined analysis completed")
                
            except Exception as video_error:
                print(f"[Segmented] Video processing error: {video_error}")
                import traceback
                traceback.print_exc()
                # Continue even if video processing fails
        
        # Step 3: Add user answer to timeline
        try:
            session = await session_manager.get_session(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")
        
        current_time = len(session.timeline) * 30.0  # Approximate 30s per turn
        user_end_time = current_time + duration
        
        # Add user answer to timeline
        await session_manager.seg_start(session_id, current_time, "user")
        await session_manager.seg_append_text(session_id, user_text)
        if nonverbal_data:
            await session_manager.seg_append_nonverbal(session_id, nonverbal_data)
        await session_manager.seg_commit(session_id, user_end_time)
        
        # Step 4: Check if should end interview based on rounds
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        
        # Count user answers (rounds)
        user_rounds = len([msg for msg in timeline_doc["conversation"] if msg.get("role") == "user"])
        max_rounds = interview_params_service.get_basic_rounds()
        
        print(f"[Segmented] Current round: {user_rounds}/{max_rounds}")
        
        # Check if should end
        if user_rounds >= max_rounds:
            next_question = "今回の面接はこれで終了です。ご協力ありがとうございました。結果画面で詳細な評価をご確認ください。"
            if session_language.startswith("en"):
                next_question = "This concludes the interview. Thank you for your cooperation. Please check the results screen for detailed evaluation."
            elif session_language.startswith("zh"):
                next_question = "本次面试到此结束。感谢您的配合。请在结果页面查看详细评价。"
            
            print(f"[Segmented] Interview completed after {user_rounds} rounds")
        else:
            # Generate next question
            next_question = await deepseek_service.generate_next_question(
                conversation_history=timeline_doc["conversation"],
                user_answer=user_text,
                role=session.role,
                system_message=session.system_message,
                language=session_language
            )
        
        # Step 5: Add AI question to timeline
        ai_start_time = user_end_time + 1.0
        ai_end_time = ai_start_time + 5.0  # Assume AI question takes ~5 seconds
        await session_manager.seg_start(session_id, ai_start_time, "system")
        await session_manager.seg_append_text(session_id, next_question)
        await session_manager.seg_commit(session_id, ai_end_time)
        
        return JSONResponse({
            "next_question": next_question,
            "transcribed_text": user_text,
            "timestamp": time.time()
        })
    
    finally:
        # Cleanup temp files
        if os.path.exists(audio_path):
            os.unlink(audio_path)
        if video_path and os.path.exists(video_path):
            os.unlink(video_path)


@router.get("/timeline/{session_id}")
async def get_timeline(session_id: str):
    """Get complete interview timeline"""
    try:
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        return JSONResponse(timeline_doc)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/interview-flow/{session_id}")
async def get_interview_flow(session_id: str):
    """
    获取完整面试流程数组，包含所有nonverbal分析
    
    Returns:
        Array of interview segments with timestamp, role, content, and nonverbal analysis
    """
    try:
        try:
            session = await session_manager.get_session(session_id)
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or expired."
            )
        
        # Build interview flow array
        interview_flow = []
        
        for segment in session.timeline:
            # Format timestamp
            start_time = segment.start_time
            end_time = segment.end_time
            
            start_formatted = _format_time(start_time)
            end_formatted = _format_time(end_time)
            
            # Build nonverbal info
            nonverbal_info = {}
            if segment.nonverbal:
                analysis = segment.nonverbal.get("analysis", {})
                voice_analysis = analysis.get("voice", {})
                visual_analysis = analysis.get("visual", {})
                
                # 如果是system角色（面试官）
                if segment.role == "system":
                    nonverbal_info = {
                        "expression": visual_analysis.get("facial_expression", "专业友好"),
                        "body_gesture": visual_analysis.get("body_posture", "端正自然"),
                        "tone": voice_analysis.get("tone", "专业平稳"),
                        "overall": analysis.get("overall_impression", "专业得体")
                    }
                else:  # user角色（应试者）
                    nonverbal_info = {
                        "voice_performance": {
                            "speed": voice_analysis.get("speed", ""),
                            "tone": voice_analysis.get("tone", ""),
                            "volume": voice_analysis.get("volume", ""),
                            "pronunciation": voice_analysis.get("pronunciation", ""),
                            "pause": voice_analysis.get("pause", ""),
                            "summary": voice_analysis.get("summary", "")
                        },
                        "visual_performance": {
                            "eye_contact": visual_analysis.get("eye_contact", ""),
                            "facial_expression": visual_analysis.get("facial_expression", ""),
                            "body_posture": visual_analysis.get("body_posture", ""),
                            "appearance": visual_analysis.get("appearance", ""),
                            "summary": visual_analysis.get("summary", "")
                        },
                        "overall_impression": analysis.get("overall_impression", ""),
                        "video_url": segment.nonverbal.get("video_url", "")
                    }
            
            interview_flow.append({
                "timestamp": {
                    "start": start_formatted,
                    "end": end_formatted
                },
                "role": segment.role,
                "content": segment.text,
                "nonverbal": nonverbal_info
            })
        
        return JSONResponse({
            "session_id": session_id,
            "role": session.role,
            "total_segments": len(interview_flow),
            "interview_flow": interview_flow
        })
        
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        print(f"[Segmented] Error getting interview flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-video/{session_id}")
async def analyze_video_segment(
    session_id: str,
    video_file: UploadFile = File(...),
    segment_index: int = Form(...),
    duration: float = Form(...)
):
    """
    Analyze a single video segment and return GPT-4o-mini analysis
    This endpoint is called after interview ends to batch process all videos
    """
    print(f"[Segmented] Analyzing video segment {segment_index} for session {session_id}")
    
    video_path = None
    try:
        # Read video content first
        video_content = await video_file.read()
        print(f"[Segmented] Read video segment {segment_index}: {len(video_content)} bytes")
        
        # Save video temporarily (use project temp dir to avoid system temp space issues)
        import os
        temp_dir = os.path.join(os.getcwd(), "temp_videos")
        os.makedirs(temp_dir, exist_ok=True)
        
        video_path = os.path.join(temp_dir, f"video_{session_id}_{segment_index}.mp4")
        with open(video_path, 'wb') as f:
            f.write(video_content)
        print(f"[Segmented] Saved video segment {segment_index}: {video_path}")
        
        # Get transcript for this segment (if available)
        transcript = ""
        session_language = "ja"
        try:
            session = await session_manager.get_session(session_id)
            session_metadata = getattr(session, "metadata", {}) or {}
            session_language = session_metadata.get("language", "ja")
            
            user_segments = [seg for seg in session.timeline if seg.role == "user"]
            
            if segment_index < len(user_segments):
                transcript = user_segments[segment_index].content
            else:
                transcript = ""
                print(f"[Segmented] Warning: No transcript found for segment {segment_index}")
        except Exception as e:
            print(f"[Segmented] Error getting transcript: {e}")
            transcript = ""
        
        # Analyze video with LLM for tone and expression
        print(f"[Segmented] Starting video analysis with LLM for segment {segment_index}...")
        
        # 1. 视频分析获取视觉信息
        video_analysis = None
        if video_nonverbal_analyzer is not None:
            try:
                video_analysis = await video_nonverbal_analyzer.analyze_video(
                    video_path=video_path,
                    transcript=transcript,
                    duration=duration,
                    language=session_language
                )
                print(f"[Segmented] Video visual analysis completed")
            except Exception as e:
                print(f"[Segmented] Video analysis failed: {e}")
        
        # 2. 使用LangChain LLM分析语气
        llm_analysis = None
        if langchain_service is not None:
            try:
                # 获取当前问题
                timeline = await session_manager.get_timeline_doc(session_id)
                current_question = ""
                for msg in reversed(timeline.get("conversation", [])):
                    if msg.get("role") == "system":
                        current_question = msg.get("content", "")
                        break
                
                # 使用LangChain分析语气
                six_dim_analysis = await langchain_service.analyze_interview_six_dimensions(
                    transcript=transcript,
                    question=current_question or "面接質問",
                    audio_features=None,
                )
                
                expression_dim = six_dim_analysis.expression
                llm_analysis = {
                    "tone": expression_dim.performance,
                    "tone_issues": expression_dim.issues,
                    "tone_suggestions": expression_dim.suggestions,
                    "tone_score": expression_dim.score,
                    "tone_score_label": "Good" if expression_dim.score >= 70 else ("Fair" if expression_dim.score >= 50 else "Poor"),
                }
                print(f"[Segmented] LLM tone analysis completed (score: {expression_dim.score})")
                
                # 如果有视频分析，用LLM进一步分析表情
                if video_analysis and "visual" in video_analysis:
                    visual_info = video_analysis["visual"]
                    facial_expression_raw = visual_info.get("facial_expression", "")
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
{transcript[:200]}

JSON形式で返してください：
{{"facial_expression": "詳細な表情分析", "facial_expression_score_label": "Good/Fair/Poor"}}
"""
                            response = await langchain_service.default_model.ainvoke([HumanMessage(content=facial_prompt)])
                            import json as json_lib
                            import re
                            response_text = response.content.strip()
                            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
                            if json_match:
                                facial_llm_result = json_lib.loads(json_match.group(0))
                                llm_analysis["facial_expression"] = facial_llm_result.get("facial_expression", facial_expression_raw)
                                llm_analysis["facial_expression_score_label"] = facial_llm_result.get("facial_expression_score_label", "Fair")
                                print(f"[Segmented] LLM facial expression analysis completed")
                        except Exception as e:
                            print(f"[Segmented] LLM facial expression analysis failed: {e}")
            except Exception as e:
                print(f"[Segmented] LLM analysis failed: {e}")
                import traceback
                traceback.print_exc()
        
        # 3. 合并分析结果
        merged_analysis = {}
        if video_analysis:
            merged_analysis["visual"] = video_analysis.get("visual", {}).copy()
            merged_analysis["overall_impression"] = video_analysis.get("overall_impression", "")
        
        if llm_analysis:
            if "voice" not in merged_analysis:
                merged_analysis["voice"] = {}
            if video_analysis and "voice" in video_analysis:
                merged_analysis["voice"].update(video_analysis["voice"])
            merged_analysis["voice"]["tone"] = llm_analysis["tone"]
            merged_analysis["voice"]["tone_issues"] = llm_analysis.get("tone_issues", "")
            merged_analysis["voice"]["tone_suggestions"] = llm_analysis.get("tone_suggestions", "")
            merged_analysis["voice"]["tone_score"] = llm_analysis.get("tone_score", 50)
            merged_analysis["voice"]["tone_score_label"] = llm_analysis.get("tone_score_label", "Fair")
            
            if "facial_expression" in llm_analysis:
                merged_analysis["visual"]["facial_expression"] = llm_analysis["facial_expression"]
                if "facial_expression_score_label" in llm_analysis:
                    merged_analysis["visual"]["facial_expression_score_label"] = llm_analysis["facial_expression_score_label"]
        
        if not llm_analysis and video_analysis:
            merged_analysis = video_analysis
        
        print(f"[Segmented] Combined analysis completed for segment {segment_index}")
        
        # Return analysis result
        result = {
            "segmentIndex": segment_index,
            "videoUrl": None,  # 不再上传视频
            "analysis": merged_analysis,
            "transcript": transcript,
            "duration": duration
        }
        
        return JSONResponse(result)
        
    except Exception as e:
        print(f"[Segmented] Error analyzing video segment {segment_index}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {str(e)}")
    
    finally:
        # Cleanup temp video file
        if video_path and os.path.exists(video_path):
            try:
                os.unlink(video_path)
                print(f"[Segmented] Cleaned up temp video file: {video_path}")
            except Exception as cleanup_err:
                print(f"[Segmented] Warning: Failed to cleanup video file: {cleanup_err}")


@router.post("/end/{session_id}")
async def end_interview(session_id: str):
    """End interview and return final timeline"""
    try:
        timeline_doc = await session_manager.get_timeline_doc(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # TODO: Save to database (Supabase)
    print(f"[Segmented] Interview ended: {session_id}")
    
    return JSONResponse({
        "status": "completed",
        "timeline": timeline_doc
    })


def _format_time(seconds: float) -> str:
    """Format seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


# ========== Helper Functions ==========

async def _transcribe_audio(audio_path: str, duration: Optional[float] = None, language: Optional[str] = None) -> str:
    """
    Transcribe audio to text using OpenAI Whisper
    """
    import os
    
    print(f"[ASR] Transcribing audio file: {audio_path} (language: {language})")
    
    # Check file size
    file_size = os.path.getsize(audio_path) / (1024 * 1024)  # MB
    print(f"[ASR] Audio file size: {file_size:.2f} MB")
    
    # Use OpenAI Whisper
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print("[ASR] Using OpenAI Whisper")
        return await _transcribe_with_openai(audio_path, openai_key, language=language)
    
    # No ASR configured - return standard no-answer marker
    print("[ASR] Warning: OPENAI_API_KEY not configured")
    return "ユーザーはこの質問に回答していません"


async def _transcribe_with_openai(audio_path: str, api_key: str, language: Optional[str] = None) -> str:
    """OpenAI Whisper API"""
    try:
        import os
        import tempfile
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=api_key, timeout=60.0)
        
        # 检查文件大小和格式
        file_size = os.path.getsize(audio_path)
        file_ext = os.path.splitext(audio_path)[1].lower()
        
        print(f"[ASR] Audio file: {audio_path}, size: {file_size} bytes, ext: {file_ext}")
        
        # 如果文件太小（< 1KB），可能用户没有说话
        if file_size < 1024:
            print(f"[ASR] ⚠️ File too small ({file_size} bytes), user may not have spoken")
            return "ユーザーはこの質問に回答していません"
        
        # 对于 m4a 格式，检查文件头部是否完整
        if file_ext == ".m4a":
            with open(audio_path, 'rb') as f:
                header = f.read(12)
                # m4a 文件应该以 ftyp box 开头
                if not header.startswith(b'\x00\x00\x00') and b'ftyp' not in header[:12]:
                    print(f"[ASR] ⚠️ M4A file header may be corrupted, attempting to read anyway")
        
        # Map language code to Whisper supported code if needed
        whisper_lang = language
        if language:
            # Handle zh-CN, zh-TW -> zh
            if language.lower().startswith('zh'):
                whisper_lang = 'zh'
            # Handle other codes if necessary
            elif '-' in language:
                whisper_lang = language.split('-')[0]
        
        # If no language specified, default to 'ja' or auto-detect if we remove the default
        # For now, let's default to 'ja' if not provided to maintain behavior, 
        # but the caller should provide it.
        target_lang = whisper_lang or "ja"
        
        for attempt in range(2):
            try:
                print(f"[ASR] Attempt {attempt + 1}/2: Sending to OpenAI Whisper (language={target_lang})...")
                
                # 尝试直接读取
                with open(audio_path, 'rb') as audio_file:
                    # 使用 prompt 引导 Whisper 输出标点符号
                    # 对于中文/日语，使用包含标点的引导语有助于模型输出标点
                    initial_prompt = "这是一个面试回答，请准确转录并保留标点符号。"
                    if target_lang == "ja":
                        initial_prompt = "これは面接の回答です。句読点を含めて正確に書き起こしてください。"
                    elif target_lang == "en":
                        initial_prompt = "This is an interview answer. Please transcribe accurately with punctuation."

                    transcript = await client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=target_lang,
                        prompt=initial_prompt
                    )
                
                text = transcript.text.strip()
                
                # ⚠️ 检查转写结果是否为空（用户没有说话或选择不回答）
                if not text or len(text) < 2:
                    print(f"[ASR] ℹ️ Transcription is empty or too short (len={len(text)}), user did not answer")
                    return "ユーザーはこの質問に回答していません"
                
                def _should_flag_no_answer() -> bool:
                    """
                    当 duration < 1s 时才视为无回答。
                    旧接口未提供 duration（None），保持原有行为。
                    """
                    if duration is None:
                        return True
                    return duration < 1.0
                
                # ⚠️ 检查是否是无意义的识别结果（常见的静音误识别）
                # Whisper 在静音时可能会误识别出一些无意义的文本
                meaningless_patterns = [
                    "ご視聴ありがとう",
                    "ご視聴",
                    "視聴",
                    "最後まで視聴",
                    "本当にありがとう",
                    "ご清聴ありがとう",
                    "ご清聴",
                    "ありがとうございました",
                    "ありがとうございます",
                    "字幕",
                    "subtitle",
                    "thank you for watching",
                    "thank you",
                    "。。。",
                    "...",
                    "無音",
                    "silence",
                ]
                
                text_lower = text.lower()
                for pattern in meaningless_patterns:
                    # 对于视聴/清聴/thank you 等关键词，允许更长的文本（因为这些是固定短语）
                    max_length = 60 if any(key in pattern for key in ["視聴", "清聴", "thank"]) else 30
                    if pattern.lower() in text_lower and len(text) < max_length:
                        if _should_flag_no_answer():
                            print(f"[ASR] ℹ️ Detected meaningless transcription pattern: '{text}' (contains: {pattern}), marking as no answer")
                            return "ユーザーはこの質問に回答していません"
                        else:
                            print(f"[ASR] ℹ️ Detected meaningless transcription pattern but duration={duration:.2f}s, keeping transcript")
                            break
                
                # ⚠️ 检查是否只包含标点符号和空白
                if all(c in '。、！？!?,.;:　 \n\t' for c in text):
                    if _should_flag_no_answer():
                        print(f"[ASR] ℹ️ Transcription contains only punctuation: '{text}', marking as no answer")
                        return "ユーザーはこの質問に回答していません"
                    else:
                        print(f"[ASR] ℹ️ Punctuation-only transcript but duration={duration:.2f}s, keeping transcript")
                
                print(f"[ASR] ✓ OpenAI Success: {text[:100]}...")
                return text
            
            except Exception as e:
                error_msg = str(e)
                print(f"[ASR] ✗ Attempt {attempt + 1} failed: {type(e).__name__}: {error_msg[:200]}")
                
                # 如果是格式错误且是第一次尝试，尝试重新读取文件
                if attempt == 0 and ("could not be decoded" in error_msg or "format is not supported" in error_msg):
                    print(f"[ASR] ⚠️ Format error detected, checking file integrity...")
                    # 验证文件是否可读
                    try:
                        with open(audio_path, 'rb') as f:
                            test_read = f.read(1024)
                            if len(test_read) < 100:
                                print(f"[ASR] ⚠️ File appears corrupted (only {len(test_read)} bytes readable)")
                                return "ユーザーはこの質問に回答していません"
                    except Exception as read_err:
                        print(f"[ASR] ⚠️ Cannot read file: {read_err}")
                        return "ユーザーはこの質問に回答していません"
                    
                    import asyncio
                    await asyncio.sleep(2)
                elif attempt == 0:
                    import asyncio
                    await asyncio.sleep(2)
        
        # 所有重试都失败，标记为未回答
        print(f"[ASR] ✗ All transcription attempts failed")
        return "ユーザーはこの質問に回答していません"
    
    except Exception as e:
        print(f"[ASR] ✗ OpenAI error: {type(e).__name__}: {e}")
        return "ユーザーはこの質問に回答していません"

