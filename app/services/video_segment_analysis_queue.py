"""
Video segment analysis queue (MVP)

Purpose:
- Accept a Supabase video URL per segment
- Download to local temp file
- Run existing OpenCV frame extraction + unified evaluation pipeline
- Ensure idempotency and cross-instance mutual exclusion via Redis

Notes:
- This is a best-effort in-process scheduler. For stronger guarantees, replace the
  "asyncio.create_task" scheduling with Cloud Tasks / PubSub.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import httpx

from app.core.redis import redis_client
from app.core.config import settings
from app.services.interview_video_processor import process_video_async
from app.services.interview_session_manager import session_manager


def _analysis_key(session_id: str, segment_index: int) -> str:
    return f"{session_id}:{segment_index}"


def _status_key(session_id: str, segment_index: int) -> str:
    return f"careerface:video_analysis_status:{_analysis_key(session_id, segment_index)}"


def _job_key(session_id: str, segment_index: int) -> str:
    return f"careerface:video_analysis_job:{_analysis_key(session_id, segment_index)}"


def _lock_key(session_id: str, segment_index: int) -> str:
    return f"careerface:lock:video_analysis:{_analysis_key(session_id, segment_index)}"


def _redis_enabled() -> bool:
    return getattr(settings, "SESSION_STORE", "memory") == "redis" and getattr(redis_client, "redis", None) is not None


_CONCURRENCY = int(os.getenv("VIDEO_ANALYSIS_CONCURRENCY_PER_INSTANCE", "1"))
_SEMAPHORE = asyncio.Semaphore(max(1, _CONCURRENCY))


@dataclass(frozen=True)
class VideoSegmentJob:
    session_id: str
    segment_index: int
    segment_url: str
    duration: float
    transcript: str = ""
    language: str = "ja"


async def _set_status(session_id: str, segment_index: int, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
    if not _redis_enabled():
        return
    payload: Dict[str, Any] = {
        "session_id": session_id,
        "segment_index": segment_index,
        "status": status,
        "updated_at": int(time.time()),
    }
    if extra:
        payload.update(extra)
    await redis_client.set(_status_key(session_id, segment_index), json.dumps(payload, ensure_ascii=False), expire=60 * 60 * 24 * 2)


async def get_status(session_id: str, segment_index: int) -> Optional[Dict[str, Any]]:
    if not _redis_enabled():
        return None
    raw = await redis_client.get(_status_key(session_id, segment_index))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def enqueue(job: VideoSegmentJob) -> Tuple[bool, str]:
    """
    Enqueue analysis. Returns (queued, status).
    Status is one of: queued | running | done | skipped | error
    """
    if _redis_enabled():
        existing = await get_status(job.session_id, job.segment_index)
        if existing and existing.get("status") == "done":
            return False, "skipped"

        # Persist job payload for later visibility/debug
        await redis_client.set(
            _job_key(job.session_id, job.segment_index),
            json.dumps(job.__dict__, ensure_ascii=False),
            expire=60 * 60 * 24 * 2,
        )
        await _set_status(job.session_id, job.segment_index, "queued")

    # Best-effort local scheduling
    asyncio.create_task(_run_job(job))
    return True, "queued"


async def _download_to_path(url: str, dst_path: str, *, timeout_sec: float = 60.0) -> None:
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dst_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)


async def _run_job(job: VideoSegmentJob) -> None:
    lock_token: Optional[str] = None
    tmp_path: Optional[str] = None
    try:
        async with _SEMAPHORE:
            if _redis_enabled():
                lock_token = uuid4().hex
                ok = await redis_client.set_if_not_exists(_lock_key(job.session_id, job.segment_index), lock_token, expire=60 * 30)
                if not ok:
                    # Another instance is running this segment
                    await _set_status(job.session_id, job.segment_index, "running", {"note": "locked_by_other_instance"})
                    return

            await _set_status(job.session_id, job.segment_index, "running")

            # Download to /tmp (Cloud Run) or backend/temp_videos (local)
            base_dir = "/tmp" if os.name != "nt" else os.path.join(os.getcwd(), "temp_videos")
            tmp_path = os.path.join(base_dir, f"video_{job.session_id}_{job.segment_index}_{uuid4().hex}.mp4")
            await _download_to_path(job.segment_url, tmp_path)

            # If transcript is not provided yet, try to fetch it from session timeline (best-effort).
            transcript = job.transcript or ""
            if not transcript:
                for _ in range(20):  # up to ~10s
                    try:
                        transcript = await session_manager.get_segment_transcript(job.session_id, job.segment_index) or ""
                    except Exception:
                        transcript = ""
                    if transcript:
                        break
                    await asyncio.sleep(0.5)

            # Reuse existing processing pipeline (will update session timeline + cleanup video)
            await process_video_async(
                session_id=job.session_id,
                video_path=tmp_path,
                user_text=transcript,
                duration=float(job.duration or 0.0),
                segment_index=int(job.segment_index),
                realtime_hint=None,
                language=job.language or "ja",
            )

            await _set_status(job.session_id, job.segment_index, "done")

    except Exception as e:
        await _set_status(
            job.session_id,
            job.segment_index,
            "error",
            {"error": str(e)[:500]},
        )
        # Best-effort cleanup if process_video_async didn't
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    finally:
        if lock_token and _redis_enabled():
            try:
                await redis_client.delete_if_value_matches(_lock_key(job.session_id, job.segment_index), lock_token)
            except Exception:
                pass


