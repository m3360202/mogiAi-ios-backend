"""
Adapters for transforming between API DTOs and business entities
"""
from datetime import datetime
from typing import List, Optional
import uuid

from app.schemas.evaluation import InterviewEvalRequest, InterviewEvalResponse, NonverbalPerformance
from app.services.evaluation.business.entities import EvaluationRecord
from app.services.evaluation.business.value_objects import (
    DialogMessage, 
    RawDialogInfo, 
    NonverbalPerformance as BusinessNonverbalPerformance,
    VoicePerformance as BusinessVoicePerformance,
    VisualPerformance as BusinessVisualPerformance
)
from app.services.evaluation.business.enums import MessageRole, ScoreLabel


def _default_suggestions(metric_key: str, language: str) -> str:
    """
    Provide a small, deterministic fallback suggestion list per metric,
    so the UI never shows an empty '- ' placeholder.
    """
    lang = (language or "ja").lower()
    key = (metric_key or "").lower()

    if lang.startswith("zh"):
        # Deprecated: Do not use hardcoded suggestions as they confuse users.
        # Return generic prompting if LLM failed to generate suggestions.
        return "（请参考详细评价中的具体分析，结合自身情况进行改进。）"

    if lang.startswith("en"):
        return "(Please refer to the detailed evaluation for specific improvement steps.)"

    # ja
    return "（詳細評価を参考に、具体的な改善点を確認してください。）"


def _ensure_two_part_feedback(feedback: str, language: str, metric_key: str = "") -> str:
    """
    Enforce the required two-part structure:
    - Detailed evaluation section
    - Improvement suggestions section

    This is a defensive backend guard so even if upstream feedback generation
    returns a plain paragraph, the API payload still matches the expected format.
    """
    if not isinstance(feedback, str):
        feedback = "" if feedback is None else str(feedback)
    text = feedback.strip()
    if not text:
        text = "-"

    lang = (language or "ja").lower()
    if lang.startswith("zh"):
        det = "🔸 详细评价："
        sug = "💡 改进建议："
        has_det = ("🔸" in text) and ("详细" in text or "评价" in text)
        has_sug = ("💡" in text) and ("改进建议" in text or "改善提案" in text)
    elif lang.startswith("en"):
        det = "🔸 Detailed evaluation:"
        sug = "💡 Improvement suggestions:"
        has_det = "🔸" in text and "detailed" in text.lower()
        has_sug = "💡" in text and "improvement" in text.lower()
    else:
        det = "🔸 詳細評価："
        sug = "💡 改善提案："
        has_det = ("🔸" in text) and ("詳細" in text or "評価" in text)
        has_sug = ("💡" in text) and ("改善提案" in text)

    if has_det and has_sug:
        # Normalize formatting to guarantee the UI renders two sections on separate lines.
        # Some upstream models return: "🔸 詳細評価：... 💡 改善提案：..." without line breaks.
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Ensure a newline after the detailed header marker
        det_pos = text.find(det)
        if det_pos >= 0:
            det_end = det_pos + len(det)
            if det_end < len(text) and text[det_end] != "\n":
                text = text[:det_end] + "\n" + text[det_end:].lstrip(" ")

        # Ensure suggestions header starts on a new paragraph
        sug_pos = text.find(sug)
        if sug_pos > 0:
            prefix = text[:sug_pos].rstrip()
            suffix = text[sug_pos:]  # starts with sug
            prefix = prefix.rstrip("\n") + "\n\n"
            text = prefix + suffix

        # Ensure a newline after the suggestions header marker
        sug_pos2 = text.find(sug)
        if sug_pos2 >= 0:
            sug_end = sug_pos2 + len(sug)
            if sug_end < len(text) and text[sug_end] != "\n":
                text = text[:sug_end] + "\n" + text[sug_end:].lstrip(" ")

        # If suggestions section is effectively empty (e.g. "- " only), fill it.
        if "\n- " in text and text.strip().endswith("-"):
            filled = _default_suggestions(metric_key, language)
            return text.rstrip().rstrip("-").rstrip() + "\n" + filled
        if "\n- " in text and text.strip().endswith("- "):
            filled = _default_suggestions(metric_key, language)
            return text.rstrip().rstrip("-").rstrip() + "\n" + filled
        return text

    # If the upstream already included one of the sections, keep it and add the missing one.
    # Otherwise, wrap the whole content as the detailed evaluation and add an empty suggestions stub.
    if has_det and not has_sug:
        return f"{text}\n\n{sug}\n{_default_suggestions(metric_key, language)}"
    if not has_det and has_sug:
        return f"{det}\n{text}"
    return f"{det}\n{text}\n\n{sug}\n{_default_suggestions(metric_key, language)}"


def _convert_nonverbal_to_business(api_nonverbal: Optional[NonverbalPerformance]) -> Optional[BusinessNonverbalPerformance]:
    """
    Convert API NonverbalPerformance to business domain NonverbalPerformance.
    """
    if not api_nonverbal:
        return None
    
    # Convert voice performance
    business_voice = None
    if api_nonverbal.voice_performance:
        voice_api = api_nonverbal.voice_performance
        business_voice = BusinessVoicePerformance(
            speed=voice_api.speed,
            tone=voice_api.tone,
            volume=voice_api.volume,
            pronunciation=voice_api.pronunciation,
            pause=voice_api.pause,
            summary=voice_api.summary,
            speed_score_label=voice_api.speed_score_label,
            tone_score_label=voice_api.tone_score_label,
            volume_score_label=voice_api.volume_score_label,
            pronunciation_score_label=voice_api.pronunciation_score_label,
            pause_score_label=voice_api.pause_score_label,
        )
    
    # Convert visual performance
    business_visual = None
    if api_nonverbal.visual_performance:
        visual_api = api_nonverbal.visual_performance
        business_visual = BusinessVisualPerformance(
            eye_contact=visual_api.eye_contact,
            facial_expression=visual_api.facial_expression,
            body_posture=visual_api.body_posture,
            appearance=visual_api.appearance,
            summary=visual_api.summary,
            eye_contact_score_label=visual_api.eye_contact_score_label,
            facial_expression_score_label=visual_api.facial_expression_score_label,
            body_posture_score_label=visual_api.body_posture_score_label,
            appearance_score_label=visual_api.appearance_score_label,
        )
    
    return BusinessNonverbalPerformance(
        voice_performance=business_voice,
        visual_performance=business_visual
    )


def parse_eval_request(request: InterviewEvalRequest) -> RawDialogInfo:
    """
    Convert InterviewEvalRequest to RawDialogInfo for evaluation processing.
    """
    # Generate a unique dialog ID
    dialog_id = str(uuid.uuid4())
    
    # Convert interview dialog items to DialogMessage objects
    messages: List[DialogMessage] = []
    for item in request.interview:
        # Parse timestamp strings to datetime
        # Assuming timestamp format like "0:00:00" represents seconds from start
        start_time_parts = item.timestamp.start.split(":")
        start_seconds = int(start_time_parts[0]) * 3600 + int(start_time_parts[1]) * 60 + int(start_time_parts[2])
        
        end_time_parts = item.timestamp.end.split(":")
        end_seconds = int(end_time_parts[0]) * 3600 + int(end_time_parts[1]) * 60 + int(end_time_parts[2])
        
        # Use epoch time with offset for simplicity
        start_time = datetime.fromtimestamp(start_seconds)
        end_time = datetime.fromtimestamp(end_seconds)
        
        # Map role from API schema to business enum
        role = MessageRole.INTERVIEWER if item.role == "agent" else MessageRole.CANDIDATE
        
        # Convert nonverbal performance from API to business domain
        business_nonverbal = _convert_nonverbal_to_business(item.nonverbal)
        
        target_dimensions = None
        if isinstance(item.target_dimensions, list):
            dims: List[str] = []
            for dim in item.target_dimensions:
                if isinstance(dim, str):
                    normalized = dim.strip()
                    if normalized and normalized not in dims:
                        dims.append(normalized)
            if dims:
                target_dimensions = dims

        message = DialogMessage(
            section_id=dialog_id,  # Use dialog_id as section_id for now
            role=role,
            content=item.content,
            start_time=start_time,
            end_time=end_time,
            nonverbal=business_nonverbal,
            target_dimensions=target_dimensions,
        )
        messages.append(message)
    
    return RawDialogInfo(
        dialog_id=dialog_id,
        messages=messages,
        language=request.language
    )


def pack_eval_response(evaluation: EvaluationRecord, language: str = "ja") -> InterviewEvalResponse:
    """
    Convert EvaluationRecord to InterviewEvalResponse for API response.
    """
    from typing import Dict, Any
    
    # Map super metric types to response field names
    super_metric_mapping = {
        "CLARITY": "clarity",
        "EVIDENCE": "evidence", 
        "IMPACT": "impact",
        "ENGAGEMENT": "engagement",
        "VERBAL_PERFORMANCE": "verbal_performance",
        "VISUAL_PERFORMANCE": "visual_performance"
    }
    
    # Map score labels to response format
    def map_score_label(label_enum: ScoreLabel) -> str:
        label_str = str(label_enum.value)
        return label_str.title()  # Convert "GOOD" -> "Good", "FAIR" -> "Fair", "POOR" -> "Poor"
    
    # Build the response data structure
    data: Dict[str, Any] = {
        "overall": {
            "score": int(evaluation.overall_score.numeric_score),
            "label": map_score_label(evaluation.overall_score.score_label)
        }
    }
    
    # Add super metric evaluations
    for super_metric in evaluation.super_metrics:
        metric_type = super_metric.metadata.super_metric_type.value
        metric_key = super_metric_mapping.get(metric_type, metric_type.lower())
        
        raw_feedback = super_metric.feedback.feedback
        # Light tone guard: shift obvious 3rd-person "candidate" wording to 2nd-person where safe.
        if isinstance(raw_feedback, str):
            lang = (language or "ja").lower()
            if lang.startswith("zh"):
                raw_feedback = raw_feedback.replace("候选人", "你")
            elif lang.startswith("en"):
                raw_feedback = raw_feedback.replace("the candidate", "you").replace("The candidate", "You")
            else:
                raw_feedback = raw_feedback.replace("候補者", "あなた")

        data[metric_key] = {
            "score": int(super_metric.score.numeric_score),
            "label": map_score_label(super_metric.score.score_label),
            "brief": super_metric.feedback.brief_feedback,
            "feedback": _ensure_two_part_feedback(raw_feedback, language=language, metric_key=metric_key),
        }
    
    return InterviewEvalResponse(
        code=0,
        msg="success", 
        data=data
    )