"""
Interview History Service
管理面试历史记录的查询和详情获取
"""
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.models.interview import Interview
from app.models.user import User


class InterviewHistoryService:
    """面试历史记录服务"""
    
    async def get_user_by_supabase_id(self, supabase_id: str, db: AsyncSession) -> Dict[str, Any]:
        """
        通过Supabase ID获取用户信息
        
        Args:
            supabase_id: Supabase Auth用户ID
            db: 数据库会话
            
        Returns:
            用户信息字典
            
        Raises:
            HTTPException: 用户不存在时抛出404
        """
        try:
            result = await db.execute(
                select(User).where(User.supabase_id == supabase_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            return {
                "id": str(user.id),
                "supabase_id": user.supabase_id,
                "email": user.email,
                "full_name": user.full_name,
                "avatar_url": user.avatar_url,
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"[HistoryService] ❌ Get user error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_interview_history(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        db: AsyncSession = None
    ) -> Dict[str, Any]:
        """
        获取用户的面试历史记录列表
        
        Args:
            user_id: 应用内部用户ID（users表的id字段）
            skip: 跳过的记录数（分页）
            limit: 返回的最大记录数
            db: 数据库会话
            
        Returns:
            面试历史列表字典（按完成时间倒序）
        """
        try:
            # ✅ IMPORTANT: History list must be fast.
            # Do NOT select large JSON columns (timeline / conversation_history / overall_eval),
            # otherwise Postgres may hit statement_timeout and the frontend will spin forever.
            result = await db.execute(
                select(
                    Interview.id,
                    Interview.session_id,
                    Interview.position,
                    Interview.mode,
                    Interview.status,
                    Interview.interview_type,
                    Interview.practice_category,
                    Interview.overall_score,
                    Interview.overall_feedback,
                    Interview.completed_at,
                    Interview.created_at,
                )
                .where(Interview.user_id == UUID(user_id))
                .where(Interview.status == "completed")
                .order_by(Interview.completed_at.desc())
                .offset(skip)
                .limit(limit)
            )
            rows = result.all()
            
            # 格式化返回数据
            history_list = []
            for row in rows:
                overall_score = row.overall_score if row.overall_score is not None else 0
                history_list.append({
                    "id": str(row.id),
                    "session_id": row.session_id,
                    "position": row.position or "面试练习",
                    "mode": row.mode,
                    "status": row.status,
                    "interview_type": row.interview_type,
                    "practice_category": row.practice_category,
                    "overall_score": overall_score,
                    "overall_feedback": row.overall_feedback,
                    # total_rounds used to be derived from timeline JSON; keep lightweight for list view
                    "total_rounds": None,
                    "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            
            return {
                "interviews": history_list,
                "total": len(history_list),
                "skip": skip,
                "limit": limit
            }
            
        except Exception as e:
            print(f"[HistoryService] ❌ Get history error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_interview_detail(
        self,
        interview_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        获取面试详情（用于结果页和履历详情页）
        
        Args:
            interview_id: 面试ID
            db: 数据库会话
            
        Returns:
            完整的面试数据，包括timeline、视频URLs、评估结果等
            
        Raises:
            HTTPException: 面试不存在时抛出404
        """
        try:
            # 查询面试记录
            result = await db.execute(
                select(Interview)
                .where(Interview.id == UUID(interview_id))
            )
            interview = result.scalar_one_or_none()
            
            if not interview:
                raise HTTPException(status_code=404, detail="Interview not found")
            
            # 构建详细数据
            timeline = interview.timeline or {}
            video_segments = interview.video_segments or {}
            fast_evaluations = interview.fast_evaluations or {}
            section_evaluations = interview.section_evaluations or []  # ✅ 获取section evaluations
            aggregated = interview.aggregated_evaluation or {}
            
            # 计算时长
            duration = 0
            if interview.completed_at and interview.started_at:
                duration = int((interview.completed_at - interview.started_at).total_seconds())
            
            # 统计问答轮数
            # 优先从 timeline 获取 conversation，如果没有则从 conversation_history 获取
            conversation = timeline.get("conversation", [])
            if not conversation and interview.conversation_history:
                conversation = interview.conversation_history.get("conversation", [])
            total_rounds = len([msg for msg in conversation if msg.get("role") == "user"])
            
            return {
                "id": str(interview.id),
                "session_id": interview.session_id,
                "user_id": str(interview.user_id),
                "mode": interview.mode,
                "status": interview.status,
                "interview_type": interview.interview_type,
                "practice_category": interview.practice_category,
                "position": interview.position,
                "duration": duration,
                "total_rounds": total_rounds,
                "started_at": interview.started_at.isoformat() if interview.started_at else None,
                "completed_at": interview.completed_at.isoformat() if interview.completed_at else None,
                "created_at": interview.created_at.isoformat(),
                "timeline": timeline,
                "video_segments": video_segments,  # ✅ 保持原始格式 {"segments": [...]}
                "fast_evaluations": fast_evaluations,
                "section_evaluations": section_evaluations,  # ✅ 返回 section evaluations
                "aggregated_evaluation": aggregated,
                "overall_eval": interview.overall_eval or {},  # ✅ 完整评估结果
                "dimension_scores": interview.dimension_scores or {},  # ✅ 六维评分
                "overall_score": interview.overall_score,  # ✅ 总评分
                "overall_feedback": interview.overall_feedback,  # ✅ 总评语
                "detailed_description": interview.detailed_description,  # ✅ 详细描述
                "conversation": conversation  # ✅ 确保返回 conversation
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"[HistoryService] ❌ Get interview detail error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def get_interview_by_session_id(
        self,
        session_id: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        通过session_id获取面试详情（用于视频回放页）
        
        Args:
            session_id: 会话ID
            db: 数据库会话
            
        Returns:
            完整的面试数据，包括timeline、视频URLs、评估结果等
            
        Raises:
            HTTPException: 面试不存在时抛出404
        """
        try:
            # 查询面试记录
            result = await db.execute(
                select(Interview)
                .where(Interview.session_id == session_id)
                .order_by(Interview.created_at.desc())  # 获取最新的记录
            )
            interview = result.scalar_one_or_none()
            
            if not interview:
                raise HTTPException(status_code=404, detail=f"Interview not found for session_id: {session_id}")
            
            # 构建详细数据
            timeline = interview.timeline or {}
            video_segments = interview.video_segments or {}
            section_evaluations = interview.section_evaluations or []  # ✅ 获取section evaluations
            
            # 提取video_urls - 从video_segments中获取
            video_urls = []
            if isinstance(video_segments, dict) and "segments" in video_segments:
                for segment in video_segments["segments"]:
                    if "url" in segment and segment["url"]:
                        video_urls.append(segment["url"])
            
            # 如果video_segments是数组格式（旧格式）
            elif isinstance(video_segments, list):
                for segment in video_segments:
                    if "url" in segment and segment["url"]:
                        video_urls.append(segment["url"])
            
            print(f"[HistoryService] 📹 Found {len(video_urls)} video URLs for session {session_id}")
            
            # 计算时长
            duration = 0
            if interview.completed_at and interview.started_at:
                duration = int((interview.completed_at - interview.started_at).total_seconds())
            
            # 统计问答轮数
            # 优先从 timeline 获取 conversation，如果没有则从 conversation_history 获取
            conversation = timeline.get("conversation", [])
            if not conversation and interview.conversation_history:
                conversation = interview.conversation_history.get("conversation", [])
            total_rounds = len([msg for msg in conversation if msg.get("role") == "user"])
            
            # 提取评分数据
            scores = {}
            if interview.dimension_scores:
                for dim_key, dim_data in interview.dimension_scores.items():
                    if isinstance(dim_data, dict) and "score" in dim_data:
                        scores[dim_key] = dim_data["score"]
                    elif isinstance(dim_data, (int, float)):
                        scores[dim_key] = dim_data
            
            return {
                "id": str(interview.id),
                "session_id": interview.session_id,
                "user_id": str(interview.user_id),
                "mode": interview.mode,
                "status": interview.status,
                "interview_type": interview.interview_type,
                "practice_category": interview.practice_category,
                "position": interview.position,
                "duration": duration,
                "total_rounds": total_rounds,
                "started_at": interview.started_at.isoformat() if interview.started_at else None,
                "completed_at": interview.completed_at.isoformat() if interview.completed_at else None,
                "created_at": interview.created_at.isoformat(),
                "video_urls": video_urls,  # 🎬 直接提供视频URLs数组
                "scores": scores,  # 📊 评分数据
                "conversation": conversation,  # 💬 会话履历（确保返回）
                "section_evaluations": section_evaluations,  # ✅ 返回 section evaluations
                "overall_score": interview.overall_score,
                "overall_feedback": interview.overall_feedback,
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"[HistoryService] ❌ Get interview by session error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    async def save_interview_to_db(
        self,
        session_id: str,
        user_id: str,
        position: Optional[str],
        role: str,
        timeline_doc: Dict[str, Any],
        db: AsyncSession,
        interview_type: str = "practice",
        practice_category: Optional[str] = None,
        video_urls: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        保存面试记录到数据库 (支持 Upsert: 如果存在则更新，不存在则创建)
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            position: 职位名称
            role: 面试角色
            timeline_doc: timeline文档
            db: 数据库会话
            interview_type: 面试类型（practice=练习模式, corporate=职场测试）
            practice_category: 练习分类（basic/advanced）
            video_urls: 视频URLs列表（从Supabase Storage）
            
        Returns:
            保存结果字典
        """
        try:
            # 1. Check if interview already exists
            existing_result = await db.execute(
                select(Interview).where(Interview.session_id == session_id)
            )
            existing_interview = existing_result.scalar_one_or_none()

            # 收集所有视频URLs - 优先使用传入的video_urls
            video_segments = []
            if video_urls:
                print(f"[HistoryService] Using provided video URLs: {len(video_urls)} URLs")
                for idx, url in enumerate(video_urls):
                    # Skip placeholders / invalid values (prevents "skipped" breaking playback)
                    if not isinstance(url, str) or not url.startswith("http"):
                        continue
                    video_segments.append({
                        "url": url,
                        "segment_index": idx,
                        "timestamp": {},
                        "duration": 0
                    })
            else:
                # 回退：从timeline_doc提取视频URLs
                print(f"[HistoryService] Extracting video URLs from timeline_doc")
                for item in timeline_doc.get("conversation", []):
                    if item.get("role") == "user" and item.get("nonverbal", {}).get("video_url"):
                        url = item["nonverbal"]["video_url"]
                        if not isinstance(url, str) or not url.startswith("http"):
                            continue
                        video_segments.append({
                            "url": url,
                            "timestamp": item.get("timestamp", {}),
                            "duration": item.get("nonverbal", {}).get("duration", 0)
                        })
            
            # 计算面试时长
            conversation = timeline_doc.get("conversation", [])
            print(f"[HistoryService] 📝 Conversation count in timeline_doc: {len(conversation)}")
            if len(conversation) == 0:
                print(f"[HistoryService] ⚠️  WARNING: timeline_doc has no conversation!")
                print(f"[HistoryService]    timeline_doc keys: {list(timeline_doc.keys())}")
            interview_duration = 300  # 默认5分钟
            if len(conversation) > 0:
                # 简单估算：每条用户消息60秒
                interview_duration = len([msg for msg in conversation if msg.get("role") == "user"]) * 60
            
            # 获取实际的开始和结束时间
            now = datetime.utcnow()
            started_at = now  # TODO: 从session获取实际开始时间
            completed_at = now
            
            # 从session manager获取overall_eval（如果有）
            from app.services.interview_session_manager import session_manager
            overall_eval_data = None
            section_evals = []
            try:
                overall_eval_data = await session_manager.get_full_report(session_id)
                raw_section_evals = await session_manager.get_section_evaluations(session_id)
                
                # 序列化 SectionEvaluationResult 对象为字典（mode='json' 确保枚举等都被序列化）
                for eval_item in raw_section_evals:
                    if isinstance(eval_item, dict):
                        section_result = eval_item.get("section_result")
                        if section_result and hasattr(section_result, "model_dump"):
                            eval_item["section_result"] = section_result.model_dump(mode='json')
                        section_evals.append(eval_item)
                    
            except Exception as e:
                print(f"[HistoryService] ⚠️ Failed to get eval data from session: {e}")
            
            # 提取评分信息
            dimension_scores = None
            overall_score = None
            overall_feedback = None
            detailed_description = None
            
            if overall_eval_data and isinstance(overall_eval_data, dict):
                data = overall_eval_data.get("data", overall_eval_data)
                
                # 提取总分和总评语
                if "overall" in data:
                    overall_info = data["overall"]
                    overall_score = overall_info.get("score")
                    overall_feedback = overall_info.get("label", "")
                
                # 提取六维评分
                dimension_keys = ["clarity", "evidence", "impact", "engagement", "verbal_performance", "visual_performance"]
                dimensions = {}
                detailed_parts = []
                
                for dim_key in dimension_keys:
                    if dim_key in data:
                        dim_data = data[dim_key]
                        # 获取feedback或description字段（优先使用feedback）
                        feedback = dim_data.get("feedback", "") or dim_data.get("description", "")
                        dimensions[dim_key] = {
                            "score": dim_data.get("score"),
                            "label": dim_data.get("label"),
                            "brief": dim_data.get("brief", ""),
                            "feedback": feedback  # ✅ 保存详细反馈字段
                        }
                        
                        # 收集详细反馈用于detailed_description
                        if feedback:
                            dim_name_map = {
                                "clarity": "明確さ",
                                "evidence": "論拠",
                                "impact": "影響力",
                                "engagement": "参与度",
                                "verbal_performance": "言語表現",
                                "visual_performance": "視覚表現"
                            }
                            dim_name = dim_name_map.get(dim_key, dim_key)
                            detailed_parts.append(f"【{dim_name}】\n{feedback}")
                
                if dimensions:
                    dimension_scores = dimensions
                
                if detailed_parts:
                    detailed_description = "\n\n".join(detailed_parts)
            
            # 确保 timeline_doc 包含 conversation（如果缺失则添加）
            if "conversation" not in timeline_doc or not timeline_doc.get("conversation"):
                print(f"[HistoryService] ⚠️  timeline_doc missing conversation, adding from conversation_history")
                timeline_doc["conversation"] = conversation
            
            if existing_interview:
                print(f"[HistoryService] 🔄 Updating existing interview: {existing_interview.id}")
                # Update existing fields
                existing_interview.timeline = timeline_doc
                existing_interview.video_segments = {"segments": video_segments}
                existing_interview.fast_evaluations = {"evaluations": timeline_doc.get("evaluations", [])}
                existing_interview.section_evaluations = {"evaluations": section_evals}
                existing_interview.aggregated_evaluation = timeline_doc.get("aggregated_evaluation", {})
                existing_interview.overall_eval = overall_eval_data
                existing_interview.conversation_history = {"conversation": conversation}
                existing_interview.dimension_scores = dimension_scores
                existing_interview.overall_score = overall_score
                existing_interview.overall_feedback = overall_feedback
                existing_interview.detailed_description = detailed_description
                existing_interview.completed_at = completed_at
                # Update optional fields if provided
                if position:
                    existing_interview.position = position
                if practice_category:
                    existing_interview.practice_category = practice_category
                
                # Check for user_id mismatch (should not happen in normal flow)
                if str(existing_interview.user_id) != str(user_id):
                     print(f"[HistoryService] ⚠️ User ID mismatch on update! Existing: {existing_interview.user_id}, New: {user_id}")
                
                await db.commit()
                await db.refresh(existing_interview)
                interview = existing_interview
            else:
                # 创建interview记录
                interview = Interview(
                    user_id=UUID(user_id),
                    session_id=session_id,
                    mode="practice",  # 流式面试固定为practice模式
                    status="completed",
                    interview_type=interview_type,
                    practice_category=practice_category,
                    position=position or role,
                    duration=interview_duration,
                    timeline=timeline_doc,  # ✅ 确保 timeline 包含 conversation
                    video_segments={"segments": video_segments},
                    fast_evaluations={"evaluations": timeline_doc.get("evaluations", [])},
                    section_evaluations={"evaluations": section_evals},  # ✅ 保存 section evaluations
                    aggregated_evaluation=timeline_doc.get("aggregated_evaluation", {}),
                    overall_eval=overall_eval_data,
                    conversation_history={"conversation": conversation},  # ✅ 同时保存到 conversation_history 作为备份
                    dimension_scores=dimension_scores,
                    overall_score=overall_score,
                    overall_feedback=overall_feedback,
                    detailed_description=detailed_description,
                    started_at=started_at,
                    completed_at=completed_at
                )
                
                print(f"[HistoryService] 💾 Creating new interview with {len(conversation)} conversation items")
                db.add(interview)
                try:
                    await db.commit()
                    await db.refresh(interview)
                except IntegrityError as ie:
                    # ✅ Concurrency safety:
                    # Another request may have created the same session_id between our SELECT and INSERT.
                    # Rollback, then update the existing row instead of failing the whole request.
                    await db.rollback()
                    print(f"[HistoryService] ⚠️ Insert conflict on session_id={session_id}, retrying as update: {ie}")
                    existing_result = await db.execute(
                        select(Interview).where(Interview.session_id == session_id)
                    )
                    existing_interview = existing_result.scalar_one_or_none()
                    if not existing_interview:
                        raise
                    print(f"[HistoryService] 🔄 Updating existing interview after conflict: {existing_interview.id}")
                    existing_interview.timeline = timeline_doc
                    existing_interview.video_segments = {"segments": video_segments}
                    existing_interview.fast_evaluations = {"evaluations": timeline_doc.get("evaluations", [])}
                    existing_interview.section_evaluations = {"evaluations": section_evals}
                    existing_interview.aggregated_evaluation = timeline_doc.get("aggregated_evaluation", {})
                    existing_interview.overall_eval = overall_eval_data
                    existing_interview.conversation_history = {"conversation": conversation}
                    existing_interview.dimension_scores = dimension_scores
                    existing_interview.overall_score = overall_score
                    existing_interview.overall_feedback = overall_feedback
                    existing_interview.detailed_description = detailed_description
                    existing_interview.completed_at = completed_at
                    if position:
                        existing_interview.position = position
                    if practice_category:
                        existing_interview.practice_category = practice_category
                    await db.commit()
                    await db.refresh(existing_interview)
                    interview = existing_interview
            
            print(f"[HistoryService] ✅ Saved to database: interview_id={interview.id}")
            
            return {
                "status": "completed",
                "interview_id": str(interview.id),
                "session_id": session_id,
                "timeline": timeline_doc
            }
            
        except Exception as db_error:
            print(f"[HistoryService] ❌ Database save error: {db_error}")
            import traceback
            traceback.print_exc()
            try:
                await db.rollback()
            except Exception:
                pass
            # 返回警告但不抛出异常
            return {
                "status": "completed",
                "session_id": session_id,
                "timeline": timeline_doc,
                "warning": "Failed to save to database"
            }


# 全局单例
interview_history_service = InterviewHistoryService()
