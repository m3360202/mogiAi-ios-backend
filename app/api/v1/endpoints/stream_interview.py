"""
Stream Interview API - 优化的流式面试接口
支持：
1. 流式问题生成 (NDJSON)
2. 异步视频分析 (GLM-4.5V)
3. 流式 TTS
4. 实时多维度评估
"""
import asyncio
import json
import os
import random
import re
import tempfile
import time
import shutil
from typing import AsyncGenerator, Optional, Dict, Any, List
from enum import Enum
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.audio_chunk_buffer import audio_chunk_buffer
from app.services.video_chunk_buffer import video_chunk_buffer
from app.services.deepseek_interview_service import DeepseekInterviewService
from app.services.interview_session_manager import session_manager
from app.services.interview_params_service import interview_params_service

# 新的服务层导入
from app.services.interview_streaming_helper import (
    ndj, log, get_tts_format, stream_question_tts,
    extract_latest_question, compose_nonverbal_snapshot
)
from app.services.interview_task_queue_service import section_task_queue
from app.services.interview_video_processor import process_video_async, analyze_chunk_async
from app.services.interview_evaluation_orchestrator import (
    evaluate_section_async, build_eval_request_from_timeline
)
from app.services.evaluation.public.two_phase_evaluation_api import TwoPhaseEvaluationAPIImpl
from app.services.evaluation.services.adapters import parse_eval_request
from app.services.fast_text_feedback_service import generate_text_feedback_cached
from app.services.interview_history_service import interview_history_service
from app.services.supabase_video_service import supabase_video_service
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.answer_polish_service import AnswerPolishService
from app.services.interview_framework_service import interview_framework_service
from app.services.fast_interview_evaluator import get_fast_evaluator


def _extract_framework_from_question(question: str, framework_service) -> Optional[Dict[str, Any]]:
    """
    从问题文本中提取 framework 名称
    支持多种格式：
    - "请使用 STAR 框架"
    - "使用STAR框架"
    - "STAR framework"
    - "STARフレームワーク"
    """
    if not question:
        return None
    
    # 获取所有可用的 framework 名称
    frameworks_data = framework_service._frameworks_data
    if not frameworks_data or not frameworks_data.get("interviewFrameworks"):
        return None
    
    # 收集所有 framework 名称（不区分大小写）
    framework_names = []
    for category in frameworks_data.get("interviewFrameworks", []):
        for method in category.get("methods", []):
            method_name = method.get("methodName", "")
            if method_name:
                framework_names.append({
                    "name": method_name,
                    "category": category.get("category"),
                    "method": method
                })
    
    # 在问题中查找 framework 名称
    question_lower = question.lower()
    for fw_info in framework_names:
        fw_name = fw_info["name"].upper()
        # 检查多种可能的格式
        patterns = [
            fw_name.lower(),
            fw_name,
            f"{fw_name} 框架",
            f"{fw_name}框架",
            f"{fw_name} framework",
            f"{fw_name}フレームワーク",
            f"使用 {fw_name}",
            f"使用{fw_name}",
            f"use {fw_name}",
            f"{fw_name}を使用",
        ]
        
        for pattern in patterns:
            if pattern.lower() in question_lower:
                method = fw_info["method"]
                return {
                    "category": fw_info["category"],
                    "methodName": method.get("methodName"),
                    "description": method.get("description"),
                    "bestFor": method.get("bestFor", "")
                }
    
    return None

router = APIRouter()
deepseek_service = DeepseekInterviewService()
answer_polish_service = AnswerPolishService()


class PolishQA(BaseModel):
    question: str = Field(default="")
    answer: str = Field(default="")


class PolishAnswersRequest(BaseModel):
    framework: str = Field(default="sds", description="framework md name (without .md)")
    qas: List[PolishQA] = Field(default_factory=list)
    language: Optional[str] = Field(default=None, description="language hint: zh/ja/en")
    interview_context: Optional[Dict[str, Any]] = Field(default=None)
# Use a faster evaluation strategy for stream mode (text metrics via mini; verbal/visual derived from nonverbal).
two_phase_evaluation_api = TwoPhaseEvaluationAPIImpl(default_strategy_id="strategy_stream_fast")

async def _process_video_analysis_only(
    session_id: str,
    parked_video_path: str,
    user_text: str,
    duration: float,
    segment_index: int,
    realtime_nonverbal: Optional[Dict[str, Any]],
    language: str,
    skip_analysis: bool = False,
):
    """
    后台任务：仅进行非语言分析（不上传视频）。
    上传视频会在评测完成后统一后台进行，避免影响下一题生成。
    """
    if skip_analysis:
        # Mark as analyzed with a placeholder so UI/flow doesn't wait forever,
        # but do not call any vision/voice model.
        await session_manager.update_segment_nonverbal(
            session_id=session_id,
            segment_index=segment_index,
            nonverbal_data={"analysis": {"skipped": True, "reason": "final_turn_skip_nonverbal"}},
        )
        log(f"[StreamInterview] ⏭️ Skipped nonverbal analysis for final turn segment {segment_index}")
        return

    # IMPORTANT: process_video_async deletes the file it receives.
    # To preserve the parked video for later upload, analyze a temporary copy.
    if not parked_video_path or not os.path.exists(parked_video_path):
        log(f"[StreamInterview] ⚠️ Parked video not found for analysis: {parked_video_path}")
        return

    tmp_copy_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmpf:
            tmp_copy_path = tmpf.name
        shutil.copyfile(parked_video_path, tmp_copy_path)

        await process_video_async(
            session_id=session_id,
            video_path=tmp_copy_path,
            user_text=user_text,
            duration=duration,
            segment_index=segment_index,
            realtime_hint=realtime_nonverbal,
            language=language,
        )
    finally:
        # process_video_async attempts to delete tmp_copy_path itself; double-delete safe
        if tmp_copy_path and os.path.exists(tmp_copy_path):
            try:
                os.unlink(tmp_copy_path)
            except Exception:
                pass


async def _upload_all_parked_videos(session_id: str) -> None:
    """
    Upload all parked segment videos to Supabase after evaluation is completed.
    Progress is reflected via session_manager.update_segment_video_url, and the frontend
    reads it through /check-analysis (uploaded/total).
    """
    try:
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        conversation = timeline_doc.get("conversation") or []
        user_segments = [msg for msg in conversation if msg.get("role") == "user"]
        total = len(user_segments)
        if total == 0:
            return

        log(f"[StreamInterview] 📤 Starting post-evaluation upload for {total} segments...")

        # Build current video_url state from timeline
        uploaded_indices: set[int] = set()
        for idx, msg in enumerate(user_segments):
            nonverbal = msg.get("nonverbal")
            if isinstance(nonverbal, dict) and nonverbal.get("video_url"):
                uploaded_indices.add(idx)

        # Helper for parallel upload
        async def _upload_single_segment(seg_idx: int) -> None:
            if seg_idx in uploaded_indices:
                return
            parked_path = _get_temp_video_path(session_id, seg_idx)
            if not os.path.exists(parked_path):
                log(f"[StreamInterview] ⚠️ Parked video missing for upload: seg={seg_idx} path={parked_path}")
                # Solution A (frontend direct upload to Supabase) does not rely on backend-local parked files.
                # Never overwrite a real Supabase URL with sentinel values like "skipped".
                return
            try:
                log(f"[StreamInterview] 📤 Uploading parked video seg={seg_idx} ...")
                public_url = await supabase_video_service.upload_video(parked_path, session_id, seg_idx)
                if public_url:
                    await session_manager.update_segment_video_url(session_id, seg_idx, public_url)
                    log(f"[StreamInterview] ✓ Uploaded seg={seg_idx}")
                    # Optional cleanup after successful upload
                    try:
                        os.unlink(parked_path)
                    except Exception:
                        pass
                else:
                    log(f"[StreamInterview] ⚠️ Upload returned None for seg={seg_idx}")
                    # Do not write sentinel values; leave existing URL untouched.
            except Exception as e:
                log(f"[StreamInterview] ⚠️ Upload failed for seg={seg_idx}: {e}")
                # Do not write sentinel values; leave existing URL untouched.

        # Execute uploads in parallel
        await asyncio.gather(*[_upload_single_segment(i) for i in range(total)])
        log(f"[StreamInterview] ✅ Post-evaluation upload completed for {total} segments.")

    except Exception as e:
        log(f"[StreamInterview] ⚠️ Post-evaluation upload_all failed: {e}")

MANDATORY_DIMENSIONS = ["VERBAL_PERFORMANCE", "VISUAL_PERFORMANCE"]


def _sanitize_dimension_keys(raw_keys: Any) -> List[str]:
    if not isinstance(raw_keys, list):
        return []
    keys: List[str] = []
    for key in raw_keys:
        if isinstance(key, str):
            normalized = key.strip()
            if normalized and normalized not in keys:
                keys.append(normalized)
    return keys


def _get_all_dimension_keys() -> List[str]:
    try:
        dimensions = interview_params_service.get_basic_dimensions()
    except Exception:
        dimensions = []
    keys: List[str] = []
    for dim in dimensions:
        key = dim.get("key") if isinstance(dim, dict) else None
        if isinstance(key, str):
            normalized = key.strip()
            if normalized and normalized not in keys:
                keys.append(normalized)
    if not keys:
        # fallback to default known dimensions
        keys = ["CLARITY", "EVIDENCE", "IMPACT", "ENGAGEMENT", "VERBAL_PERFORMANCE", "VISUAL_PERFORMANCE"]
    return keys


def _ensure_mandatory_dimensions(keys: List[str]) -> List[str]:
    unique = []
    seen = set()
    for key in keys:
        if isinstance(key, str):
            normalized = key.strip()
            if normalized and normalized not in seen:
                unique.append(normalized)
                seen.add(normalized)
    for mandatory in MANDATORY_DIMENSIONS:
        if mandatory not in seen:
            unique.append(mandatory)
            seen.add(mandatory)
    return unique


def _resolve_dimension_keys_from_metadata(metadata: Dict[str, Any]) -> List[str]:
    keys = _sanitize_dimension_keys(metadata.get("dimension_keys"))
    if keys:
        return _ensure_mandatory_dimensions(keys)
    return _ensure_mandatory_dimensions(_get_all_dimension_keys())


def _normalize_rounds_metadata(metadata: Dict[str, Any]) -> None:
    rounds_config = metadata.get("rounds")
    min_rounds: Optional[int] = None
    max_rounds: Optional[int] = None

    if isinstance(rounds_config, dict):
        try:
            if "min" in rounds_config:
                min_rounds = int(rounds_config["min"])
            if "max" in rounds_config:
                max_rounds = int(rounds_config["max"])
        except (ValueError, TypeError):
            min_rounds = max_rounds = None

    elif isinstance(rounds_config, (int, float)):
        try:
            fixed = int(rounds_config)
            if fixed > 0:
                min_rounds = max_rounds = fixed
        except (ValueError, TypeError):
            min_rounds = max_rounds = None

    if min_rounds is None and max_rounds is None:
        metadata["rounds"] = None
        min_rounds = max_rounds = None
    else:
        if min_rounds is None:
            min_rounds = max_rounds or 5
        if max_rounds is None:
            max_rounds = min_rounds
        if min_rounds < 1:
            min_rounds = 1
        if max_rounds < min_rounds:
            max_rounds = min_rounds
        metadata["rounds"] = {"min": min_rounds, "max": max_rounds}

    target = metadata.get("target_rounds")
    if not isinstance(target, int) or target <= 0:
        if min_rounds and max_rounds:
            metadata["target_rounds"] = random.randint(min_rounds, max_rounds)


def _resolve_target_rounds_from_metadata(metadata: Dict[str, Any]) -> int:
    target = metadata.get("target_rounds")
    if isinstance(target, int) and target > 0:
        return target

    rounds_config = metadata.get("rounds")
    if isinstance(rounds_config, dict):
        min_rounds = rounds_config.get("min")
        max_rounds = rounds_config.get("max")
        try:
            min_val = int(min_rounds) if min_rounds is not None else None
            max_val = int(max_rounds) if max_rounds is not None else None
        except (ValueError, TypeError):
            min_val = max_val = None

        if min_val and max_val:
            if min_val > max_val:
                min_val, max_val = max_val, min_val
            metadata["target_rounds"] = max_val
            return max_val
        if min_val:
            metadata["target_rounds"] = min_val
            return min_val
        if max_val:
            metadata["target_rounds"] = max_val
            return max_val

    default_rounds = interview_params_service.get_basic_rounds()
    metadata["target_rounds"] = default_rounds
    return default_rounds


@router.post("/start-stream")
async def start_interview_stream(
    role: str = Form(default="面試官-後端開発"),
    system_message: Optional[str] = Form(default=None),
    tts_voice: Optional[str] = Form(default=None),
    session_metadata: Optional[str] = Form(default=None),
    force_first_question_framework: bool = Form(default=False),
):
    """
    流式启动面试 - 返回 session_id 和流式第一个问题
    Response: application/x-ndjson
    Lines: {session_info} / {question_chunk} / {end}
    """
    if not system_message:
        system_message = f"あなたは専門的な{role}です。候補者の回答に基づいて面接を行い、深い質問をしてください。重要：すべての質問は日本語のみで記述してください。中国語や英語は一切使用しないでください。"
    
    metadata: Dict[str, Any] = {}
    if session_metadata:
        try:
            parsed = json.loads(session_metadata)
            if isinstance(parsed, dict):
                metadata = parsed
        except json.JSONDecodeError:
            log(f"[StreamInterview] ⚠️ Failed to parse session_metadata JSON, ignoring: {session_metadata[:100]}")
    metadata["dimension_keys"] = _resolve_dimension_keys_from_metadata(metadata)
    _normalize_rounds_metadata(metadata)
    current_target = metadata.get("target_rounds")
    if not isinstance(current_target, int) or current_target <= 0:
        metadata["target_rounds"] = interview_params_service.get_basic_rounds()
    if tts_voice:
        metadata["tts_voice"] = tts_voice

    # Start session
    session = await session_manager.start_session(
        role,
        system_message,
        tts_voice=tts_voice or "alloy",
        metadata=metadata,
    )
    session_id = session.session_id
    print(f"[StreamInterview] Session started: {session_id}")
    
    # 获取语言设置
    session_language = metadata.get("language", "ja")
    
    async def body() -> AsyncGenerator[bytes, None]:
        tts_format = get_tts_format()
        voice = session.tts_voice

        # 1. 先返回 session 信息
        yield ndj({
            "session_id": session_id,
            "role": role,
            "timestamp": time.time(),
            "tts_voice": voice,
            **({"tts_format": tts_format} if tts_format else {}),
        })
        # ⚡ 立即yield大量padding，强制flush HTTP缓冲区（4KB空白强制TCP立即发送）
        yield b"\n" * 4096  # 4KB换行符，强制flush
        
        # 2. 流式生成第一个问题
        print(f"[StreamInterview] 🌊 Starting to stream first question...")
        
        # 🎯 在 body() 函数内部创建一个 system_message 的副本，避免修改外部变量
        current_system_message = system_message
        
        # 🎲 Framework Logic (Roll based on probability, or force if flag is set)
        framework_use_probability = interview_params_service.get_framework_use_probability()
        if force_first_question_framework:
            use_framework = 1
            print(f"[StreamInterview] 🎲 Force framework for Q1: enabled")
        else:
            # Roll based on probability (e.g., 0.9 = 90% chance of using framework)
            use_framework = 1 if random.random() < framework_use_probability else 0
            print(f"[StreamInterview] 🎲 Rolling for Q1: got {use_framework} (probability: {framework_use_probability*100:.0f}%)")
        # 🎯 新逻辑：如果 roll 到了 1，在 system message 中提前注入所有 framework 列表
        # 让 LLM 在后续提问时根据历史问题和用户回答来选择 framework
        all_frameworks_summary = None
        framework_config = None
        
        if use_framework == 1:
            all_frameworks_summary = interview_framework_service.get_all_frameworks_summary()
            if all_frameworks_summary:
                # 在 system message 中提前注入 framework 列表
                if session_language.startswith("zh"):
                    current_system_message += f"\n\n【框架使用规则】\n在本次面试中，你可以使用以下框架来指导候选人构建回答。请根据每个问题的内容和候选人的回答，从以下框架列表中选择最适合的框架，并按照该框架的结构来设计问题，但不要在问题中明确提到框架名称。\n\n可用框架列表：\n{all_frameworks_summary}\n\n重要提示：\n1. 在提出第一个问题时，请从上述框架中选择一个最适合的框架，并按照该框架的结构来设计问题\n2. 在后续提问时，请根据历史问题和候选人的回答，选择最适合的框架来设计问题\n3. 不要在问题中明确提到框架名称（如'STAR框架'、'CAR框架'等），而是通过问题的结构和引导来自然地让候选人按照框架的结构来回答\n4. 如果候选人的回答已经很好地使用了某个框架，可以继续使用该框架进行深入提问，或者切换到更适合的框架\n5. 在问题文本的最后，务必添加一个标记来标识你使用的框架，格式必须严格为：[FRAMEWORK: 框架名称]。例如：[FRAMEWORK: STAR] 或 [FRAMEWORK: CAR]。请勿使用其他格式（如FRAMEWORK_USED:等）。这个标记不会显示给候选人，仅用于系统记录"
                elif session_language.startswith("en"):
                    current_system_message += f"\n\n【Framework Usage Rules】\nIn this interview, you can use the following frameworks to guide candidates in structuring their answers. Please select the most appropriate framework from the list below based on each question's content and the candidate's answers, and design your question according to the framework's structure, but do NOT explicitly mention the framework name in your question.\n\nAvailable Frameworks:\n{all_frameworks_summary}\n\nImportant Notes:\n1. When asking the first question, please select the most appropriate framework from the above list and design your question according to that framework's structure\n2. In subsequent questions, please select the most appropriate framework based on previous questions and the candidate's answers\n3. Do NOT explicitly mention the framework name (e.g., 'STAR framework', 'CAR framework') in your question. Instead, naturally guide the candidate to structure their answer according to the framework through the question's structure and guidance\n4. If the candidate's answer already uses a framework well, you can continue using that framework for deeper questions, or switch to a more suitable framework\n5. At the end of your question text, you MUST add a marker to identify the framework you used, in the STRICT format: [FRAMEWORK: FrameworkName]. e.g., [FRAMEWORK: STAR] or [FRAMEWORK: CAR]. Do NOT use other formats (like FRAMEWORK_USED:). This marker will not be shown to the candidate, only for system recording"
                else:
                    current_system_message += f"\n\n【フレームワーク使用ルール】\nこの面接では、以下のフレームワークを使用して候補者に回答を構築するよう指導できます。各質問の内容と候補者の回答に基づいて、以下のフレームワークリストから最も適切なフレームワークを選択し、そのフレームワークの構造に従って質問を設計してください。ただし、質問の中でフレームワーク名を明確に言及しないでください。\n\n利用可能なフレームワーク：\n{all_frameworks_summary}\n\n重要な注意事項：\n1. 最初の質問を出す際は、上記のフレームワークから最も適切なものを選択し、そのフレームワークの構造に従って質問を設計してください\n2. 後続の質問では、以前の質問と候補者の回答に基づいて、最も適切なフレームワークを選択してください\n3. 質問の中でフレームワーク名を明確に言及しないでください（例：「STARフレームワークを使用して」など）。代わりに、質問の構造とガイダンスを通じて、候補者が自然にフレームワークの構造に従って回答できるようにしてください\n4. 候補者の回答がすでにフレームワークをうまく使用している場合は、そのフレームワークを続けて使用してより深い質問をすることも、より適切なフレームワークに切り替えることもできます\n5. 質問テキストの最後に、使用したフレームワークを識別するマーカーを追加してください。形式は厳密に：[FRAMEWORK: フレームワーク名]（例：[FRAMEWORK: STAR] または [FRAMEWORK: CAR]）。他の形式（FRAMEWORK_USED:など）は使用しないでください。このマーカーは候補者には表示されず、システム記録のみに使用されます"
                
                # 更新 session 的 system_message，以便后续提问时也能使用
                # 更新 session 对象中的 system_message
                current_sess = await session_manager.get_session(session_id)
                current_sess.system_message = current_system_message
                
                await session_manager.update_session_metadata(session_id, {
                    "framework_enabled": True,
                    "framework_summary": all_frameworks_summary
                })
                
                print(f"[StreamInterview] 🎲 Rolled 1: Framework list injected into system message")
                print(f"[StreamInterview] 📋 Framework summary length: {len(all_frameworks_summary)} chars")
            else:
                print(f"[StreamInterview] 🎲 Rolled 1 but no framework data available, falling back to no framework")
        else:
            print(f"[StreamInterview] 🎲 Rolled 0: No framework for this interview")

        question_parts = []
        chunk_index = 0
        last_yield_time = time.time()
        
        # 🎯 实时过滤框架标记的缓冲区
        framework_buffer = ""
        # 支持多种标记格式: [FRAMEWORK: xxx] 或 FRAMEWORK_USED: xxx
        # 优化正则：匹配 [FRAMEWORK: ...] (允许末尾多个]) 或 FRAMEWORK_USED: ... (到行尾)
        # 并且吞掉标记后的空白字符
        framework_marker_pattern = r'(?:\[FRAMEWORK:\s*[^\]\n]+\]+|FRAMEWORK_USED:\s*[^\n]+(?:\n|$))\s*'
        
        async for chunk in deepseek_service.generate_first_question_stream(
            role, 
            current_system_message,  # 使用修改后的 system_message
            language=session_language,
            framework_config=framework_config,
            all_frameworks_summary=all_frameworks_summary
        ):
            chunk_index += 1
            question_parts.append(chunk)
            
            # 🎯 实时过滤框架标记
            framework_buffer += chunk
            
            # 检查缓冲区中是否有完整的框架标记
            if re.search(framework_marker_pattern, framework_buffer, re.IGNORECASE):
                # 找到完整标记，移除它并分割内容
                parts = re.split(framework_marker_pattern, framework_buffer, flags=re.IGNORECASE)
                # parts[0] 是标记之前的内容，parts[1] 是标记之后的内容（如果有）
                content_before_marker = parts[0] if parts else ""
                content_after_marker = parts[1] if len(parts) > 1 else ""
                
                # Yield 标记之前的内容
                if content_before_marker:
                    current_time = time.time()
                    elapsed = current_time - last_yield_time
                    print(f"[StreamInterview] 📦 Yielding chunk #{chunk_index} (before marker): {repr(content_before_marker)} (delay: {elapsed*1000:.1f}ms)")
                    yield ndj({"question_chunk": content_before_marker})
                    last_yield_time = current_time
                
                # 保留标记之后的内容在缓冲区中继续处理
                framework_buffer = content_after_marker
            else:
                # 检查缓冲区是否可能包含标记的前缀
                upper_buf = framework_buffer.upper()
                is_potential = False
                
                # 检查 [FRAMEWORK:
                if "[" in upper_buf:
                    idx = upper_buf.rfind("[")
                    potential = upper_buf[idx:]
                    if "[FRAMEWORK:".startswith(potential) or potential.startswith("[FRAMEWORK:"):
                        is_potential = True
                
                # 检查 FRAMEWORK_USED:
                if not is_potential and "F" in upper_buf:
                    idx = upper_buf.rfind("F")
                    potential = upper_buf[idx:]
                    if "FRAMEWORK_USED:".startswith(potential) or potential.startswith("FRAMEWORK_USED:"):
                        is_potential = True
                        
                if is_potential and len(framework_buffer) < 100:
                    # 可能正在构建标记，继续累积（不yield）
                    pass
                else:
                    # 不包含标记相关文本，直接 yield 并清空缓冲区
                    if framework_buffer:
                        current_time = time.time()
                        elapsed = current_time - last_yield_time
                        print(f"[StreamInterview] 📦 Yielding chunk #{chunk_index}: {repr(framework_buffer)} (delay: {elapsed*1000:.1f}ms)")
                        yield ndj({"question_chunk": framework_buffer})
                        last_yield_time = current_time
                        framework_buffer = ""
            
            await asyncio.sleep(0.001)  # 1ms延迟，减少overhead
        
        # 🎯 处理剩余的缓冲区内容（可能包含标记）
        if framework_buffer:
            framework_buffer = re.sub(framework_marker_pattern, '', framework_buffer, flags=re.IGNORECASE)
            if framework_buffer.strip():
                yield ndj({"question_chunk": framework_buffer})
        
        print(f"[StreamInterview] 🏁 First question stream completed! Total chunks: {chunk_index}")
        
        # 3. 完整问题保存到 timeline
        full_question = "".join(question_parts).strip()
        
        # 🎯 从第一个问题中提取 framework 标记（格式：[FRAMEWORK: 框架名称] 或 FRAMEWORK_USED: 框架名称）
        detected_framework = None
        # 优化正则，确保能匹配并提取框架名称
        # 捕获组1: [FRAMEWORK: xxx] 中的 xxx
        # 捕获组2: FRAMEWORK_USED: xxx 中的 xxx
        framework_marker_pattern_extract = r'(?:\[FRAMEWORK:\s*([^\]\n]+)\]+|FRAMEWORK_USED:\s*([^\n]+)(?:\n|$))'
        match = re.search(framework_marker_pattern_extract, full_question, re.IGNORECASE)
        if match:
            # 获取非空的捕获组
            framework_name = (match.group(1) or match.group(2)).strip()
            # 从 framework service 中查找对应的 framework 信息
            frameworks_data = interview_framework_service._frameworks_data
            if frameworks_data and frameworks_data.get("interviewFrameworks"):
                for category in frameworks_data.get("interviewFrameworks", []):
                    for method in category.get("methods", []):
                        if method.get("methodName", "").upper() == framework_name.upper():
                            detected_framework = {
                                "category": category.get("category"),
                                "methodName": method.get("methodName"),
                                "description": method.get("description"),
                                "bestFor": method.get("bestFor", "")
                            }
                            break
                    if detected_framework:
                        break
            
            # 如果找到了 framework，从问题中移除标记
            if detected_framework:
                # 移除标记（使用更宽泛的正则以确保清理干净）
                clean_pattern = r'(?:\[FRAMEWORK:\s*[^\]\n]+\]+|FRAMEWORK_USED:\s*[^\n]+(?:\n|$))\s*'
                full_question = re.sub(clean_pattern, '', full_question, flags=re.IGNORECASE).strip()
                # 移除任何提到"使用了xxx框架"的文本（中文）
                framework_name_zh = detected_framework.get("methodName", "")
                if framework_name_zh:
                    # 移除各种可能的框架提及方式
                    patterns_to_remove = [
                        rf'使用了{re.escape(framework_name_zh)}框架',
                        rf'使用{re.escape(framework_name_zh)}框架',
                        rf'采用{re.escape(framework_name_zh)}框架',
                        rf'运用{re.escape(framework_name_zh)}框架',
                        rf'基于{re.escape(framework_name_zh)}框架',
                        rf'按照{re.escape(framework_name_zh)}框架',
                    ]
                    for pattern in patterns_to_remove:
                        full_question = re.sub(pattern, '', full_question, flags=re.IGNORECASE).strip()
                    # 移除英文提及
                    framework_name_en = framework_name_zh.upper()  # STAR, CAR, etc.
                    en_patterns = [
                        rf'using\s+{re.escape(framework_name_en)}\s+framework',
                        rf'used\s+{re.escape(framework_name_en)}\s+framework',
                        rf'with\s+{re.escape(framework_name_en)}\s+framework',
                        rf'based\s+on\s+{re.escape(framework_name_en)}\s+framework',
                    ]
                    for pattern in en_patterns:
                        full_question = re.sub(pattern, '', full_question, flags=re.IGNORECASE).strip()
                # 清理多余的空格和标点
                full_question = re.sub(r'\s+', ' ', full_question).strip()
                full_question = re.sub(r'[，。、]\s*$', '', full_question).strip()
        
        # 记录 framework 使用情况到 metadata（第一个问题，索引为 0）
        if use_framework == 1 and all_frameworks_summary and detected_framework:
            current_sess = await session_manager.get_session(session_id)
            current_meta = getattr(current_sess, "metadata", {}) or {}
            fw_usage_map = current_meta.get("framework_usage", {}) or {}
            fw_usage_map["0"] = detected_framework
            await session_manager.update_session_metadata(session_id, {"framework_usage": fw_usage_map})
            print(f"[StreamInterview] ✅ Detected and recorded framework: {detected_framework['methodName']} for Q1")
        elif use_framework == 1 and all_frameworks_summary:
            print(f"[StreamInterview] ⚠️ Framework enabled but no framework marker found in first question")
        
        t0 = 0.0
        t1 = 5.0
        await session_manager.seg_start(session_id, t0, "system")
        await session_manager.seg_append_text(session_id, full_question)
        await session_manager.seg_commit(session_id, t1)
        
        # 4. 流式播报语音
        # (Removed) Front-end uses Google Cloud TTS directly for better latency
        # async for tts_chunk in stream_question_tts(full_question, voice):
        #     yield tts_chunk

        # 5. 结束标记
        yield ndj({"end": True, "full_question": full_question})
    
    headers = {
        "Content-Type": "application/x-ndjson",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(body(), media_type="application/x-ndjson", headers=headers)


@router.post("/submit-answer-stream/{session_id}")
async def submit_answer_stream(
    session_id: str,
    background_tasks: BackgroundTasks,
    audio_file: Optional[UploadFile] = File(None),
    video_file: Optional[UploadFile] = File(None),
    duration: float = Form(...),
    nonverbal_features: Optional[str] = Form(None),
    tts_voice: Optional[str] = Form(default=None),
    use_buffered_audio: bool = Form(default=False),
    use_buffered_video: bool = Form(default=False),
) -> Any:
    """
    流式提交答案 - 返回流式下一个问题
    同时在后台异步处理视频分析和上传
    Response: application/x-ndjson
    Lines: {transcribed_text} / {question_chunk} / {end}
    """
    log(f"[StreamInterview] Received answer for session: {session_id}")
    
    # ⚠️ 检查请求体大小（防止 413 错误）
    # 如果前端意外上传了视频文件，在这里提前检测
    MAX_REQUEST_SIZE = 30 * 1024 * 1024  # 30MB，留一些余量给 Cloud Run 的 32MB 限制
    
    # 保存音频文件（支持缓冲模式）
    audio_path: Optional[str] = None

    if use_buffered_audio:
        if audio_file:
            # 检查音频文件大小（如果提供）
            try:
                if hasattr(audio_file, 'size') and audio_file.size and audio_file.size > MAX_REQUEST_SIZE:
                    log(f"[StreamInterview] ⚠️ Audio file too large: {audio_file.size / 1024 / 1024:.2f}MB")
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio file too large ({audio_file.size / 1024 / 1024:.2f}MB). Maximum size is 30MB."
                    )
            except Exception:
                pass  # 如果无法获取大小，继续处理
            
            audio_bytes = await audio_file.read()
            suffix = os.path.splitext(audio_file.filename or "")[1] or ".wav"
            await audio_chunk_buffer.append_chunk(session_id, audio_bytes, suffix=suffix)
        audio_path = await audio_chunk_buffer.consume(session_id)
        if not audio_path or not os.path.exists(audio_path):
            raise HTTPException(status_code=400, detail="Buffered audio not available")
    else:
        if not audio_file:
            raise HTTPException(status_code=400, detail="audio_file is required when buffered audio is disabled")
        
        # 检查音频文件大小
        try:
            if hasattr(audio_file, 'size') and audio_file.size and audio_file.size > MAX_REQUEST_SIZE:
                log(f"[StreamInterview] ⚠️ Audio file too large: {audio_file.size / 1024 / 1024:.2f}MB")
                raise HTTPException(
                    status_code=413,
                    detail=f"Audio file too large ({audio_file.size / 1024 / 1024:.2f}MB). Maximum size is 30MB."
                )
        except HTTPException:
            raise
        except Exception:
            pass  # 如果无法获取大小，继续处理
        
        audio_bytes = await audio_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_bytes)
            audio_path = temp_audio.name
    
    # 保存视频文件（支持缓冲模式）
    # IMPORTANT: we park videos locally and upload ONLY after evaluation completes
    # to avoid impacting next-question generation.
    video_path = None
    # 确定当前段落索引
    try:
        timeline_doc_check = await session_manager.get_timeline_doc(session_id)
        current_segment_index = len([msg for msg in timeline_doc_check["conversation"] if msg.get("role") == "user"])
    except Exception:
        current_segment_index = 0
        
    if use_buffered_video:
        # 使用缓冲的视频（录制时分片上传）
        # 优先使用 parked 路径（ingest-video-chunk finalize 时会落盘）
        parked_existing = _get_temp_video_path(session_id, current_segment_index)
        if os.path.exists(parked_existing):
            video_path = parked_existing
        else:
        # 尝试从buffer消费（如果已经完成）
            video_path = await video_chunk_buffer.consume(session_id, current_segment_index)

        # ✅ 统一：将 buffered video 移动/落盘到可预测 parked 路径（供后续评测后上传使用）
        if video_path and os.path.exists(video_path):
            parked_path = _get_temp_video_path(session_id, current_segment_index)
            try:
                os.makedirs(os.path.dirname(parked_path), exist_ok=True)
                if os.path.abspath(video_path) != os.path.abspath(parked_path):
                    try:
                        os.replace(video_path, parked_path)
                    except Exception:
                        shutil.copyfile(video_path, parked_path)
                        try:
                            os.unlink(video_path)
                        except Exception:
                            pass
                    video_path = parked_path
                    log(f"[StreamInterview] ✓ Buffered video parked to: {video_path}")
            except Exception as park_err:
                log(f"[StreamInterview] ⚠️ Failed to park buffered video: {park_err}")
        
        # 如果没找到，检查是否有临时上传的视频（upload-video-only可能已经保存了文件）
        if not video_path or not os.path.exists(video_path):
            temp_video_path = _get_temp_video_path(session_id, current_segment_index)
            if os.path.exists(temp_video_path):
                video_path = temp_video_path
                log(f"[StreamInterview] ✓ Found pre-uploaded video for segment {current_segment_index}: {video_path}")
            else:
                log(f"[StreamInterview] ⚠️ No video available for segment {current_segment_index} yet (will try late analysis)")
        else:
            if video_path and os.path.exists(video_path):
                file_size = os.path.getsize(video_path)
                log(f"[StreamInterview] ✓ Using buffered video: {file_size} bytes")
    elif video_file:
        # 传统模式：直接上传视频文件（仅落盘，不上传到 Supabase）
        # ⚠️ 检查视频文件大小（防止 413 错误）
        try:
            if hasattr(video_file, 'size') and video_file.size and video_file.size > MAX_REQUEST_SIZE:
                log(f"[StreamInterview] ⚠️ Video file too large: {video_file.size / 1024 / 1024:.2f}MB")
                raise HTTPException(
                    status_code=413,
                    detail=f"Video file too large ({video_file.size / 1024 / 1024:.2f}MB). Maximum size is 30MB. Please use chunked upload (ingest-video-chunk) for large files."
                )
        except HTTPException:
            raise
        except Exception:
            pass  # 如果无法获取大小，继续处理
        
        # Save directly to parked predictable path (avoid extra copies in request path)
        parked_path = _get_temp_video_path(session_id, current_segment_index)
        os.makedirs(os.path.dirname(parked_path), exist_ok=True)
        total_bytes = 0
        with open(parked_path, "wb") as f:
            while True:
                chunk = await video_file.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                total_bytes += len(chunk)
                if total_bytes > MAX_REQUEST_SIZE:
                    try:
                        os.unlink(parked_path)
                    except Exception:
                        pass
                    log(f"[StreamInterview] ⚠️ Video file exceeds size limit: {total_bytes / 1024 / 1024:.2f}MB")
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video file exceeds maximum size (30MB). Received {total_bytes / 1024 / 1024:.2f}MB. Please use chunked upload (ingest-video-chunk) for large files."
                    )
        video_path = parked_path
        log(f"[StreamInterview] Video parked: {total_bytes} bytes ({total_bytes / 1024 / 1024:.2f}MB)")
    else:
        # 检查是否有通过 upload-video-only 上传的 parked video
        temp_video_path = _get_temp_video_path(session_id, current_segment_index)
        if os.path.exists(temp_video_path):
            video_path = temp_video_path
            file_size = os.path.getsize(video_path)
            log(f"[StreamInterview] ✓ Found parked video for segment {current_segment_index}: {video_path} ({file_size} bytes)")
    
    try:
        # Step 1: 获取session信息（轻量级操作）
        try:
            session = await session_manager.get_session(session_id)
        except KeyError:
            log(f"[StreamInterview] ❌ Session not found: {session_id} (可能在不同的 Cloud Run 实例)")
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found. Please start a new interview session."
            )
        session_metadata = getattr(session, "metadata", {}) or {}
        voice = tts_voice or session_metadata.get("tts_voice") or session.tts_voice
        if voice != session.tts_voice:
            await session_manager.update_params(session_id, tts_voice=voice)
            session = await session_manager.get_session(session_id)
        session_metadata = getattr(session, "metadata", {}) or {}
        session_metadata["tts_voice"] = voice
        session_language = session_metadata.get("language", "ja")
        session_dimension_keys = _resolve_dimension_keys_from_metadata(session_metadata)
        dimension_keys_for_eval = _ensure_mandatory_dimensions(session_dimension_keys)
        
        # Step 2: 解析实时非语言特征（如果有）
        realtime_nonverbal: Optional[Dict[str, Any]] = None
        if nonverbal_features:
            try:
                realtime_nonverbal = json.loads(nonverbal_features)
            except json.JSONDecodeError:
                print("[StreamInterview] ✗ nonverbal_features JSON decode failed")
        
        # Step 3: 预先判断是否需要生成完整报告
        timeline_doc_pre = await session_manager.get_timeline_doc(session_id)
        user_rounds_pre = len([msg for msg in timeline_doc_pre["conversation"] if msg.get("role") == "user"])
        max_rounds = _resolve_target_rounds_from_metadata(session_metadata)
        should_schedule_full_report = (user_rounds_pre + 1) >= max_rounds
        log(f"[StreamInterview] should_schedule_full_report: {should_schedule_full_report}, user_rounds_pre: {user_rounds_pre}, max_rounds: {max_rounds}")

        # Step 4: 立即开始流式响应（在stream中执行ASR）
        async def body() -> AsyncGenerator[bytes, None]:
            try:
                # ⏱️ 记录开始时间
                stream_start_time = time.time()
                log(f"[StreamInterview] 📤 Starting body() generator at {stream_start_time:.3f}")
                
                # ✅ 立即告知前端开始转写（让用户知道正在处理）
                yield ndj({"status": "transcribing", "tts_voice": voice})
                yield b"\n" * 4096  # 4KB padding强制flush
                log(f"[StreamInterview] 📤 Yielded transcribing status (elapsed: {(time.time() - stream_start_time)*1000:.1f}ms)")
                
                # 🎤 在stream中执行ASR（这样前端不用干等）
                asr_start = time.time()
                user_text = await _transcribe_audio(audio_path, duration=duration, language=session_language)
                asr_elapsed = (time.time() - asr_start) * 1000
                log(f"[StreamInterview] 🎤 ASR completed in {asr_elapsed:.1f}ms: {user_text[:100]}...")
                
                # 立即添加用户回答到 timeline
                current_time = len(session.timeline) * 30.0
                user_end_time = current_time + duration
                
                await session_manager.seg_start(session_id, current_time, "user")
                await session_manager.seg_append_text(session_id, user_text)
                await session_manager.seg_commit(
                    session_id,
                    user_end_time,
                    dimensions=dimension_keys_for_eval,
                )
                
                # 检查是否结束
                timeline_doc = await session_manager.get_timeline_doc(session_id)
                user_rounds = len([msg for msg in timeline_doc["conversation"] if msg.get("role") == "user"])
                
                log(f"[StreamInterview] Round: {user_rounds}/{max_rounds}")
                turn_index = max(user_rounds - 1, 0)

                # 如果有视频，添加到section任务队列处理（确保同section内FIFO，不同section并行）
                segment_index = user_rounds - 1
                if video_path:
                    section_key = f"{session_id}:{segment_index}"

                    async def _enqueue_video_task() -> None:
                        try:
                            log(f"[StreamInterview] 🎬 Enqueuing video analysis for segment {segment_index}...")
                            log(f"[StreamInterview]    Video path: {video_path}")
                            log(f"[StreamInterview]    Video exists: {os.path.exists(video_path) if video_path else False}")
                            await section_task_queue.add_task(
                                section_key,
                                _process_video_analysis_only,
                                session_id=session_id,
                                parked_video_path=video_path,
                                user_text=user_text,
                                duration=duration,
                                segment_index=segment_index,
                                realtime_nonverbal=realtime_nonverbal,
                                language=session_language,
                                skip_analysis=should_schedule_full_report,
                            )
                            log(f"[StreamInterview] ✅ Video analysis queued (section: {section_key})")
                        except Exception as enqueue_err:  # pragma: no cover
                            log(f"[StreamInterview] ✗ Failed to enqueue video task: {enqueue_err}")
                            import traceback
                            traceback.print_exc()

                    # ⚡ 优化：使用 asyncio.create_task 异步执行视频任务入队，避免阻塞流式响应
                    # 之前的 await _enqueue_video_task() 会等待 IO 操作（检查文件存在等），导致下一个问题生成延迟
                    asyncio.create_task(_enqueue_video_task())
                else:
                    # 即使没有 video_path，也检查是否有 parked video（可能通过 upload-video-only 上传）
                    temp_video_path = _get_temp_video_path(session_id, segment_index)
                    if os.path.exists(temp_video_path):
                        log(f"[StreamInterview] 🔄 Found parked video after transcript, triggering video processing...")
                        section_key = f"{session_id}:{segment_index}"
                        
                        async def _enqueue_parked_video_task():
                            try:
                                await section_task_queue.add_task(
                                    section_key,
                                    _process_video_analysis_only,
                                    session_id=session_id,
                                    parked_video_path=temp_video_path,
                                    user_text=user_text,
                                    duration=duration,
                                    segment_index=segment_index,
                                    realtime_nonverbal=realtime_nonverbal,
                                    language=session_language,
                                    skip_analysis=should_schedule_full_report,
                                )
                                log(f"[StreamInterview] ✅ Parked video processing queued (section: {section_key})")
                            except Exception as enqueue_err:
                                log(f"[StreamInterview] ✗ Failed to enqueue parked video task: {enqueue_err}")
                                import traceback
                                traceback.print_exc()
                        
                        # ⚡ 优化：同样异步执行 parked video 任务入队
                        asyncio.create_task(_enqueue_parked_video_task())
                    else:
                        log(f"[StreamInterview] ℹ️ No video found for segment {segment_index}")
                
                # 注入实时非语言特征
                if realtime_nonverbal:
                    segment_index = turn_index
                    await session_manager.update_segment_nonverbal(
                        session_id=session_id,
                        segment_index=segment_index,
                        nonverbal_data={"realtime": realtime_nonverbal},
                    )
                    log(f"[StreamInterview] ✓ Realtime nonverbal injected for segment {segment_index}")
                    timeline_doc = await session_manager.get_timeline_doc(session_id)
                    user_rounds = len([msg for msg in timeline_doc["conversation"] if msg.get("role") == "user"])
                    turn_index = max(user_rounds - 1, 0)
                
                # 🔥 将评估放到后台异步执行（不阻塞响应流）
                # COMMENTED OUT: Fast evaluation disabled, only using section evaluation
                # 1. 快速评估（保持原有逻辑，用于实时反馈）
                # background_tasks.add_task(
                #     _evaluate_turn_async,
                #     session_id=session_id,
                #     transcript=user_text,
                #     turn_index=user_rounds - 1,
                #     question=latest_question,
                #     nonverbal_snapshot=nonverbal_snapshot,
                # )
                # print(f"[StreamInterview] Fast evaluation queued (async) for turn {user_rounds - 1}")
                
                eval_turn_index = turn_index
                async def _enqueue_section_evaluation() -> None:
                    try:
                        log(f"[StreamInterview] 🔄 Starting section evaluation enqueue for turn {eval_turn_index}...")

                        # Pre-generate cached feedback for text dimensions using a fast model,
                        # so the evaluation system can skip slow per-super-metric feedback LLM calls.
                        cf_start = time.time()
                        cached_feedback_task = asyncio.create_task(
                            generate_text_feedback_cached(
                                question=extract_latest_question(timeline_doc.get("conversation", []) or []),
                                answer=user_text,
                                language=session_language,
                            )
                        )

                        async def _evaluate_with_latest_snapshot(
                            session_id: str,
                            turn_idx: int,
                            transcript: str,
                            dimension_keys: List[str],
                            realtime_nv: Optional[Dict[str, Any]],
                            is_final_turn: bool,
                            max_rounds_local: int,
                            language: str = "ja",
                        ) -> None:
                            try:
                                cached_feedback_payload = await cached_feedback_task
                                await session_manager.update_unified_feedback(
                                    session_id=session_id,
                                    segment_index=turn_idx,
                                    feedback_data=cached_feedback_payload,
                                )
                                cf_elapsed = (time.time() - cf_start) * 1000
                                log(f"[StreamInterview] ⚡ Cached text feedback generated in {cf_elapsed:.1f}ms")
                                log(f"[StreamInterview] ⚡ Cached text feedback saved for segment {turn_idx} (keys: {list(cached_feedback_payload.keys())})")
                            except Exception as cf_err:
                                log(f"[StreamInterview] ⚠️ Failed to generate cached text feedback: {cf_err}")

                            latest_snapshot = await session_manager.get_timeline_doc(session_id)
                            conversation = latest_snapshot.get("conversation") or []

                            for idx, message in enumerate(conversation):
                                role = message.get("role")
                                dims_snapshot = message.get("dimensions")
                                nonverbal_snapshot = message.get("nonverbal")
                                if isinstance(nonverbal_snapshot, dict):
                                    nonverbal_keys_snapshot = list(nonverbal_snapshot.keys())
                                else:
                                    nonverbal_keys_snapshot = nonverbal_snapshot
                                log(
                                    f"[StreamInterview] 🧭 conversation[{idx}] role={role} "
                                    f"dims={dims_snapshot} nonverbal_keys={nonverbal_keys_snapshot}"
                                )
                                if role == "user":
                                    log(
                                        f"[StreamInterview] 🧑 user_snapshot[{idx}] "
                                        f"dims={dims_snapshot} "
                                        f"nonverbal={message.get('nonverbal')}"
                                    )

                            user_messages = [msg for msg in conversation if msg.get("role") == "user"]
                            if turn_idx < len(user_messages):
                                target_user_message = user_messages[turn_idx]
                                dims = target_user_message.get("dimensions")
                                if not isinstance(dims, list) or not dims:
                                    target_user_message["dimensions"] = dimension_keys.copy()
                                else:
                                    target_user_message["dimensions"] = _ensure_mandatory_dimensions(dims)

                                if realtime_nv:
                                    nonverbal_entry = target_user_message.get("nonverbal")
                                    if not isinstance(nonverbal_entry, dict):
                                        nonverbal_entry = {}
                                    nonverbal_entry.setdefault("realtime", realtime_nv)
                                    target_user_message["nonverbal"] = nonverbal_entry
                                elif not isinstance(target_user_message.get("nonverbal"), dict):
                                    target_user_message["nonverbal"] = {}

                            candidate_dims = target_user_message.get("dimensions")
                            candidate_nonverbal = target_user_message.get("nonverbal")
                            log(
                                "[StreamInterview] 🧷 Snapshot turn "
                                f"{turn_idx} user message dims={candidate_dims} "
                                f"nonverbal_keys={list(candidate_nonverbal.keys()) if isinstance(candidate_nonverbal, dict) else candidate_nonverbal}"
                            )

                            try:
                                timeline_dump = json.dumps(latest_snapshot, ensure_ascii=False)
                            except (TypeError, ValueError):
                                timeline_dump = str(latest_snapshot)
                            log(f"[StreamInterview] 🧾 Timeline snapshot: {timeline_dump[:1000]}{'...' if len(timeline_dump) > 1000 else ''}")

                            request = build_eval_request_from_timeline(latest_snapshot, language)
                            log(f"[StreamInterview] ✓ Built eval request with {len(request.interview)} items")

                            raw_dialog = parse_eval_request(request)
                            log(f"[StreamInterview] ✓ Parsed raw dialog with {len(raw_dialog.messages)} messages")

                            dialog_sections = await two_phase_evaluation_api.build_sections(raw_dialog)
                            log(f"[StreamInterview] ✓ Built {len(dialog_sections)} dialog sections")

                            current_section = None
                            for section in dialog_sections:
                                if section.section_index == turn_idx:
                                    current_section = section
                                    log(f"[StreamInterview] ✓ Found section by section_index: {section.section_index}")
                                    break

                            if not current_section:
                                if dialog_sections and turn_idx < len(dialog_sections):
                                    current_section = dialog_sections[turn_idx]
                                    log(f"[StreamInterview] ✓ Found section by array index: {turn_idx}")
                                elif dialog_sections:
                                    current_section = dialog_sections[-1]
                                    log(f"[StreamInterview] ⚠️ Using last section as fallback: {dialog_sections[-1].section_index}")

                            if not current_section:
                                log(f"[StreamInterview] ❌ No dialog section available for turn {turn_idx} (total sections: {len(dialog_sections) if dialog_sections else 0})")
                                if dialog_sections:
                                    section_indices = [s.section_index for s in dialog_sections]
                                    log(f"[StreamInterview] Available section indices: {section_indices}")
                                return

                            latest_question_local = extract_latest_question(conversation)
                            nonverbal_snapshot_local = compose_nonverbal_snapshot(
                                realtime=realtime_nv,
                                conversation=conversation,
                            )

                            await evaluate_section_async(
                                session_id=session_id,
                                turn_index=turn_idx,
                                dialog_section=current_section,
                                transcript=transcript,
                                question=latest_question_local,
                                nonverbal_snapshot=nonverbal_snapshot_local,
                                is_final_turn=is_final_turn,
                                max_rounds=max_rounds_local,
                            )

                        section_key = f"{session_id}:{eval_turn_index}"
                        await section_task_queue.add_task(
                            section_key,
                            _evaluate_with_latest_snapshot,
                            session_id,
                            eval_turn_index,
                            user_text,
                            dimension_keys_for_eval,
                            realtime_nonverbal,
                            should_schedule_full_report,
                            max_rounds,
                            session_language,
                        )
                        log(f"[StreamInterview] ✅ Section evaluation queued successfully (section: {section_key}) for turn {eval_turn_index}")
                    except Exception as section_build_error:
                        log(f"[StreamInterview] ❌ Failed to build/enqueue dialog sections: {section_build_error}")
                        import traceback
                        traceback.print_exc()

                asyncio.create_task(_enqueue_section_evaluation())
                
                # ✅ 发送转写结果给前端
                yield ndj({"transcribed_text": user_text, "tts_voice": voice})
                # ⚡ 立即yield大量padding，强制flush HTTP缓冲区（4KB空白强制TCP立即发送）
                yield b"\n" * 4096  # 4KB换行符，强制flush
                log(f"[StreamInterview] 📤 Yielded transcribed_text + padding (elapsed: {(time.time() - stream_start_time)*1000:.1f}ms)")
                
                # 判断是否结束
                if user_rounds >= max_rounds:
                    end_message = "今回の面接はこれで終了です。ご協力ありがとうございました。"
                    if session_language.startswith("en"):
                        end_message = "This concludes the interview. Thank you for your cooperation."
                    elif session_language.startswith("zh"):
                        end_message = "本次面试到此结束。感谢您的配合。"
                    
                    yield ndj({"question_chunk": end_message})
                    # (Removed) Front-end uses Google Cloud TTS directly
                    # async for tts_chunk in stream_question_tts(end_message, voice):
                    #     yield tts_chunk
                    yield ndj({"end": True, "interview_completed": True, "full_question": end_message})
                else:
                    # 流式生成下一个问题
                    llm_call_start = time.time()
                    log(f"[StreamInterview] 🌊 Starting to stream next question (elapsed: {(llm_call_start - stream_start_time)*1000:.1f}ms)...")
                    
                    # ⚡ 立即yield一个status，让前端知道正在生成问题（无需等待LLM）
                    yield ndj({"status": "generating_question"})
                    # ⚡ 立即yield大量padding，强制flush HTTP缓冲区（4KB空白强制TCP立即发送）
                    yield b"\n" * 4096  # 4KB换行符，强制flush
                    log(f"[StreamInterview] 📤 Yielded status + padding (elapsed: {(time.time() - stream_start_time)*1000:.1f}ms)")
                    
                    log(f"[StreamInterview] 🤖 Calling LLM API...")
                    
                    # 🎯 新逻辑：检查 session metadata 中是否启用了 framework
                    # 如果启用了，system_message 中已经包含了 framework 列表，LLM 会自动选择
                    next_q_index = user_rounds
                    current_sess = await session_manager.get_session(session_id)
                    current_meta = getattr(current_sess, "metadata", {}) or {}
                    framework_enabled = current_meta.get("framework_enabled", False)
                    all_frameworks_summary = current_meta.get("framework_summary")
                    
                    if framework_enabled and all_frameworks_summary:
                        print(f"[StreamInterview] 🎯 Framework enabled: LLM will select framework from system message")
                    else:
                        print(f"[StreamInterview] ℹ️ Framework not enabled for this session")
                    
                    question_parts = []
                    chunk_index = 0
                    first_chunk_received = False
                    last_yield_time = llm_call_start
                    
                    # 🎯 实时过滤框架标记的缓冲区
                    framework_buffer = ""
                    # 支持多种标记格式: [FRAMEWORK: xxx] 或 FRAMEWORK_USED: xxx
                    # 优化正则：匹配 [FRAMEWORK: ...] (允许末尾多个]) 或 FRAMEWORK_USED: ... (到行尾)
                    # 并且吞掉标记后的空白字符
                    framework_marker_pattern = r'(?:\[FRAMEWORK:\s*[^\]\n]+\]+|FRAMEWORK_USED:\s*[^\n]+(?:\n|$))\s*'
                    
                    async for chunk in deepseek_service.generate_next_question_stream(
                        conversation_history=timeline_doc["conversation"][-2:],  # 只保留最近1轮Q&A
                        user_answer=user_text,
                        role=session.role,
                        system_message=session.system_message,  # system_message 中已经包含了 framework 列表
                        language=session_language,
                        framework_config=None,  # 不再传递 framework_config，让 LLM 从 system_message 中选择
                        all_frameworks_summary=None  # 不再传递，因为已经在 system_message 中
                    ):
                        chunk_index += 1
                        question_parts.append(chunk)
                        current_time = time.time()
                        
                        if not first_chunk_received:
                            first_chunk_received = True
                            ttfb = (current_time - llm_call_start) * 1000
                            log(f"[StreamInterview] ⚡ LLM TTFB: {ttfb:.1f}ms")
                        
                        # 🎯 实时过滤框架标记
                        framework_buffer += chunk
                        
                        # 检查缓冲区中是否有完整的框架标记
                        if re.search(framework_marker_pattern, framework_buffer, re.IGNORECASE):
                            # 找到完整标记，移除它并分割内容
                            parts = re.split(framework_marker_pattern, framework_buffer, flags=re.IGNORECASE)
                            # parts[0] 是标记之前的内容，parts[1] 是标记之后的内容（如果有）
                            content_before_marker = parts[0] if parts else ""
                            content_after_marker = parts[1] if len(parts) > 1 else ""
                            
                            # Yield 标记之前的内容
                            if content_before_marker:
                                elapsed = current_time - last_yield_time
                                log(f"[StreamInterview] 📦 Yielding chunk #{chunk_index} (before marker): {repr(content_before_marker)} (delay: {elapsed*1000:.1f}ms)")
                                yield ndj({"question_chunk": content_before_marker})
                                last_yield_time = current_time
                            
                            # 保留标记之后的内容在缓冲区中继续处理
                            framework_buffer = content_after_marker
                        else:
                            # 检查缓冲区是否可能包含标记的前缀
                            upper_buf = framework_buffer.upper()
                            is_potential = False
                            
                            # 检查 [FRAMEWORK:
                            if "[" in upper_buf:
                                idx = upper_buf.rfind("[")
                                potential = upper_buf[idx:]
                                # 检查是否匹配前缀或者已经是前缀的一部分
                                if "[FRAMEWORK:".startswith(potential) or potential.startswith("[FRAMEWORK:"):
                                    is_potential = True
                            
                            # 检查 FRAMEWORK_USED:
                            if not is_potential and "F" in upper_buf:
                                idx = upper_buf.rfind("F") # 简化的检查，实际上应该检查单词边界，但这里简单起见
                                potential = upper_buf[idx:]
                                if "FRAMEWORK_USED:".startswith(potential) or potential.startswith("FRAMEWORK_USED:"):
                                    is_potential = True
                                    
                            if is_potential and len(framework_buffer) < 100: # 限制缓冲区大小，防止误判导致的无限缓冲
                                # 可能正在构建标记，继续累积（不yield）
                                pass
                            else:
                                # 不包含标记相关文本，直接 yield 并清空缓冲区
                                if framework_buffer:
                                    elapsed = current_time - last_yield_time
                                    log(f"[StreamInterview] 📦 Yielding chunk #{chunk_index}: {repr(framework_buffer)} (delay: {elapsed*1000:.1f}ms)")
                                    yield ndj({"question_chunk": framework_buffer})
                                    last_yield_time = current_time
                                    framework_buffer = ""
                        
                        await asyncio.sleep(0.001)  # 1ms延迟，减少网络overhead
                    
                    # 🎯 处理剩余的缓冲区内容（可能包含标记）
                    if framework_buffer:
                        framework_buffer = re.sub(framework_marker_pattern, '', framework_buffer, flags=re.IGNORECASE)
                        if framework_buffer.strip():
                            yield ndj({"question_chunk": framework_buffer})
                    
                    log(f"[StreamInterview] 🏁 Next question stream completed! Total chunks: {chunk_index}")
                    
                    # 保存完整问题到 timeline
                    full_question = "".join(question_parts).strip()
                    
                    # 🎯 从问题中提取 framework 标记（格式：[FRAMEWORK: 框架名称] 或 FRAMEWORK_USED: 框架名称）
                    detected_framework = None
                    framework_marker_pattern_extract = r'(?:\[FRAMEWORK:\s*([^\]\n]+)\]+|FRAMEWORK_USED:\s*([^\n]+)(?:\n|$))'
                    match = re.search(framework_marker_pattern_extract, full_question, re.IGNORECASE)
                    if match:
                        framework_name = (match.group(1) or match.group(2)).strip()
                        # 从 framework service 中查找对应的 framework 信息
                        frameworks_data = interview_framework_service._frameworks_data
                        if frameworks_data and frameworks_data.get("interviewFrameworks"):
                            for category in frameworks_data.get("interviewFrameworks", []):
                                for method in category.get("methods", []):
                                    if method.get("methodName", "").upper() == framework_name.upper():
                                        detected_framework = {
                                            "category": category.get("category"),
                                            "methodName": method.get("methodName"),
                                            "description": method.get("description"),
                                            "bestFor": method.get("bestFor", "")
                                        }
                                        break
                                if detected_framework:
                                    break
                        
                        # 如果找到了 framework，从问题中移除标记
                        if detected_framework:
                            # 移除标记（使用更宽泛的正则以确保清理干净）
                            clean_pattern = r'(?:\[FRAMEWORK:\s*[^\]\n]+\]+|FRAMEWORK_USED:\s*[^\n]+(?:\n|$))\s*'
                            full_question = re.sub(clean_pattern, '', full_question, flags=re.IGNORECASE).strip()
                            # 移除任何提到"使用了xxx框架"的文本（中文）
                            framework_name_zh = detected_framework.get("methodName", "")
                            if framework_name_zh:
                                # 移除各种可能的框架提及方式
                                patterns_to_remove = [
                                    rf'使用了{re.escape(framework_name_zh)}框架',
                                    rf'使用{re.escape(framework_name_zh)}框架',
                                    rf'采用{re.escape(framework_name_zh)}框架',
                                    rf'运用{re.escape(framework_name_zh)}框架',
                                    rf'基于{re.escape(framework_name_zh)}框架',
                                    rf'按照{re.escape(framework_name_zh)}框架',
                                ]
                                for pattern in patterns_to_remove:
                                    full_question = re.sub(pattern, '', full_question, flags=re.IGNORECASE).strip()
                                # 移除英文提及
                                framework_name_en = framework_name_zh.upper()  # STAR, CAR, etc.
                                en_patterns = [
                                    rf'using\s+{re.escape(framework_name_en)}\s+framework',
                                    rf'used\s+{re.escape(framework_name_en)}\s+framework',
                                    rf'with\s+{re.escape(framework_name_en)}\s+framework',
                                    rf'based\s+on\s+{re.escape(framework_name_en)}\s+framework',
                                ]
                                for pattern in en_patterns:
                                    full_question = re.sub(pattern, '', full_question, flags=re.IGNORECASE).strip()
                            # 清理多余的空格和标点
                            full_question = re.sub(r'\s+', ' ', full_question).strip()
                            full_question = re.sub(r'[，。、]\s*$', '', full_question).strip()
                    
                    # 记录 framework 使用情况到 metadata
                    if framework_enabled and all_frameworks_summary:
                        if detected_framework:
                            current_sess = await session_manager.get_session(session_id)
                            current_meta = getattr(current_sess, "metadata", {}) or {}
                            fw_usage_map = current_meta.get("framework_usage", {}) or {}
                            fw_usage_map[str(next_q_index)] = detected_framework
                            await session_manager.update_session_metadata(session_id, {"framework_usage": fw_usage_map})
                            print(f"[StreamInterview] ✅ Detected and recorded framework: {detected_framework['methodName']} for Q{next_q_index + 1}")
                        else:
                            print(f"[StreamInterview] ⚠️ Framework enabled but no framework marker found in question")
                    
                    ai_start_time = user_end_time + 1.0
                    ai_end_time = ai_start_time + 5.0
                    await session_manager.seg_start(session_id, ai_start_time, "system")
                    await session_manager.seg_append_text(session_id, full_question)
                    await session_manager.seg_commit(session_id, ai_end_time)
                    
                    # (Removed) Front-end uses Google Cloud TTS directly
                    # async for tts_chunk in stream_question_tts(full_question, voice):
                    #     yield tts_chunk
                    yield ndj({"end": True, "full_question": full_question})
            finally:
                # 清理音频文件（在body()内部清理，确保在ASR完成后再删除）
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.unlink(audio_path)
                        log(f"[StreamInterview] ✓ Cleaned up audio file")
                    except Exception as cleanup_err:
                        log(f"[StreamInterview] ✗ Audio cleanup error: {cleanup_err}")
        
        headers = {
            "Content-Type": "application/x-ndjson",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }

        # Full report scheduling is now handled by _check_and_schedule_full_report
        # after all section evaluations are completed
        
        return StreamingResponse(body(), media_type="application/x-ndjson", headers=headers)
    
    except Exception as e:
        # 如果在创建StreamingResponse前出错，需要清理音频文件
        if audio_path and os.path.exists(audio_path):
            try:
                os.unlink(audio_path)
            except:
                pass
        raise


@router.post("/ingest-audio-chunk/{session_id}")
async def ingest_audio_chunk(
    session_id: str,
    audio_chunk: UploadFile = File(...),
    chunk_index: int = Form(default=0),
    is_last: bool = Form(default=False),
    reset: bool = Form(default=False),
):
    """录制过程中分片上传音频并缓存在服务器端。"""

    if reset:
        await audio_chunk_buffer.discard(session_id)

    chunk_bytes = await audio_chunk.read()
    suffix = os.path.splitext(audio_chunk.filename or "")[1]
    if not suffix:
        suffix = {
            "audio/webm": ".webm",
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/x-wav": ".wav",
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
        }.get(audio_chunk.content_type or "", ".wav")  # 默认使用 WAV 格式

    state = await audio_chunk_buffer.append_chunk(session_id, chunk_bytes, suffix=suffix)

    response = {
        "status": "buffered",
        "chunk_index": chunk_index,
        "bytes_buffered": state.bytes_written,
        "is_last": is_last,
    }

    if is_last:
        response["ready"] = True

    return JSONResponse(response)


@router.post("/ingest-video-chunk/{session_id}")
async def ingest_video_chunk(
    session_id: str,
    video_chunk: UploadFile = File(...),
    segment_index: int = Form(default=0),
    chunk_index: int = Form(default=0),
    is_last: bool = Form(default=False),
    reset: bool = Form(default=False),
):
    """
    录制过程中分片上传视频并缓存在服务器端
    
    Args:
        session_id: 会话ID
        video_chunk: 视频分片文件
        chunk_index: 分片索引
        is_last: 是否是最后一个分片
        reset: 是否重置缓冲区
        
    Returns:
        上传状态
    """
    if reset:
        await video_chunk_buffer.discard(session_id, segment_index)
        log(f"[StreamInterview] ♻️ Reset video buffer for session {session_id} seg={segment_index}")

    chunk_bytes = await video_chunk.read()
    suffix = os.path.splitext(video_chunk.filename or "")[1] or ".mp4"

    state = await video_chunk_buffer.append_chunk(session_id, segment_index, chunk_bytes, suffix=suffix)

    response = {
        "status": "buffered",
        "chunk_index": chunk_index,
        "bytes_buffered": state.bytes_written,
        "chunk_count": state.chunk_count,
        "is_last": is_last,
    }

    if is_last:
        # 完成拼接并落盘到 parked 路径（这样 post-eval upload 一定能找到 seg=0）
        await video_chunk_buffer.finalize(session_id, segment_index)
        tmp_path = await video_chunk_buffer.consume(session_id, segment_index)
        if tmp_path and os.path.exists(tmp_path):
            parked_path = _get_temp_video_path(session_id, segment_index)
            try:
                os.makedirs(os.path.dirname(parked_path), exist_ok=True)
                if os.path.abspath(tmp_path) != os.path.abspath(parked_path):
                    try:
                        os.replace(tmp_path, parked_path)
                    except Exception:
                        shutil.copyfile(tmp_path, parked_path)
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                log(f"[StreamInterview] ✓ Buffered video parked (finalize) seg={segment_index}: {parked_path}")
            except Exception as park_err:
                log(f"[StreamInterview] ⚠️ Failed to park buffered video on finalize seg={segment_index}: {park_err}")
        response["ready"] = True
        log(f"[StreamInterview] ✓ Video buffer finalized for session {session_id}: "
            f"{state.chunk_count} chunks, {state.bytes_written} bytes")

        # Try late analysis if transcript already exists and analysis not present yet
        try:
            timeline_doc = await session_manager.get_timeline_doc(session_id)
            conversation = timeline_doc.get("conversation") or []
            user_msgs = [m for m in conversation if m.get("role") == "user"]
            if 0 <= segment_index < len(user_msgs):
                msg = user_msgs[segment_index]
                nonverbal = msg.get("nonverbal") if isinstance(msg, dict) else None
                already_analyzed = isinstance(nonverbal, dict) and isinstance(nonverbal.get("analysis"), dict)
                if not already_analyzed:
                    user_text = (msg.get("content") or "") if isinstance(msg, dict) else ""
                    # duration fallback from timestamps if available
                    duration = 0.0
                    try:
                        ts = msg.get("timestamp") if isinstance(msg, dict) else None
                        if isinstance(ts, dict) and ts.get("start") and ts.get("end"):
                            def _to_sec(s: str) -> float:
                                parts = [float(p) for p in str(s).split(":")]
                                if len(parts) == 3:
                                    return parts[0] * 3600 + parts[1] * 60 + parts[2]
                                if len(parts) == 2:
                                    return parts[0] * 60 + parts[1]
                                return float(parts[0])
                            duration = max(0.0, _to_sec(ts["end"]) - _to_sec(ts["start"]))
                    except Exception:
                        duration = 0.0

                    sess = await session_manager.get_session(session_id)
                    meta = getattr(sess, "metadata", {}) or {}
                    language = meta.get("language", "ja")
                    max_rounds_local = _resolve_target_rounds_from_metadata(meta)
                    is_final_turn = segment_index >= max(0, max_rounds_local - 1)

                    parked_path = _get_temp_video_path(session_id, segment_index)
                    if os.path.exists(parked_path):
                        # Respect "skip nonverbal on final turn" rule: mark as analyzed (skipped) so polling can complete.
                        if is_final_turn:
                            await session_manager.update_segment_nonverbal(
                                session_id=session_id,
                                segment_index=segment_index,
                                nonverbal_data={"analysis": {"skipped": True, "reason": "final_turn_skip_nonverbal"}},
                            )
                            log(f"[StreamInterview] ⏭️ Final turn: marked nonverbal analysis skipped (finalize) seg={segment_index}")
                        else:
                            section_key = f"{session_id}:{segment_index}"
                            await section_task_queue.add_task(
                                section_key,
                                _process_video_analysis_only,
                                session_id=session_id,
                                parked_video_path=parked_path,
                                user_text=user_text,
                                duration=duration,
                                segment_index=segment_index,
                                realtime_nonverbal=None,
                                language=language,
                            )
                            log(f"[StreamInterview] 🎬 Late video analysis queued from finalize seg={segment_index}")
        except Exception as late_err:
            log(f"[StreamInterview] ⚠️ Late analysis scheduling failed seg={segment_index}: {late_err}")

    return JSONResponse(response)


@router.post("/analyze-during-recording/{session_id}")
async def analyze_during_recording(
    session_id: str,
    background_tasks: BackgroundTasks,
    video_chunk: UploadFile = File(...),
    chunk_index: int = Form(...),
    duration: float = Form(...)
):
    """
    录制过程中实时分析视频片段（异步）
    前端可以在录制时定期发送视频片段进行分析
    这个接口立即返回，分析在后台进行
    """
    print(f"[StreamInterview] Received video chunk {chunk_index} for real-time analysis")
    
    # 保存视频片段
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_chunk:
        chunk_content = await video_chunk.read()
        temp_chunk.write(chunk_content)
        chunk_path = temp_chunk.name
    
    # 添加到后台任务
    background_tasks.add_task(
        analyze_chunk_async,
        session_id=session_id,
        chunk_path=chunk_path,
        chunk_index=chunk_index,
        duration=duration
    )
    
    return JSONResponse({
        "status": "queued",
        "chunk_index": chunk_index,
        "message": "Analysis queued in background"
    })


# ========== 辅助函数 ==========

async def _transcribe_audio(audio_path: str, duration: Optional[float] = None, language: Optional[str] = None) -> str:
    """
    音频转文字（复用原有逻辑）
    """
    from app.api.v1.endpoints.segmented_interview import _transcribe_audio as original_transcribe
    return await original_transcribe(audio_path, duration=duration, language=language)


def _get_temp_video_path(session_id: str, segment_index: int) -> str:
    """生成可预测的临时视频路径"""
    return os.path.join(tempfile.gettempdir(), f"video_buffer_{session_id}_{segment_index}.mp4")


@router.get("/timeline/{session_id}")
async def get_timeline(session_id: str):
    """获取完整 timeline"""
    try:
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        return JSONResponse(timeline_doc)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/polish-answers/{session_id}")
async def polish_answers(session_id: str, payload: PolishAnswersRequest):
    """
    Polish each user answer using a specified framework (md file under config/prompts/evaluation/v3/frameworks).
    For a given session, the first call generates and caches; later calls return cached result.
    """
    try:
        sess = await session_manager.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    framework = (payload.framework or "sds").strip()
    if not framework:
        framework = "sds"

    # Cache in session metadata to make the operation idempotent per session.
    meta = getattr(sess, "metadata", {}) or {}
    cache_key = f"polished_answers:{framework}"
    cached = meta.get(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("items"), list):
        return JSONResponse(cached)

    # Load framework md (currently only sds.md is present)
    try:
        import pathlib

        base_dir = pathlib.Path(__file__).resolve().parents[3]  # backend/app
        md_path = base_dir / "config" / "prompts" / "evaluation" / "v3" / "frameworks" / f"{framework}.md"
        framework_md = md_path.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail=f"Framework md not found: {framework}.md")

    qas = [{"question": qa.question or "", "answer": qa.answer or ""} for qa in (payload.qas or [])]
    # Drop empty rows
    qas = [qa for qa in qas if (qa.get("question") or "").strip() or (qa.get("answer") or "").strip()]
    if not qas:
        raise HTTPException(status_code=400, detail="qas is empty")

    # Add interview background context: role/system_message + any client context
    interview_context: Dict[str, Any] = {
        "session_id": session_id,
        "role": getattr(sess, "role", ""),
        "system_message": getattr(sess, "system_message", ""),
        "note": "Polish answers to a 90-point level using the framework, without hallucinating facts.",
    }
    if isinstance(payload.interview_context, dict):
        interview_context.update(payload.interview_context)

    # Retrieve framework usage from session metadata to enrich QAs
    fw_usage_map = meta.get("framework_usage", {})
    enriched_qas = []
    for i, qa in enumerate(qas):
        # qa is a dict here (from previous comprehension)
        qa_copy = qa.copy()
        usage = fw_usage_map.get(str(i))
        if usage:
            # Only add framework if it was actually used (roll=1)
            qa_copy["framework"] = {
                "methodName": usage.get("methodName"),
                "description": usage.get("description"),
                "category": usage.get("category"),
                "bestFor": usage.get("bestFor", "")  # Include bestFor if available
            }
        # If no framework usage recorded, qa_copy won't have framework field (will use default)
        enriched_qas.append(qa_copy)

    try:
        items = await answer_polish_service.polish_answers(
            framework_md=framework_md,
            qas=enriched_qas,
            language=payload.language,
            interview_context=interview_context,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to polish answers: {e}")

    result = {
        "session_id": session_id,
        "framework": framework,
        "items": items,
    }
    await session_manager.update_session_metadata(session_id, {cache_key: result})
    return JSONResponse(result)


@router.get("/evaluation-status/{session_id}")
async def get_evaluation_status(session_id: str):
    """
    获取面试评估状态（用于轮询异步评估结果）
    
    返回:
    - fast_evaluations: 每轮评估详情（现为空数组，保持兼容性）
    - aggregated: 聚合评估结果（现为空对象，保持兼容性）
    - full_report_status: 完整报告状态
    - all_completed: 是否所有评估都已完成（基于full_report_status）
    """
    try:
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        full_report = await session_manager.get_full_report(session_id)
        
        # COMMENTED OUT: Fast evaluation disabled, using section evaluation instead
        # fast_evals = timeline_doc.get("evaluations", [])
        # aggregated = timeline_doc.get("aggregated_evaluation", {})
        
        # Keep original fields empty for backward compatibility
        fast_evals = []  # 空数组，保持向后兼容
        aggregated = {}  # 空对象，保持向后兼容
        
        # 获取section评估状态和full report状态
        full_report_status = timeline_doc.get("full_report_status", "pending")

        # 🚚 Legacy buffered video uploader (backend-local temp files).
        # Solution A uses frontend direct upload to Supabase, so this must stay OFF by default,
        # otherwise it can overwrite good Supabase URLs with placeholders ("skipped"/"failed").
        try:
            legacy_enabled = os.getenv("ENABLE_LEGACY_POST_EVAL_VIDEO_UPLOAD", "0").lower() in ("1", "true", "yes", "on")
            if legacy_enabled and full_report_status == "completed":
                sess = await session_manager.get_session(session_id)
                meta = getattr(sess, "metadata", {}) or {}
                if not meta.get("post_eval_upload_started"):
                    await session_manager.update_session_metadata(session_id, {"post_eval_upload_started": True})
                    asyncio.create_task(_upload_all_parked_videos(session_id))
                    log(f"[StreamInterview] 🚚 Post-evaluation upload scheduled for session {session_id}")
        except Exception as upload_schedule_err:
            print(f"[StreamInterview] ⚠️ Failed to schedule post-evaluation upload: {upload_schedule_err}")
        
        # 检查所有评估是否完成 - 基于full report状态而非fast evaluation
        # OLD: all_completed = all(eval_item.get("status") == "completed" for eval_item in fast_evals) and aggregated.get("status") == "completed"
        # NEW: 使用full report状态来判断评估是否完成
        all_completed = full_report_status == "completed"
        
        def _serialize_value(result: Any) -> Any:
            """
            Safely convert complex objects (Pydantic models, Enums, collections) to JSON-serializable values.
            Leave primitives unchanged.
            """
            try:
                if result is None:
                    return None
                if isinstance(result, Enum):
                    return result.value
                # Pydantic BaseModel (SectionEvaluationResult inherits from BaseModel)
                if hasattr(result, "model_dump"):
                    return result.model_dump(mode="json")
                # Dataclasses or other objects with dict conversion
                if hasattr(result, "dict"):
                    raw_dict = result.dict()  # type: ignore[attr-defined]
                    return {key: _serialize_value(value) for key, value in raw_dict.items()}
                if isinstance(result, dict):
                    return {
                        key: _serialize_value(value)
                        for key, value in result.items()
                    }
                if isinstance(result, (list, tuple, set)):
                    return [_serialize_value(item) for item in result]
                return result
            except Exception as serialization_error:
                print(f"[StreamInterview] ⚠️ Failed to serialize value: {serialization_error}")
                return {"error": "serialization_failed", "details": str(serialization_error)}

        # 计算evaluation_count基于section评估进度，并返回section评估结果
        section_evals = []
        evaluation_count = 0
        try:
            section_evals_raw = await session_manager.get_section_evaluations(session_id)
            if section_evals_raw:
                # 转换section评估结果为前端可用的格式
                section_evals = [
                    {
                        "turn_index": eval_item.get("turn_index"),
                        "section_index": eval_item.get("section_index"),
                        "status": eval_item.get("status"),
                        "section_result": _serialize_value(eval_item.get("section_result")),
                        "evaluation_time": eval_item.get("evaluation_time"),
                        "timestamp": eval_item.get("timestamp"),
                    }
                    for eval_item in section_evals_raw
                ]
                completed_sections = len([
                    eval_item for eval_item in section_evals_raw 
                    if eval_item.get("status") == "completed"
                ])
                evaluation_count = completed_sections
        except Exception as e:
            print(f"[StreamInterview] ⚠️ Error getting section evaluations: {e}")
            import traceback
            traceback.print_exc()
        
        serialized_full_report = _serialize_value(full_report)

        return JSONResponse({
            "fast_evaluations": fast_evals,  # 保持向后兼容
            "aggregated": aggregated,  # 保持向后兼容
            "section_evaluations": section_evals,  # 新增：section评估结果
            "full_report_status": full_report_status,
            "full_report": serialized_full_report,
            "all_completed": all_completed,  # 前端可以根据这个停止轮询
            "evaluation_count": evaluation_count,
            "timeline": timeline_doc,  # 💬 添加 timeline，包含 conversation
        })
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/upload-video-only")
async def upload_video_only(
    video_file: UploadFile = File(...),
    session_id: str = Form(...),
    segment_index: int = Form(...),
    duration: float = Form(...),
):
    """
    录制过程中上传视频（边录边传）- 增强版
    支持：
    1. 异步保存视频到临时路径
    2. 检查是否已有 Transcript
    3. 如果已有 Transcript，立即触发补救分析（Late Analysis）
    
    注意：Cloud Run 最大请求体限制为 32MB，如果视频文件过大，请使用分片上传（ingest-video-chunk）
    """
    log(f"[StreamInterview] 📥 upload-video-only called for session {session_id}, segment {segment_index}")
    
    # 检查文件大小（Cloud Run 限制为 32MB）
    MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB，留一些余量
    try:
        # 尝试获取文件大小（如果可用）
        if hasattr(video_file, 'size') and video_file.size:
            if video_file.size > MAX_FILE_SIZE:
                error_msg = f"Video file too large ({video_file.size / 1024 / 1024:.2f}MB). Maximum size is 30MB. Please use chunked upload (ingest-video-chunk) for large files."
                log(f"[StreamInterview] ✗ {error_msg}")
                return JSONResponse(
                    {"status": "error", "message": error_msg, "error_code": "FILE_TOO_LARGE"},
                    status_code=413
                )
    except Exception as size_check_err:
        log(f"[StreamInterview] ⚠️ Could not check file size: {size_check_err}")
        # 继续处理，让 Cloud Run 自己处理 413 错误
    
    # 1. 保存视频到可预测的临时路径
    temp_path = _get_temp_video_path(session_id, segment_index)
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        
        total_bytes = 0
        with open(temp_path, "wb") as f:
            while True:
                chunk = await video_file.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                total_bytes += len(chunk)
                # 在写入过程中也检查大小
                if total_bytes > MAX_FILE_SIZE:
                    os.unlink(temp_path)  # 删除部分写入的文件
                    error_msg = f"Video file exceeds maximum size (30MB). Received {total_bytes / 1024 / 1024:.2f}MB. Please use chunked upload (ingest-video-chunk) for large files."
                    log(f"[StreamInterview] ✗ {error_msg}")
                    return JSONResponse(
                        {"status": "error", "message": error_msg, "error_code": "FILE_TOO_LARGE"},
                        status_code=413
                    )
        
        file_size = os.path.getsize(temp_path)
        log(f"[StreamInterview] ✓ Video saved to {temp_path} ({file_size / 1024 / 1024:.2f}MB)")
    except Exception as save_err:
        log(f"[StreamInterview] ✗ Failed to save video: {save_err}")
        # 检查是否是 413 错误
        error_str = str(save_err).lower()
        if "413" in error_str or "payload too large" in error_str or "request entity too large" in error_str:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "Video file is too large (exceeds Cloud Run's 32MB limit). Please use chunked upload (ingest-video-chunk) for large files.",
                    "error_code": "FILE_TOO_LARGE"
                },
                status_code=413
            )
        return JSONResponse({"status": "error", "message": str(save_err)}, status_code=500)
    
    # 2. 检查是否已有 Transcript (即主请求是否已经处理完)
    transcript = await session_manager.get_segment_transcript(session_id, segment_index)
    
    if transcript:
        log(f"[StreamInterview] 🔄 Transcript found for segment {segment_index}, triggering LATE ANALYSIS...")
        
        # 3. 触发补救分析（final turn: skip nonverbal and mark analyzed)
        section_key = f"{session_id}:{segment_index}"
        try:
            sess = await session_manager.get_session(session_id)
            meta = getattr(sess, "metadata", {}) or {}
            language = meta.get("language", "ja")
            max_rounds_local = _resolve_target_rounds_from_metadata(meta)
            is_final_turn = segment_index >= max(0, max_rounds_local - 1)

            if is_final_turn:
                await session_manager.update_segment_nonverbal(
                    session_id=session_id,
                    segment_index=segment_index,
                    nonverbal_data={"analysis": {"skipped": True, "reason": "final_turn_skip_nonverbal"}},
                )
                log(f"[StreamInterview] ⏭️ Final turn: marked nonverbal analysis skipped (upload-video-only) seg={segment_index}")
            else:
                await section_task_queue.add_task(
                    section_key,
                    _process_video_analysis_only,
                    session_id=session_id,
                    parked_video_path=temp_path,
                    user_text=transcript,
                    duration=duration,
                    segment_index=segment_index,
                    realtime_nonverbal=None,
                    language=language,
                )
                log(f"[StreamInterview] ✅ Late analysis queued for segment {segment_index}")
        except Exception as queue_err:
            log(f"[StreamInterview] ✗ Failed to queue late analysis: {queue_err}")
    else:
        log(f"[StreamInterview] ⏳ No transcript yet for segment {segment_index}, video parked waiting for submit request")
    
    return JSONResponse({
        "status": "accepted",
        "message": "Video uploaded successfully",
        "video_url": None,
        "segment_index": segment_index,
        "duration": duration
    })


@router.post("/upload-segment-video")
async def upload_segment_video(
    background_tasks: BackgroundTasks,
    video_file: UploadFile = File(...),
    session_id: str = Form(...),
    segment_index: int = Form(...),
):
    """
    手动上传视频的能力已停用（保留接口以兼容旧客户端）
    前端如调用此接口，将收到上传已禁用的响应
    """
    log(f"[StreamInterview] ⚠️ Manual video upload disabled for session {session_id}, segment {segment_index}")
    
    # 读取文件内容后丢弃，避免阻塞客户端（保持兼容）
    try:
        await video_file.read()
    except Exception as read_err:
        print(f"[StreamInterview] ⚠️ Unable to read uploaded video (ignored): {read_err}")
    
    return JSONResponse({
        "status": "disabled",
        "message": "Video uploads to Supabase have been disabled. Nonverbal analysis remains available.",
        "video_url": None,
        "segment_index": segment_index
    })


@router.post("/end/{session_id}")
async def end_interview(
    session_id: str,
    position: Optional[str] = Form(None),
    interview_type: Optional[str] = Form(None),
    practice_category: Optional[str] = Form(None),
    video_urls: Optional[str] = Form(None),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    结束面试会话
    
    注意：此接口有两种调用方式：
    1. 从InterviewScreen调用（不带FormData）：仅结束会话，返回timeline，不保存数据库
    2. 从PracticeResultScreen调用（带FormData）：保存到数据库
    """
    try:
        # ✅ Accept both multipart/form-data and application/json payloads.
        # Some mobile clients/axios configs may send JSON even when you pass FormData.
        # If the request is JSON, Form(...) params will be None, so parse JSON body as a fallback.
        if request is not None and not video_urls:
            try:
                content_type = (request.headers.get("content-type") or "").lower()
                if "application/json" in content_type:
                    body = await request.json()
                    if isinstance(body, dict):
                        # allow both snake_case and camelCase
                        if not position:
                            position = body.get("position") or body.get("job_title")
                        if not interview_type:
                            interview_type = body.get("interview_type") or body.get("interviewType")
                        if not practice_category:
                            practice_category = body.get("practice_category") or body.get("practiceCategory")
                        vu = body.get("video_urls") or body.get("videoUrls")
                        if vu is not None:
                            if isinstance(vu, list):
                                video_urls = json.dumps(vu, ensure_ascii=False)
                            elif isinstance(vu, str):
                                video_urls = vu
            except Exception:
                # Best-effort only; never break end/save if body parsing fails
                pass

        try:
            timeline_doc = await session_manager.get_timeline_doc(session_id)
            session = await session_manager.get_session(session_id)
        except KeyError:
            log(f"[StreamInterview] ❌ Session not found on end: {session_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or expired."
            )
        print(f"[StreamInterview] Interview ended: session_id: {session_id}, user_id: {str(current_user.id)}")
        
        # 如果提供了interview_type，或者默认保存
        # 始终保存到数据库，以防止前端获取详情时404
        interview_type_val = interview_type or "practice"
        
        print(f"[StreamInterview] Saving to database - interview_type: {interview_type_val}, practice_category: {practice_category}")
        
        # 解析视频URLs
        video_url_list = []
        if video_urls:
            try:
                import json
                video_url_list = json.loads(video_urls)
                print(f"[StreamInterview] Received {len(video_url_list)} video URLs")
            except json.JSONDecodeError:
                print(f"[StreamInterview] Failed to parse video_urls: {video_urls}")

        # ✅ Best-effort: enqueue visual analysis by Supabase URLs (non-blocking)
        # This should never slow down DB save / result generation.
        if video_url_list:
            try:
                from app.services.video_segment_analysis_queue import VideoSegmentJob, enqueue as enqueue_video_segment

                session_metadata = getattr(session, "metadata", {}) or {}
                session_language = session_metadata.get("language", "ja")

                for idx, url in enumerate(video_url_list):
                    if not isinstance(url, str) or not url.startswith("http"):
                        continue
                    transcript = await session_manager.get_segment_transcript(session_id, idx) or ""
                    job = VideoSegmentJob(
                        session_id=session_id,
                        segment_index=int(idx),
                        segment_url=url,
                        duration=0.0,
                        transcript=transcript,
                        language=session_language,
                    )
                    await enqueue_video_segment(job)
            except Exception as e:
                print(f"[StreamInterview] ⚠️ enqueue video analysis failed (ignored): {e}")
        
        # 保存到数据库
        result = await interview_history_service.save_interview_to_db(
            session_id=session_id,
            user_id=str(current_user.id),
            position=position,
            role=session.role,
            timeline_doc=timeline_doc,
            db=db,
            interview_type=interview_type_val,
            practice_category=practice_category,
            video_urls=video_url_list
        )
        return JSONResponse(result)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/check-analysis/{session_id}")
async def check_analysis_status(session_id: str):
    """
    检查视频分析是否全部完成
    返回: {"complete": true/false, "total": N, "analyzed": M, "pending": K}
    """
    try:
        status = await session_manager.check_analysis_complete(session_id)
        return JSONResponse(status)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


# ========== 历史记录相关接口 ==========

@router.get("/user/by-supabase-id/{supabase_id}")
async def get_user_by_supabase_id(
    supabase_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    通过Supabase ID获取用户信息
    
    Args:
        supabase_id: Supabase Auth用户ID
    
    Returns:
        用户信息（包含应用内部的user_id）
    """
    user_info = await interview_history_service.get_user_by_supabase_id(supabase_id, db)
    return JSONResponse(user_info)


@router.get("/history/list")
async def get_interview_history(
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    获取用户的面试历史记录列表
    
    Args:
        user_id: 应用内部用户ID（users表的id字段）
        skip: 跳过的记录数（分页）
        limit: 返回的最大记录数
    
    Returns:
        面试历史列表（按完成时间倒序）
    """
    result = await interview_history_service.get_interview_history(user_id, skip, limit, db)
    return JSONResponse(result)


@router.get("/history/{interview_id}")
async def get_interview_detail(
    interview_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    获取面试详情（用于结果页和履历详情页）
    
    Returns:
        完整的面试数据，包括timeline、视频URLs、评估结果等
    """
    result = await interview_history_service.get_interview_detail(interview_id, db)
    return JSONResponse(result)


@router.get("/detail/{session_id}")
async def get_interview_by_session(
    session_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    通过session_id获取面试详情（用于视频回放页）
    
    Returns:
        完整的面试数据，包括timeline、视频URLs、评估结果等
    """
    result = await interview_history_service.get_interview_by_session_id(session_id, db)
    return JSONResponse(result)


@router.post("/fast-eval/{session_id}")
async def fast_evaluate_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    快速评估面试（使用v3/content规则，3-8秒返回结果）
    
    特点：
    - ⚡ 只调用一次LLM，速度快（3-8秒）
    - 📊 返回4个维度（clarity, evidence, impact, engagement）的评分和评语
    - 🎯 使用v3/content预设规则，与正式评估体系一致
    - 💰 成本低，适合面试结束后立即展示结果
    
    Returns:
        快速评估结果，包含overall_score和4个维度的详细反馈
    """
    try:
        log(f"[StreamInterview] 🚀 Fast evaluation requested for session: {session_id}")
        
        # 获取timeline
        timeline_doc = await session_manager.get_timeline_doc(session_id)
        conversation = timeline_doc.get("conversation", [])
        
        if not conversation:
            raise HTTPException(status_code=404, detail="No conversation found for this session")
        
        # 转换为fast-eval格式
        interview_data = []
        for msg in conversation:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                interview_data.append({
                    "role": "system" if role == "system" else "user",
                    "content": content,
                    "timestamp": msg.get("timestamp", {})
                })
        
        # 获取session信息
        session = await session_manager.get_session(session_id)
        metadata = getattr(session, "metadata", {}) or {}
        language = metadata.get("language", "ja")
        position = metadata.get("position") or session.role or "候选人"
        
        # 调用快速评估器
        evaluator = get_fast_evaluator()
        result = await evaluator.evaluate(
            interview_data=interview_data,
            position=position,
            language=language
        )
        
        # 转换为响应格式
        response_data = {
            "overall_score": result.overall_score,
            "overall_brief": result.overall_brief,
            "dimensions": {
                key: {
                    "score": dim.score,
                    "brief_feedback": dim.brief_feedback,
                    "detailed_feedback": dim.detailed_feedback
                }
                for key, dim in result.dimensions.items()
            }
        }
        
        log(f"[StreamInterview] ✅ Fast evaluation completed: {result.overall_score}/100")
        return JSONResponse(response_data)
        
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        log(f"[StreamInterview] ❌ Fast evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Fast evaluation failed: {str(e)}"
        )

