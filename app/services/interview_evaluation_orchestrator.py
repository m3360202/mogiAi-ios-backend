"""
Interview Evaluation Orchestrator Service
编排面试评估流程：section评估 + overall评估
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from uuid import UUID
from sqlalchemy import select, update

from app.services.interview_session_manager import session_manager
from app.services.evaluation.services.adapters import (
    parse_eval_request,
    pack_eval_response,
)
from app.schemas.evaluation import (
    InterviewDialogItem,
    InterviewEvalRequest,
    InterviewTimestamp,
    NonverbalPerformance,
    VoicePerformance,
    VisualPerformance,
)
from app.models.interview import Interview
from app.core import database
from datetime import datetime, timedelta
from sqlalchemy import and_, desc


_two_phase_evaluation_api = None
_two_phase_evaluation_init_error: Optional[Exception] = None


def _get_two_phase_evaluation_api():
    """
    Lazily initialize the two-phase evaluation API.

    Important:
    - Avoid crashing the whole process at import time if prompt assets are missing.
    - If initialization fails, we disable two-phase evaluation and log the error.
    """
    global _two_phase_evaluation_api, _two_phase_evaluation_init_error
    if _two_phase_evaluation_api is not None:
        return _two_phase_evaluation_api
    if _two_phase_evaluation_init_error is not None:
        return None
    try:
        from app.services.evaluation.public.two_phase_evaluation_api import TwoPhaseEvaluationAPIImpl

        _two_phase_evaluation_api = TwoPhaseEvaluationAPIImpl()
        return _two_phase_evaluation_api
    except Exception as e:
        _two_phase_evaluation_init_error = e
        log(f"[EvaluationOrchestrator] ⚠️ Two-phase evaluation disabled (init failed): {e}")
        return None


async def get_previous_scores_for_user(
    user_id: UUID,
    current_time: datetime
) -> Optional[Dict[str, float]]:
    """
    查询用户最近一次测试（7天以内）的所有维度得分（只查询一次数据库）
    
    Args:
        user_id: 用户ID
        current_time: 当前时间
        
    Returns:
        字典，key为维度类型（小写），value为得分。如果没有7天内的测试则返回 None
    """
    try:
        session_maker = database.async_session_maker
        if session_maker is None:
            return None
        
        # 计算7天前的时间
        seven_days_ago = current_time - timedelta(days=7)
        
        async with session_maker() as db:
            # 查询用户最近一次完成的面试（7天以内）
            result = await db.execute(
                select(Interview)
                .where(
                    and_(
                        Interview.user_id == user_id,
                        Interview.status == "completed",
                        Interview.completed_at >= seven_days_ago,
                        Interview.completed_at < current_time
                    )
                )
                .order_by(desc(Interview.completed_at))
                .limit(1)
            )
            previous_interview = result.scalar_one_or_none()
            
            if not previous_interview:
                log(f"[EvaluationOrchestrator] No previous interview found within 7 days for user {user_id}")
                return None
            
            # 从 dimension_scores 中提取所有维度的得分
            scores_dict: Dict[str, float] = {}
            dimension_scores = previous_interview.dimension_scores
            if dimension_scores and isinstance(dimension_scores, dict):
                for dim_key, dim_data in dimension_scores.items():
                    if isinstance(dim_data, dict) and "score" in dim_data:
                        scores_dict[dim_key.lower()] = float(dim_data["score"])
                    elif isinstance(dim_data, (int, float)):
                        scores_dict[dim_key.lower()] = float(dim_data)
            
            # 如果 dimension_scores 没有，尝试从 overall_eval 中提取总体得分
            if not scores_dict and previous_interview.overall_eval and isinstance(previous_interview.overall_eval, dict):
                overall_data = previous_interview.overall_eval.get("overall", {})
                if isinstance(overall_data, dict) and "score" in overall_data:
                    overall_score = float(overall_data["score"])
                    # 如果没有维度得分，使用总体得分作为所有维度的参考
                    log(f"[EvaluationOrchestrator] Using overall score {overall_score} as reference for all dimensions (from interview {previous_interview.id})")
                    return {"overall": overall_score}
            
            if scores_dict:
                log(f"[EvaluationOrchestrator] Found previous scores for {len(scores_dict)} dimensions (from interview {previous_interview.id}): {scores_dict}")
            else:
                log(f"[EvaluationOrchestrator] No scores found in previous interview {previous_interview.id}")
            
            return scores_dict if scores_dict else None
            
    except Exception as e:
        log(f"[EvaluationOrchestrator] Error querying previous scores: {e}")
        import traceback
        traceback.print_exc()
        return None


async def get_previous_score_for_user(
    user_id: UUID,
    super_metric_type: str,
    current_time: datetime
) -> Optional[float]:
    """
    查询用户最近一次测试（7天以内）的指定维度得分（已废弃，建议使用 get_previous_scores_for_user）
    
    保留此函数以保持向后兼容，但建议使用 get_previous_scores_for_user 一次性获取所有维度得分
    """
    scores_dict = await get_previous_scores_for_user(user_id, current_time)
    if not scores_dict:
        return None
    
    # 将 super_metric_type 转换为小写（如 "CLARITY" -> "clarity"）
    dim_key = super_metric_type.lower()
    return scores_dict.get(dim_key) or scores_dict.get("overall")


def log(message: str) -> None:
    """打印日志"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")


async def update_interview_overall_eval(
    session_id: str, 
    evaluation_data: Dict[str, Any], 
    max_retries: int = 12, 
    initial_delay: float = 2.0,
    max_delay: float = 60.0
) -> bool:
    """
    Update the interview record with overall evaluation results.
    Uses retry with exponential backoff to handle race conditions where
    the interview record might not be ready yet.
    
    The retry mechanism ensures that evaluation data gets into the database
    even if there's a timing issue between async evaluation completion 
    and interview record creation.
    
    Args:
        session_id: Interview session ID
        evaluation_data: Evaluation data from InterviewEvalResponse.data
        max_retries: Maximum number of retry attempts (default 12, ~4 minutes total)
        initial_delay: Initial delay between retries in seconds (default 2s)
        max_delay: Maximum delay between retries in seconds (default 60s)
        
    Returns:
        bool: True if successfully saved to database, False if all retries failed
    """
    import asyncio
    import random

    session_maker = database.async_session_maker
    if session_maker is None:
        try:
            await database.init_db()
        except Exception as init_err:
            print(f"[EvaluationOrchestrator] ⚠️ Failed to initialize database before saving overall_eval: {init_err}")
        session_maker = database.async_session_maker

    if session_maker is None:
        print(f"[EvaluationOrchestrator] ⚠️ Database unavailable, skipping overall_eval persistence for session {session_id}")
        return False
    
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            async with session_maker() as db:
                # Find interview record by session_id
                result = await db.execute(
                    select(Interview).where(Interview.session_id == session_id)
                )
                interview = result.scalar_one_or_none()
                
                if interview:
                    # Update the overall_eval field
                    await db.execute(
                        update(Interview)
                        .where(Interview.session_id == session_id)
                        .values(overall_eval=evaluation_data)
                    )
                    await db.commit()
                    print(f"[EvaluationOrchestrator] ✅ Saved overall_eval to database for interview {interview.id} (attempt {attempt + 1})")
                    return True
                else:
                    if attempt < max_retries:
                        # Calculate delay with exponential backoff + jitter
                        base_delay = min(initial_delay * (2 ** attempt), max_delay)
                        jitter = random.uniform(0.1, 0.3) * base_delay  # Add 10-30% jitter
                        delay = base_delay + jitter
                        
                        print(f"[EvaluationOrchestrator] ⏳ Interview record not found (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s...")
                        await asyncio.sleep(delay)
                    else:
                        print(f"[EvaluationOrchestrator] ❌ Interview record with session_id {session_id} not found after {max_retries + 1} attempts")
                        return False
                        
        except Exception as e:
            if attempt < max_retries:
                delay = min(initial_delay * (2 ** attempt), max_delay)
                print(f"[EvaluationOrchestrator] ❌ Database error on attempt {attempt + 1}: {e}")
                print(f"[EvaluationOrchestrator] 🔄 Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

                # Attempt to reinitialize the database session maker if it became unavailable
                session_maker = database.async_session_maker
                if session_maker is None:
                    try:
                        await database.init_db()
                    except Exception as init_err:
                        print(f"[EvaluationOrchestrator] ⚠️ Database re-initialization failed during retry: {init_err}")
                    session_maker = database.async_session_maker
                    if session_maker is None:
                        print(f"[EvaluationOrchestrator] ⚠️ Database still unavailable after retry attempt for session {session_id}")
                        return False
            else:
                print(f"[EvaluationOrchestrator] ❌ Failed to save overall_eval after {max_retries + 1} attempts: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    return False


async def evaluate_section_async(
    session_id: str,
    turn_index: int,
    dialog_section: Any,  # DialogSection from two-phase evaluation
    transcript: str,
    question: Optional[str] = None,
    nonverbal_snapshot: Optional[Dict[str, Any]] = None,
    is_final_turn: bool = False,
    max_rounds: int = 5,
) -> None:
    """
    Phase 1: 异步评估当前对话section（每轮用户回答后执行）
    使用两阶段评估系统的section-level评估
    
    Args:
        session_id: 会话ID
        turn_index: 轮次索引
        dialog_section: 预构建的对话section对象（避免异步任务中数据不一致）
        transcript: 用户回答文本
        question: 面试官问题
        nonverbal_snapshot: 非语言特征快照
        is_final_turn: 是否为最后一轮
        max_rounds: 最大轮数
    """
    try:
        log(f"[EvaluationOrchestrator] 🔄 Starting section evaluation for turn {turn_index} (session: {session_id})...")
        log(f"[EvaluationOrchestrator] Section details: section_id={dialog_section.id if dialog_section else 'None'}, section_index={getattr(dialog_section, 'section_index', 'N/A') if dialog_section else 'N/A'}")
        start_time = time.time()
        
        # Resolve user_id for history comparison
        user_id = None
        try:
            # 1. Try session metadata
            session = await session_manager.get_session(session_id)
            if session and session.metadata:
                user_id_str = session.metadata.get("user_id")
                if user_id_str:
                    try:
                        user_id = UUID(user_id_str)
                    except (ValueError, TypeError):
                        pass
            
            # 2. Try database if not in metadata
            if not user_id and database.async_session_maker:
                async with database.async_session_maker() as db:
                    result = await db.execute(
                        select(Interview).where(Interview.session_id == session_id).limit(1)
                    )
                    interview = result.scalar_one_or_none()
                    if interview:
                        user_id = interview.user_id
                        log(f"[EvaluationOrchestrator] Found user_id from database: {user_id}")
        except Exception as uid_err:
            log(f"[EvaluationOrchestrator] ⚠️ Failed to resolve user_id (continuing without history): {uid_err}")

        # Phase 1: 直接评估传入的dialog section
        log(f"[EvaluationOrchestrator] 📊 Calling two_phase_evaluation_api.evaluate_section...")
        
        # 尝试从 session metadata 中获取 cached feedback
        cached_feedback = None
        if session and session.metadata and "unified_feedback" in session.metadata:
            # unified_feedback key format: "segment_{section_index}"
            section_key = f"segment_{turn_index}"
            cached_feedback = session.metadata["unified_feedback"].get(section_key)
            if cached_feedback:
                log(f"[EvaluationOrchestrator] 🎯 Found cached unified feedback for section {turn_index}, will skip redundant LLM generation")
        
        api = _get_two_phase_evaluation_api()
        if api is None:
            raise RuntimeError("Two-phase evaluation API unavailable (init failed).")

        section_result = await api.evaluate_section(
            dialog_section, 
            user_id=user_id,
            cached_feedback=cached_feedback
        )
        log(f"[EvaluationOrchestrator] ✓ Received section evaluation result")
        
        elapsed = time.time() - start_time
        log(f"[EvaluationOrchestrator] ✅ Section {turn_index} evaluation completed in {elapsed:.2f}s")
        
        # 构建简化的section评估结果 - 直接存储section_result和基本元数据
        section_eval_data = {
            "turn_index": turn_index,
            "section_id": str(dialog_section.id),
            "section_index": dialog_section.section_index,
            "section_result": section_result,  # 直接存储完整的SectionEvaluationResult对象
            "evaluation_time": elapsed,
            "status": "completed",
            "timestamp": time.time()
        }
        
        # 使用专门的section evaluation存储方法
        log(f"[EvaluationOrchestrator] 💾 Saving section evaluation to session manager...")
        await session_manager.add_section_evaluation(session_id, section_eval_data)
        log(f"[EvaluationOrchestrator] ✅ Section evaluation saved for turn {turn_index}")
        
        # 如果是最后一轮，检查是否所有section评估都完成，然后触发完整报告生成
        # ⚡ 使用后台任务，不阻塞响应
        if is_final_turn:
            log(f"[EvaluationOrchestrator] 🎯 Final turn detected, scheduling full report check...")
            asyncio.create_task(check_and_schedule_full_report(session_id))
        
    except Exception as e:
        log(f"[EvaluationOrchestrator] ❌ Section evaluation failed for turn {turn_index}: {e}")
        import traceback
        traceback.print_exc()
        
        # 保存失败状态
        try:
            error_eval = {
                "turn_index": turn_index,
                "section_id": str(dialog_section.id) if dialog_section else "unknown",
                "section_index": getattr(dialog_section, 'section_index', turn_index) if dialog_section else turn_index,
                "section_result": None,  # No result due to failure
                "evaluation_time": 0.0,
                "status": "failed",
                "error": str(e)[:300],
                "timestamp": time.time()
            }
            await session_manager.add_section_evaluation(session_id, error_eval)
            log(f"[EvaluationOrchestrator] 💾 Saved failed evaluation status for turn {turn_index}")
        except Exception as save_error:
            log(f"[EvaluationOrchestrator] ❌ Failed to save error status: {save_error}")


async def check_and_schedule_full_report(session_id: str, max_retries: int = 10, retry_delay: float = 2.0) -> None:
    """
    检查是否所有section评估都已完成，如果是则触发完整报告生成
    
    Args:
        session_id: 会话ID
        max_retries: 最大重试次数（默认10次）
        retry_delay: 每次重试的延迟秒数（默认2秒）
    """
    for attempt in range(max_retries):
        try:
            # 获取timeline以确定实际的用户回答轮数
            timeline_doc = await session_manager.get_timeline_doc(session_id)
            conversation = timeline_doc.get("conversation", [])
            actual_user_rounds = len([msg for msg in conversation if msg.get("role") == "user"])
            
            # 获取已存储的section evaluation结果
            stored_section_evals = await session_manager.get_section_evaluations(session_id)
            
            if not stored_section_evals:
                print(f"[EvaluationOrchestrator] ⚠️ No section evaluations found for session {session_id} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    print(f"[EvaluationOrchestrator] 🔄 Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    print(f"[EvaluationOrchestrator] ❌ Max retries reached, no section evaluations found")
                    return
            
            # 检查是否所有轮次的section评估都完成
            completed_sections = [
                eval_item for eval_item in stored_section_evals
                if eval_item.get("status") == "completed"
            ]
            
            print(f"[EvaluationOrchestrator] Section evaluation status: {len(completed_sections)}/{actual_user_rounds} completed (attempt {attempt + 1}/{max_retries})")
            
            # 只有当所有轮次的section评估都完成时才生成完整报告
            if len(completed_sections) >= actual_user_rounds:
                print(f"[EvaluationOrchestrator] 🎯 All {actual_user_rounds} section evaluations completed, scheduling full report...")
                await session_manager.set_full_report_status(session_id, "processing")
                asyncio.create_task(generate_full_report_async(session_id))
                return  # 成功，退出重试循环
            else:
                print(f"[EvaluationOrchestrator] ⏳ Waiting for more section evaluations: {len(completed_sections)}/{actual_user_rounds}")
                if attempt < max_retries - 1:
                    print(f"[EvaluationOrchestrator] 🔄 Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"[EvaluationOrchestrator] ❌ Max retries reached, not all sections completed. Attempting to generate report with available sections...")
                    # 最后一次尝试：即使不是所有section都完成，也尝试生成报告
                    await session_manager.set_full_report_status(session_id, "processing")
                    asyncio.create_task(generate_full_report_async(session_id))
                    return
                
        except Exception as e:
            print(f"[EvaluationOrchestrator] ❌ Error checking section evaluation status (attempt {attempt + 1}/{max_retries}): {e}")
            import traceback
            traceback.print_exc()
            
            if attempt < max_retries - 1:
                print(f"[EvaluationOrchestrator] 🔄 Retrying in {retry_delay}s after error...")
                await asyncio.sleep(retry_delay)
            else:
                print(f"[EvaluationOrchestrator] ❌ Max retries reached after errors, giving up")
                # 设置失败状态
                try:
                    await session_manager.set_full_report_status(session_id, "failed", {"error": "Failed to check section evaluations after retries"})
                except:
                    pass


async def generate_full_report_async(session_id: str) -> None:
    """
    Phase 2: 基于所有section评估结果生成overall evaluation（面试结束时执行）
    使用已经存储的section evaluation结果中的文本部分缓存，同时刷新非语言部分（因为视频分析可能刚完成）
    """
    try:
        print(f"[EvaluationOrchestrator] 🔄 Starting overall evaluation for session {session_id}...")
        start_time = time.time()
        
        # 1. 获取最新的 Session 和 Timeline (确保包含最新的 nonverbal 数据)
        session = await session_manager.get_session(session_id)
        metadata = getattr(session, "metadata", {}) or {}
        language = metadata.get("language", "ja")
        
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        
        # 2. 重新构建 DialogSections (包含最新 nonverbal)
        request = build_eval_request_from_timeline(timeline_doc, language)
        raw_dialog = parse_eval_request(request)
        api = _get_two_phase_evaluation_api()
        if api is None:
            raise RuntimeError("Two-phase evaluation API unavailable (init failed).")

        dialog_sections = await api.build_sections(raw_dialog)
        
        if not dialog_sections:
            print(f"[EvaluationOrchestrator] ⚠️ No dialog sections built from timeline, cannot generate report")
            raise Exception("No dialog sections available")

        # 3. 获取已存储的section evaluations (作为缓存源)
        stored_section_evals = await session_manager.get_section_evaluations(session_id) or []
        stored_map = {
            item["section_index"]: item["section_result"] 
            for item in stored_section_evals 
            if item.get("status") == "completed" and item.get("section_result")
        }
        
        print(f"[EvaluationOrchestrator] 📊 Found {len(stored_map)} stored section evaluations to use as cache")

        # 4. 并行重新评估所有 Sections (复用文本反馈，刷新非语言反馈)
        async def _evaluate_single_section(section: Any) -> Any:
            """评估单个section的辅助函数，用于并行执行"""
            cached_feedback = {}
            
            # 尝试从存储的结果中提取文本维度的反馈
            stored_result = stored_map.get(section.section_index)
            if stored_result:
                # stored_result 可能是 Pydantic 对象或 Dict
                super_metrics = []
                if isinstance(stored_result, dict):
                    super_metrics = stored_result.get("super_metrics", [])
                elif hasattr(stored_result, "super_metrics"):
                    super_metrics = stored_result.super_metrics
                
                # 提取 feedback
                for sm in super_metrics:
                    # 处理 sm 可能是 Pydantic 对象或 Dict
                    sm_type = ""
                    sm_feedback_obj = None
                    
                    if isinstance(sm, dict):
                        metadata = sm.get("metadata", {})
                        sm_type = metadata.get("super_metric_type", "")
                        sm_feedback_obj = sm.get("feedback", {})
                    else:
                        sm_type = sm.metadata.super_metric_type.value
                        sm_feedback_obj = sm.feedback
                        
                    # 只缓存文本维度，跳过非语言维度以强制重新计算
                    # 注意：这里我们假设非语言维度的类型名称包含 VERBAL 或 VISUAL
                    if sm_type and "VERBAL" not in sm_type.upper() and "VISUAL" not in sm_type.upper():
                        # 提取反馈内容
                        feedback_dict = {}
                        if isinstance(sm_feedback_obj, dict):
                            feedback_dict = {
                                "brief_feedback": sm_feedback_obj.get("brief_feedback"),
                                "detailed_feedback": sm_feedback_obj.get("feedback"),
                                "revised_response": sm_feedback_obj.get("revised_response")
                            }
                        else:
                            feedback_dict = {
                                "brief_feedback": getattr(sm_feedback_obj, "brief_feedback", ""),
                                "detailed_feedback": getattr(sm_feedback_obj, "feedback", ""),
                                "revised_response": getattr(sm_feedback_obj, "revised_response", "")
                            }
                        
                        cached_feedback[sm_type.lower()] = feedback_dict
            
            # 如果提取到了缓存，打印日志
            if cached_feedback:
                print(f"[EvaluationOrchestrator] 🎯 Section {section.section_index}: Using cached text feedback, refreshing nonverbal...")
            else:
                print(f"[EvaluationOrchestrator] ⚠️ Section {section.section_index}: No cache found, full re-evaluation...")

            # 调用 evaluate_section (传入 cached_feedback)
            # API 会复用 cached_feedback 中的文本结果，并计算缺失的非语言结果
            section_result = await api.evaluate_section(
                section,
                user_id=None, # user_id 解析逻辑如果需要可以在这里加上，暂时传 None
                cached_feedback=cached_feedback
            )
            return section_result
        
        # ⚡ 并行执行所有section评估
        print(f"[EvaluationOrchestrator] 🚀 Starting parallel evaluation for {len(dialog_sections)} sections...")
        section_results = await asyncio.gather(*[
            _evaluate_single_section(section) for section in dialog_sections
        ])
        print(f"[EvaluationOrchestrator] ✅ All {len(section_results)} sections evaluated in parallel")

        if not section_results:
             print(f"[EvaluationOrchestrator] ⚠️ No valid section results generated")
             return

        # Phase 2: 生成overall evaluation
        evaluation_record = await api.evaluate_overall(section_results)
        response = pack_eval_response(evaluation_record, language=language)
        
        elapsed = time.time() - start_time
        print(f"[EvaluationOrchestrator] ✅ Overall evaluation completed in {elapsed:.2f}s")

        # First, expose the result to the in-memory session so the frontend can read it immediately
        await session_manager.set_full_report_status(
            session_id,
            "completed",
            response.model_dump(mode="json"),
        )
        
    except Exception as exc:
        print(f"[EvaluationOrchestrator] ✗ Full report generation failed: {exc}")
        import traceback
        traceback.print_exc()
        await session_manager.set_full_report_status(
            session_id,
            "failed",
            {"error": str(exc)},
        )


async def fallback_full_evaluation(session_id: str) -> None:
    """
    回退方案：如果没有存储的section evaluations，重新进行完整评估
    """
    try:
        print(f"[EvaluationOrchestrator] 🔄 Fallback: Re-evaluating all sections for session {session_id}...")
        start_time = time.time()
        
        session = await session_manager.get_session(session_id)
        metadata = getattr(session, "metadata", {}) or {}
        language = metadata.get("language", "ja")
        
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        request = build_eval_request_from_timeline(timeline_doc, language)
        raw_dialog = parse_eval_request(request)
        
        # 使用两阶段评估API重新构建sections并获取所有section结果
        api = _get_two_phase_evaluation_api()
        if api is None:
            raise RuntimeError("Two-phase evaluation API unavailable (init failed).")

        dialog_sections = await api.build_sections(raw_dialog)
        
        # 重新评估所有sections
        section_results = []
        for section in dialog_sections:
            section_result = await api.evaluate_section(section)
            section_results.append(section_result)
        
        # Phase 2: 生成overall evaluation
        evaluation_record = await api.evaluate_overall(section_results)
        response = pack_eval_response(evaluation_record, language=language)
        
        elapsed = time.time() - start_time
        print(f"[EvaluationOrchestrator] ✅ Fallback evaluation completed in {elapsed:.2f}s")

        # Immediately surface the result in the in-memory session
        await session_manager.set_full_report_status(
            session_id,
            "completed",
            response.model_dump(mode="json"),
        )
        
    except Exception as exc:
        print(f"[EvaluationOrchestrator] ✗ Fallback evaluation failed: {exc}")
        await session_manager.set_full_report_status(
            session_id,
            "failed",
            {"error": str(exc)},
        )


def build_eval_request_from_timeline(timeline_doc: Dict[str, Any], language: str = "ja") -> InterviewEvalRequest:
    """从timeline文档构建评估请求"""
    conversation = timeline_doc.get("conversation", []) or []
    items: List[InterviewDialogItem] = []

    for entry in conversation:
        timestamp_payload = entry.get("timestamp") or {"start": "0:00:00", "end": "0:00:00"}
        timestamp = InterviewTimestamp(**timestamp_payload)
        role = "agent" if entry.get("role") == "system" else "user"
        content = entry.get("content") or ""
        nonverbal_model = convert_nonverbal(entry.get("nonverbal")) if role == "user" else None
        raw_dimensions = entry.get("dimensions")
        if isinstance(raw_dimensions, list):
            target_dimensions = []
            for dim in raw_dimensions:
                if isinstance(dim, str):
                    normalized = dim.strip()
                    if normalized and normalized not in target_dimensions:
                        target_dimensions.append(normalized)
        else:
            target_dimensions = None

        items.append(
            InterviewDialogItem(
                timestamp=timestamp,
                role=role,
                content=content,
                nonverbal=nonverbal_model,
                target_dimensions=target_dimensions,
            )
        )

    return InterviewEvalRequest(interview=items, language=language)


def convert_nonverbal(raw: Any) -> Optional[NonverbalPerformance]:
    """转换非语言特征数据为schema格式"""
    if not isinstance(raw, dict):
        return None

    analysis = raw.get("analysis") or {}
    voice_src = analysis.get("voice") or raw.get("voice") or {}
    visual_src = analysis.get("visual") or raw.get("visual") or {}
    if not isinstance(voice_src, dict):
        voice_src = {}
    if not isinstance(visual_src, dict):
        visual_src = {}

    pause_value = voice_src.get("pause") or voice_src.get("pauses") or voice_src.get("pause_summary")

    # 辅助函数：将字典转换为字符串
    def _to_string(value: Any) -> Optional[str]:
        """将值转换为字符串，如果是字典则合并其内容"""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # 如果是字典，尝试提取关键字段并合并
            parts = []
            if "状態" in value:
                parts.append(f"状態: {value['状態']}")
            if "具体的な観察点" in value:
                parts.append(f"観察点: {value['具体的な観察点']}")
            if "改善提案" in value:
                parts.append(f"改善提案: {value['改善提案']}")
            # 如果没有上述字段，尝试提取所有字符串值
            if not parts:
                parts = [str(v) for v in value.values() if isinstance(v, str)]
            return " | ".join(parts) if parts else str(value)
        return str(value)

    voice = VoicePerformance(
        speed=voice_src.get("speed"),
        tone=voice_src.get("tone"),
        volume=voice_src.get("volume"),
        pronunciation=voice_src.get("pronunciation"),
        pause=pause_value,
        summary=voice_src.get("summary"),
        speed_score_label=voice_src.get("speed_score_label"),
        tone_score_label=voice_src.get("tone_score_label"),
        volume_score_label=voice_src.get("volume_score_label"),
        pronunciation_score_label=voice_src.get("pronunciation_score_label"),
        pause_score_label=voice_src.get("pause_score_label"),
    ) if any(voice_src.get(field) for field in ("speed", "tone", "volume", "pronunciation", "summary")) or pause_value else None

    # 转换 facial_expression：如果是字典则转换为字符串
    facial_expr = visual_src.get("facial_expression")
    facial_expr_str = _to_string(facial_expr)

    visual = VisualPerformance(
        eye_contact=visual_src.get("eye_contact"),
        facial_expression=facial_expr_str,
        body_posture=visual_src.get("body_posture"),
        appearance=visual_src.get("appearance"),
        summary=visual_src.get("summary"),
        eye_contact_score_label=visual_src.get("eye_contact_score_label"),
        facial_expression_score_label=visual_src.get("facial_expression_score_label"),
        body_posture_score_label=visual_src.get("body_posture_score_label"),
        appearance_score_label=visual_src.get("appearance_score_label"),
    ) if any(visual_src.get(field) for field in ("eye_contact", "facial_expression", "body_posture", "appearance", "summary")) or facial_expr_str else None

    if not voice and not visual:
        return None

    return NonverbalPerformance(
        voice_performance=voice,
        visual_performance=visual,
    )


