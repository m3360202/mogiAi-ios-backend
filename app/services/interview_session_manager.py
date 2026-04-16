"""
Interview session manager: holds realtime session params, timeline, and state.
This is a minimal in-memory implementation to unblock frontend integration.

Notes:
- For production, replace in-memory store with DB persistence.
- GLM realtime bridge is pluggable via adapter (not implemented here).
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.config import settings
from app.core.redis import redis_client


@dataclass
class TimelineItem:
    timestamp: Dict[str, str]
    role: str
    content: str
    nonverbal: Optional[Dict[str, Any]] = None
    dimensions: Optional[List[str]] = None


@dataclass
class InterviewSession:
    session_id: str
    role: str
    system_message: str
    persona: Dict[str, Any] = field(default_factory=dict)
    style: str = "neutral"  # gentle | stern | neutral
    preset_prompts: List[str] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=dict)
    timeline: List[TimelineItem] = field(default_factory=list)
    created_at_sec: float = 0.0
    tts_voice: str = "alloy"
    fast_evaluations: List[Dict[str, Any]] = field(default_factory=list)
    section_evaluations: List[Dict[str, Any]] = field(default_factory=list)  # Two-phase evaluation section results
    aggregated_evaluation: Optional[Dict[str, Any]] = None
    full_report: Optional[Dict[str, Any]] = None
    full_report_status: str = "pending"  # pending | processing | completed | failed
    metadata: Dict[str, Any] = field(default_factory=dict)
    # bookkeeping for current segment
    _seg_start_sec: Optional[float] = None
    _seg_role: Optional[str] = None
    _seg_text_buf: List[str] = field(default_factory=list)
    _seg_nonverbal_buf: List[Dict[str, Any]] = field(default_factory=list)


class InterviewSessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, InterviewSession] = {}
        self._lock = asyncio.Lock()

    def _redis_enabled(self) -> bool:
        return getattr(settings, "SESSION_STORE", "memory") == "redis" and getattr(redis_client, "redis", None) is not None

    def _session_key(self, session_id: str) -> str:
        prefix = getattr(settings, "SESSION_KEY_PREFIX", "careerface:interview_session:")
        return f"{prefix}{session_id}"

    def _session_lock_key(self, session_id: str) -> str:
        return f"careerface:lock:interview_session:{session_id}"

    async def _acquire_session_lock(self, session_id: str, *, ttl_sec: int = 30) -> Optional[str]:
        """
        Acquire a coarse Redis lock for session mutation across Cloud Run instances.
        Returns lock token if acquired, else None.
        """
        if not self._redis_enabled():
            return None
        token = uuid4().hex
        # Best-effort retry to reduce races when Cloud Run hits multiple instances.
        for _ in range(10):
            ok = await redis_client.set_if_not_exists(self._session_lock_key(session_id), token, expire=ttl_sec)
            if ok:
                return token
            await asyncio.sleep(0.05)
        return None

    async def _release_session_lock(self, session_id: str, token: Optional[str]) -> None:
        if not token or not self._redis_enabled():
            return
        try:
            await redis_client.delete_if_value_matches(self._session_lock_key(session_id), token)
        except Exception:
            # best-effort
            return

    def _timeline_item_to_dict(self, ti: TimelineItem) -> Dict[str, Any]:
        return {
            "timestamp": ti.timestamp,
            "role": ti.role,
            "content": ti.content,
            "nonverbal": ti.nonverbal,
            "dimensions": ti.dimensions,
        }

    def _timeline_item_from_dict(self, d: Dict[str, Any]) -> TimelineItem:
        return TimelineItem(
            timestamp=d.get("timestamp") or {},
            role=d.get("role") or "",
            content=d.get("content") or "",
            nonverbal=d.get("nonverbal"),
            dimensions=d.get("dimensions"),
        )

    def _session_to_dict(self, s: InterviewSession) -> Dict[str, Any]:
        return {
            "session_id": s.session_id,
            "role": s.role,
            "system_message": s.system_message,
            "persona": s.persona,
            "style": s.style,
            "preset_prompts": s.preset_prompts,
            "thresholds": s.thresholds,
            "timeline": [self._timeline_item_to_dict(ti) for ti in s.timeline],
            "created_at_sec": s.created_at_sec,
            "tts_voice": s.tts_voice,
            "fast_evaluations": s.fast_evaluations,
            "section_evaluations": s.section_evaluations,
            "aggregated_evaluation": s.aggregated_evaluation,
            "full_report": s.full_report,
            "full_report_status": s.full_report_status,
            "metadata": s.metadata,
            "_seg_start_sec": s._seg_start_sec,
            "_seg_role": s._seg_role,
            "_seg_text_buf": s._seg_text_buf,
            "_seg_nonverbal_buf": s._seg_nonverbal_buf,
        }

    def _session_from_dict(self, d: Dict[str, Any]) -> InterviewSession:
        s = InterviewSession(
            session_id=d.get("session_id") or "",
            role=d.get("role") or "",
            system_message=d.get("system_message") or "",
            persona=d.get("persona") or {},
            style=d.get("style") or "neutral",
            preset_prompts=d.get("preset_prompts") or [],
            thresholds=d.get("thresholds") or {},
            tts_voice=d.get("tts_voice") or "alloy",
            metadata=d.get("metadata") or {},
        )
        s.timeline = [self._timeline_item_from_dict(x) for x in (d.get("timeline") or [])]
        s.created_at_sec = float(d.get("created_at_sec") or 0.0)
        s.fast_evaluations = d.get("fast_evaluations") or []
        s.section_evaluations = d.get("section_evaluations") or []
        s.aggregated_evaluation = d.get("aggregated_evaluation")
        s.full_report = d.get("full_report")
        s.full_report_status = d.get("full_report_status") or "pending"
        s._seg_start_sec = d.get("_seg_start_sec")
        s._seg_role = d.get("_seg_role")
        s._seg_text_buf = d.get("_seg_text_buf") or []
        s._seg_nonverbal_buf = d.get("_seg_nonverbal_buf") or []
        return s

    async def _persist_session(self, s: InterviewSession) -> None:
        if not self._redis_enabled():
            return
        try:
            payload = json.dumps(self._session_to_dict(s), ensure_ascii=False)
            await redis_client.set(
                self._session_key(s.session_id),
                payload,
                expire=int(getattr(settings, "SESSION_TTL_SECONDS", 7200)),
            )
        except Exception:
            # best-effort persistence; in-memory still works
            return

    async def _get_or_load_session(self, session_id: str) -> InterviewSession:
        s = self._sessions.get(session_id)
        if s is not None:
            return s
        if self._redis_enabled():
            raw = await redis_client.get(self._session_key(session_id))
            if raw:
                try:
                    d = json.loads(raw)
                    s = self._session_from_dict(d)
                    self._sessions[session_id] = s
                    return s
                except Exception:
                    # fallthrough to KeyError
                    pass
        raise KeyError(session_id)
    
    @property
    def sessions(self) -> Dict[str, InterviewSession]:
        """Direct access to sessions dict (use with caution, prefer async methods)"""
        return self._sessions

    async def start_session(
        self,
        role: str,
        system_message: str,
        persona: Optional[Dict[str, Any]] = None,
        style: str = "neutral",
        preset_prompts: Optional[List[str]] = None,
        thresholds: Optional[Dict[str, float]] = None,
        *,
        tts_voice: str = "alloy",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InterviewSession:
        async with self._lock:
            sid = uuid4().hex
            sess = InterviewSession(
                session_id=sid,
                role=role,
                system_message=system_message,
                persona=persona or {},
                style=style,
                preset_prompts=preset_prompts or [],
                thresholds=thresholds or {},
                tts_voice=tts_voice,
                metadata=metadata or {},
            )
            self._sessions[sid] = sess
            sess.created_at_sec = time.time()
            await self._persist_session(sess)
            return sess

    async def update_params(
        self,
        session_id: str,
        *,
        style: Optional[str] = None,
        preset_prompts: Optional[List[str]] = None,
        persona_delta: Optional[Dict[str, Any]] = None,
        thresholds: Optional[Dict[str, float]] = None,
        tts_voice: Optional[str] = None,
    ) -> InterviewSession:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                sess = await self._get_or_load_session(session_id)
                if style:
                    sess.style = style
                if preset_prompts is not None:
                    sess.preset_prompts = preset_prompts
                if persona_delta:
                    sess.persona.update(persona_delta)
                if thresholds:
                    sess.thresholds.update(thresholds)
                if tts_voice:
                    sess.tts_voice = tts_voice
                await self._persist_session(sess)
                return sess
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def update_session_metadata(
        self,
        session_id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """Update session metadata"""
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                sess = await self._get_or_load_session(session_id)
                sess.metadata.update(metadata)
                await self._persist_session(sess)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def update_unified_feedback(
        self,
        session_id: str,
        segment_index: int,
        feedback_data: Dict[str, Any]
    ) -> None:
        """Update unified feedback for a specific segment in session metadata"""
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                if "unified_feedback" not in s.metadata:
                    s.metadata["unified_feedback"] = {}

                # Update specific segment feedback
                segment_key = f"segment_{segment_index}"
                s.metadata["unified_feedback"][segment_key] = feedback_data
                await self._persist_session(s)
                print(f"[SessionManager] Updated unified feedback for {segment_key}")
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def get_session(self, session_id: str) -> InterviewSession:
        async with self._lock:
            return await self._get_or_load_session(session_id)

    async def get_timeline_doc(self, session_id: str) -> Dict[str, Any]:
        async with self._lock:
            s = await self._get_or_load_session(session_id)
            return {
                "interview_session_id": s.session_id,
                "role": s.role,
                "system_message": s.system_message,
                "conversation": [
                    {
                        "timestamp": ti.timestamp,
                        "role": ti.role,
                        "content": ti.content,
                        "nonverbal": ti.nonverbal or {},
                        "dimensions": ti.dimensions or [],
                    }
                    for ti in s.timeline
                ],
                "evaluations": s.fast_evaluations,
                "aggregated_evaluation": s.aggregated_evaluation,
                "full_report_status": s.full_report_status,
            }

    async def seg_start(self, session_id: str, start_sec: float, role: str = "user") -> None:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s._seg_start_sec = start_sec
                s._seg_role = role
                s._seg_text_buf.clear()
                s._seg_nonverbal_buf.clear()
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def seg_append_text(self, session_id: str, text_delta: str) -> None:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s._seg_text_buf.append(text_delta)
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def seg_append_nonverbal(self, session_id: str, feat: Dict[str, Any]) -> None:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s._seg_nonverbal_buf.append(feat)
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def seg_commit(
        self,
        session_id: str,
        end_sec: float,
        dimensions: Optional[List[str]] = None,
    ) -> Optional[TimelineItem]:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                if s._seg_start_sec is None:
                    return None
                text = "".join(s._seg_text_buf).strip()
                nonverbal = self._aggregate_nonverbal(s._seg_nonverbal_buf)
                dims_value: Optional[List[str]] = None
                if dimensions:
                    dims_value = [d for d in dimensions if isinstance(d, str) and d.strip()]
                    if not dims_value:
                        dims_value = None
                item = TimelineItem(
                    timestamp={
                        "start": self._fmt_hhmmss(s._seg_start_sec or 0.0),
                        "end": self._fmt_hhmmss(end_sec),
                    },
                    role=s._seg_role or "user",
                    content=text,
                    nonverbal=nonverbal,
                    dimensions=dims_value,
                )
                s.timeline.append(item)
                # reset segment buffers
                s._seg_start_sec = None
                s._seg_role = None
                s._seg_text_buf.clear()
                s._seg_nonverbal_buf.clear()
                await self._persist_session(s)
                return item
        finally:
            await self._release_session_lock(session_id, lock_token)

    def _aggregate_nonverbal(self, feats: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not feats:
            return {}
        # Minimal aggregation: compute simple means/counts if present
        eye_hits = 0
        smile_hits = 0
        frames = 0
        for f in feats:
            frames += 1
            eye_hits += 1 if f.get("eye_contact", False) else 0
            smile_hits += 1 if f.get("smile", False) else 0
        eye_rate = eye_hits / frames if frames else 0.0
        smile_rate = smile_hits / frames if frames else 0.0
        return {
            "expression": {"smile_rate": round(smile_rate, 2)},
            "gaze": {"eye_contact_rate": round(eye_rate, 2)},
        }

    def _fmt_hhmmss(self, sec: float) -> str:
        sec = max(0.0, float(sec))
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        return f"{h}:{m:02d}:{s:02d}"
    
    async def update_segment_nonverbal(
        self, 
        session_id: str, 
        segment_index: int, 
        nonverbal_data: Dict[str, Any]
    ) -> None:
        """更新指定 segment 的 nonverbal 数据（用于异步视频处理完成后更新）"""
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                # 找到用户回答的 segments
                user_segments = [i for i, ti in enumerate(s.timeline) if ti.role == "user"]
                if segment_index < len(user_segments):
                    actual_index = user_segments[segment_index]
                    if s.timeline[actual_index].nonverbal:
                        s.timeline[actual_index].nonverbal.update(nonverbal_data)
                    else:
                        s.timeline[actual_index].nonverbal = nonverbal_data
                    await self._persist_session(s)
                    print(f"[SessionManager] Updated segment {segment_index} nonverbal data")
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def update_segment_dimensions(
        self,
        session_id: str,
        segment_index: int,
        dimensions: List[str],
    ) -> None:
        """更新指定 segment 的目标维度数据"""
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                user_segments = [i for i, ti in enumerate(s.timeline) if ti.role == "user"]
                if segment_index < len(user_segments):
                    actual_index = user_segments[segment_index]
                    s.timeline[actual_index].dimensions = dimensions
                    await self._persist_session(s)
                    print(f"[SessionManager] Updated segment {segment_index} dimensions: {dimensions}")
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def add_fast_evaluation(
        self,
        session_id: str,
        evaluation_payload: Dict[str, Any],
    ) -> None:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s.fast_evaluations.append(evaluation_payload)
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def add_section_evaluation(
        self,
        session_id: str,
        section_result: Dict[str, Any],
    ) -> None:
        """Store section evaluation result from two-phase evaluation system"""
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s.section_evaluations.append(section_result)
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def get_section_evaluations(
        self,
        session_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all stored section evaluation results"""
        async with self._lock:
            try:
                s = await self._get_or_load_session(session_id)
            except KeyError:
                return []
            return s.section_evaluations

    async def set_aggregated_evaluation(
        self,
        session_id: str,
        aggregated: Dict[str, Any],
    ) -> None:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s.aggregated_evaluation = aggregated
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def set_full_report_status(
        self,
        session_id: str,
        status: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                s.full_report_status = status
                if payload is not None:
                    s.full_report = payload
                await self._persist_session(s)
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def get_full_report(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        async with self._lock:
            try:
                s = await self._get_or_load_session(session_id)
            except KeyError:
                return None
            return s.full_report
    
    async def check_analysis_complete(self, session_id: str) -> Dict[str, Any]:
        """检查所有用户回答的视频分析是否完成"""
        async with self._lock:
            try:
                s = await self._get_or_load_session(session_id)
            except KeyError:
                return {"complete": False, "error": "Session not found"}
            
            user_segments = [ti for ti in s.timeline if ti.role == "user"]
            total = len(user_segments)
            
            if total == 0:
                return {"complete": True, "total": 0, "analyzed": 0}
            
            analyzed = 0
            uploaded = 0
            for seg in user_segments:
                # 检查是否有 nonverbal.analysis 数据
                if seg.nonverbal and seg.nonverbal.get("analysis"):
                    analyzed += 1
                # 检查是否有 video_url
                if seg.nonverbal and seg.nonverbal.get("video_url"):
                    uploaded += 1
            
            complete = (analyzed == total)
            upload_complete = (uploaded == total)
            print(f"[SessionManager] Analysis status: {analyzed}/{total}, Upload status: {uploaded}/{total}")
            
            return {
                "complete": complete,
                "upload_complete": upload_complete,
                "total": total,
                "analyzed": analyzed,
                "uploaded": uploaded,
                "pending": total - analyzed
            }

    async def update_segment_video_url(
        self,
        session_id: str,
        segment_index: int,
        video_url: str
    ) -> None:
        """更新指定 segment 的 video_url"""
        lock_token: Optional[str] = None
        try:
            lock_token = await self._acquire_session_lock(session_id)
            async with self._lock:
                s = await self._get_or_load_session(session_id)
                user_segments = [i for i, ti in enumerate(s.timeline) if ti.role == "user"]
                if segment_index < len(user_segments):
                    actual_index = user_segments[segment_index]
                    if s.timeline[actual_index].nonverbal:
                        s.timeline[actual_index].nonverbal["video_url"] = video_url
                    else:
                        s.timeline[actual_index].nonverbal = {"video_url": video_url}
                    await self._persist_session(s)
                    print(f"[SessionManager] Updated segment {segment_index} video_url: {video_url}")
        finally:
            await self._release_session_lock(session_id, lock_token)

    async def get_segment_transcript(self, session_id: str, segment_index: int) -> Optional[str]:
        """
        获取指定 segment 的文本（用于视频后传时的补救分析）
        """
        async with self._lock:
            try:
                s = await self._get_or_load_session(session_id)
            except KeyError:
                return None
            
            user_segments = [ti for ti in s.timeline if ti.role == "user"]
            if segment_index < len(user_segments):
                return user_segments[segment_index].content
            return None


# singleton
session_manager = InterviewSessionManager()


