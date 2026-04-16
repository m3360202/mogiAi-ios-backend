"""
Simple section feedback service implementation.

This is a KISS (Keep It Simple and Stupid) implementation that generates
feedback for a single super-metric in a single section.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.services.evaluation.utils.litellm_client import acompletion
from pydantic import BaseModel

from app.services.evaluation.business.entities import DialogSection
from app.services.evaluation.business.repositories import DialogSectionRepo
from app.services.evaluation.business.services import (
    Logger,
    SimpleSectionFeedbackService,
)
from app.services.evaluation.business.value_objects import SuperMetric, SuperMetricFeedback

from .rule_based_feedback import build_rule_based_feedback


class MetricEvaluationData(BaseModel):
    """
    Pydantic model for metric evaluation data used in LLM prompts.
    """
    metric_type: str
    score_label: str


class SingleMetricData(BaseModel):
    """
    Pydantic model for a single metric data in evaluation.
    """
    metric: MetricEvaluationData
    sub_metrics: Dict[str, Any]


class EvaluationData(BaseModel):
    """
    Pydantic model for evaluation data sent to LLM.
    """
    super_metric_type: str
    section_index: int
    metrics: List[SingleMetricData]


class SingleSectionFeedbackResult(BaseModel):
    """
    Pydantic model for single section feedback result from LLM response.
    """
    super_metric_type: str
    brief_feedback: str
    revised_response: Optional[str] = ""
    feedback: str


class SimpleSectionFeedbackServiceImpl(SimpleSectionFeedbackService):
    """
    Simple implementation that generates feedback for one super-metric in one section.
    
    This service focuses on simplicity and clarity, handling one feedback generation at a time.
    """
    
    def __init__(self, logger: Logger, dialog_section_repo: DialogSectionRepo, model: str = "gpt-4o"):
        """
        Initialize the simple section feedback service.
        
        Args:
            logger: Logger service for logging operations
            dialog_section_repo: Repository for retrieving dialog sections
            model: LLM model to use for feedback generation
        """
        self.logger = logger
        self.dialog_section_repo = dialog_section_repo
        self.model = model
        self.temperature = 0.3
        
        # Load prompts
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Load system and user prompts from files."""
        try:
            # Get the directory containing prompt files
            prompt_dir = Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts" / "evaluation"
            
            # Load section-level prompts (v3)
            section_prompt_dir = prompt_dir / "v3"
            
            # Initialize prompt dictionaries
            self.section_system_prompts = {}
            self.section_user_prompt_templates = {}
            
            # Load v3/content dimension-specific prompts
            self.v3_content_system_prompts = {}  # {lang: {dimension: prompt}}
            self.v3_content_user_prompt_templates = {}  # {lang: {dimension: template}}
            
            # Load prompts for each supported language
            languages = ["ja", "zh", "en"]
            
            # Load v3/content rules for content dimensions
            content_dimensions = ["clarity", "evidence", "impact", "engagement"]
            v3_content_dir = prompt_dir / "v3" / "content"
            
            for lang in languages:
                self.v3_content_system_prompts[lang] = {}
                self.v3_content_user_prompt_templates[lang] = {}
                
                for dim in content_dimensions:
                    dim_dir = v3_content_dir / dim
                    sys_path = dim_dir / f"system_msg_{lang}.md"
                    user_path = dim_dir / f"user_msg_{lang}.md"
                    
                    # Try to load dimension-specific prompts
                    if sys_path.exists():
                        try:
                            self.v3_content_system_prompts[lang][dim] = sys_path.read_text(encoding="utf-8")
                        except Exception:
                            pass
                    # Fallback to zh if lang-specific not found
                    if dim not in self.v3_content_system_prompts[lang] and lang != "zh":
                        sys_path_fallback = dim_dir / "system_msg_zh.md"
                        if sys_path_fallback.exists():
                            try:
                                self.v3_content_system_prompts[lang][dim] = sys_path_fallback.read_text(encoding="utf-8")
                            except Exception:
                                pass
                    
                    if user_path.exists():
                        try:
                            self.v3_content_user_prompt_templates[lang][dim] = user_path.read_text(encoding="utf-8")
                        except Exception:
                            pass
                    # Fallback to zh if lang-specific not found
                    if dim not in self.v3_content_user_prompt_templates[lang] and lang != "zh":
                        user_path_fallback = dim_dir / "user_msg_zh.md"
                        if user_path_fallback.exists():
                            try:
                                self.v3_content_user_prompt_templates[lang][dim] = user_path_fallback.read_text(encoding="utf-8")
                            except Exception:
                                pass
            
            for lang in languages:
                # System prompts
                # Prefer: extract section-feedback template from unified v3 prompt (single source of truth)
                def _extract_block(text: str, start: str, end: str) -> str:
                    if not isinstance(text, str) or not text:
                        return ""
                    s = text.find(start)
                    if s == -1:
                        return ""
                    e = text.find(end, s + len(start))
                    if e == -1:
                        return ""
                    return text[s + len(start):e].strip()

                unified_path = section_prompt_dir / f"prompt_unified_evaluation_system_msg_{lang}.md"
                unified_text = ""
                if unified_path.exists():
                    try:
                        unified_text = unified_path.read_text(encoding="utf-8")
                    except Exception:
                        unified_text = ""
                # fallback unified prompt if missing
                if not unified_text:
                    unified_fallback = section_prompt_dir / "prompt_unified_evaluation_system_msg_ja.md"
                    if unified_fallback.exists():
                        try:
                            unified_text = unified_fallback.read_text(encoding="utf-8")
                        except Exception:
                            unified_text = ""

                block = _extract_block(
                    unified_text,
                    "## 【SECTION_FEEDBACK_SYSTEM_PROMPT】",
                    "## 【END_SECTION_FEEDBACK_SYSTEM_PROMPT】",
                )
                if block:
                    self.section_system_prompts[lang] = block
                else:
                    # Fallback: legacy section feedback system prompt file
                    sys_filename = f"prompt_section_feedback_system_msg_{lang}.md"
                    sys_path = section_prompt_dir / sys_filename
                    if sys_path.exists():
                        with open(sys_path, "r", encoding="utf-8") as f:
                            self.section_system_prompts[lang] = f.read()
                    else:
                        if lang == "ja":
                            sys_path_legacy = section_prompt_dir / "prompt_section_feedback_system_msg.md"
                            if sys_path_legacy.exists():
                                with open(sys_path_legacy, "r", encoding="utf-8") as f:
                                    self.section_system_prompts[lang] = f.read()
                
                # User prompts
                user_filename = f"prompt_section_feedback_user_msg_{lang}.md"
                user_path = section_prompt_dir / user_filename
                
                if user_path.exists():
                    with open(user_path, 'r', encoding='utf-8') as f:
                        self.section_user_prompt_templates[lang] = f.read()
                else:
                    if lang == "ja":
                        user_path_legacy = section_prompt_dir / "prompt_section_feedback_user_msg.md"
                        if user_path_legacy.exists():
                            with open(user_path_legacy, 'r', encoding='utf-8') as f:
                                self.section_user_prompt_templates[lang] = f.read()
            
            # Set default prompts (ja) for backward compatibility
            self.section_system_prompt = self.section_system_prompts.get("ja", "")
            self.section_user_prompt_template = self.section_user_prompt_templates.get("ja", "")
                
            self.logger.debug("Successfully loaded section feedback prompts", {
                "languages": list(self.section_system_prompts.keys()),
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            
        except Exception as e:
            self.logger.error("Failed to load feedback prompts", e, {
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            raise
    
    def _format_timestamp(self, value: Any) -> str:
        """
        Safely format timestamp values for JSON payloads.

        Windows 的 datetime.timestamp 在 1970 之前会抛 Errno 22，
        因此统一转换为 ISO8601 字符串，避免平台差异。
        """
        if isinstance(value, datetime):
            return value.isoformat()
        # 兼容 float/int/string 等类型
        return str(value)

    async def _call_llm_with_json_response(self, messages: List[Dict[str, str]]) -> Any:
        """
        Helper method to call LiteLLM and parse JSON response.
        
        Args:
            messages: List of message dictionaries for the LLM
            
        Returns:
            Parsed JSON response as dictionary
        """
        try:
            response = await acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content  # type: ignore
            if content is None:
                raise ValueError("LLM returned empty content")
            return json.loads(content)  # type: ignore
                
        except Exception as e:
            self.logger.error("Failed to call LLM for feedback generation", e, {
                "model": self.model,
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            raise
    
    async def generate_feedback_for_super_metric(
        self, 
        section: DialogSection, 
        super_metric: SuperMetric,
        language: str = "ja",
        current_score: Optional[float] = None,
        previous_score: Optional[float] = None
    ) -> SuperMetricFeedback:
        """
        Generate feedback for a single super-metric in a single section.
        
        Args:
            section: The dialog section to generate feedback for
            super_metric: The super-metric with score to generate feedback for
            language: Language for the feedback (ja/en/zh)
            
        Returns:
            SuperMetricFeedback: Generated feedback for this super-metric in this section
        """
        try:
            self.logger.debug(f"Generating feedback for super-metric {super_metric.metadata.super_metric_type.value} in section {section.id}", {
                "section_id": section.id,
                "section_index": section.section_index,
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "language": language,
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            
            # Prepare section data in expected JSON format
            section_data: Dict[str, Any] = {
                "section_index": section.section_index,
                "messages": []
            }
            
            for message in section.messages:
                role_label = "interviewer" if message.role.value == "INTERVIEWER" else "candidate"
                section_data["messages"].append({
                    "role": role_label,
                    "start_time": self._format_timestamp(message.start_time),
                    "end_time": self._format_timestamp(message.end_time),
                    "content": message.content
                })
            
            # Convert metric groups to the expected format using Pydantic models
            metrics_data: List[SingleMetricData] = []
            for metric_group in super_metric.metric_groups:
                for metric in metric_group.metrics:
                    # Use Pydantic models for proper serialization
                    metric_eval_data = MetricEvaluationData(
                        metric_type=metric.metadata.metric_type.value,
                        score_label=metric.score.score_label.value
                    )
                    
                    # Since metric.sub_metrics is already a Dict[str, Any] from Pydantic serialization,
                    # we can use it directly. The Pydantic model ensures proper validation and serialization
                    single_metric = SingleMetricData(
                        metric=metric_eval_data,
                        sub_metrics=metric.sub_metrics
                    )
                    metrics_data.append(single_metric)
            
            # Create evaluation data using Pydantic model for proper serialization
            evaluation_data_model = EvaluationData(
                super_metric_type=super_metric.metadata.super_metric_type.value,
                section_index=section.section_index,
                metrics=metrics_data
            )
            
            # Check if this is a content dimension that should use v3/content rules
            super_metric_type = super_metric.metadata.super_metric_type.value
            content_dimension_map = {
                "CLARITY": "clarity",
                "EVIDENCE": "evidence",
                "IMPACT": "impact",
                "ENGAGEMENT": "engagement"
            }
            
            # Get appropriate prompts for the language
            target_lang = language if language in self.section_system_prompts else "ja"
            
            # Use v3/content rules for content dimensions if available
            if super_metric_type in content_dimension_map:
                dim_key = content_dimension_map[super_metric_type]
                v3_sys_prompts = self.v3_content_system_prompts.get(target_lang, {})
                v3_user_templates = self.v3_content_user_prompt_templates.get(target_lang, {})
                
                # Try to use v3/content prompts
                if dim_key in v3_sys_prompts and dim_key in v3_user_templates:
                    system_prompt = v3_sys_prompts[dim_key]
                    user_prompt_template = v3_user_templates[dim_key]
                    self.logger.debug(f"Using v3/content rules for {super_metric_type}", {
                        "dimension": dim_key,
                        "language": target_lang
                    })
                else:
                    # Fallback to generic prompts
                    system_prompt = self.section_system_prompts.get(target_lang) or self.section_system_prompts.get("ja") or list(self.section_system_prompts.values())[0]
                    user_prompt_template = self.section_user_prompt_templates.get(target_lang) or self.section_user_prompt_templates.get("ja") or list(self.section_user_prompt_templates.values())[0]
            else:
                # Use generic prompts for non-content dimensions
                system_prompt = self.section_system_prompts.get(target_lang) or self.section_system_prompts.get("ja") or list(self.section_system_prompts.values())[0]
                user_prompt_template = self.section_user_prompt_templates.get(target_lang) or self.section_user_prompt_templates.get("ja") or list(self.section_user_prompt_templates.values())[0]
            
            # Calculate current score from super_metric if not provided
            if current_score is None:
                current_score = super_metric.score.numeric_score
            
            # Prepare score information for user message
            current_score_str = f"{current_score:.1f}" if current_score is not None else "N/A"
            previous_score_str = f"{previous_score:.1f}" if previous_score is not None else "N/A"
            
            if current_score is not None and previous_score is not None:
                score_diff = current_score - previous_score
                if score_diff > 0:
                    score_change_str = f"提升了 {score_diff:.1f} 分" if language.startswith("zh") else f"向上 {score_diff:.1f}点" if language.startswith("ja") else f"increased by {score_diff:.1f} points"
                elif score_diff < 0:
                    score_change_str = f"下降了 {abs(score_diff):.1f} 分" if language.startswith("zh") else f"向下 {abs(score_diff):.1f}点" if language.startswith("ja") else f"decreased by {abs(score_diff):.1f} points"
                else:
                    score_change_str = "无变化" if language.startswith("zh") else "変化なし" if language.startswith("ja") else "no change"
            else:
                score_change_str = "无历史记录" if language.startswith("zh") else "履歴なし" if language.startswith("ja") else "no history"
            
            # Prepare user message for LLM
            # For v3/content prompts, format with transcript, question, and previous_scores
            if super_metric_type in content_dimension_map:
                # Extract transcript and question from section_data
                transcript = ""
                question = ""
                for msg in section_data.get("messages", []):
                    if msg.get("role") == "candidate":
                        transcript = msg.get("content", "")
                    elif msg.get("role") == "interviewer":
                        question = msg.get("content", "")
                
                # Format v3/content user prompt
                user_message = user_prompt_template.format(
                    language=target_lang,
                    transcript=transcript,
                    question=question or "（なし）",
                    previous_scores=f"当前得分: {current_score_str}, 上次得分: {previous_score_str}" if target_lang.startswith("zh") else f"現在のスコア: {current_score_str}, 前回のスコア: {previous_score_str}" if target_lang.startswith("ja") else f"Current: {current_score_str}, Previous: {previous_score_str}"
                )
            else:
                # Use generic format for non-content dimensions
                user_message = user_prompt_template.format(
                    section_data=json.dumps(section_data, ensure_ascii=False, indent=2),
                    evaluation_data=evaluation_data_model.model_dump_json(indent=2),
                    current_score=current_score_str,
                    previous_score=previous_score_str,
                    score_change=score_change_str
                )
            
            # Call LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            self.logger.info(f"Calling LLM for feedback generation", {
                "section_id": section.id,
                "section_index": section.section_index,
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            
            response_data = await self._call_llm_with_json_response(messages)
            
            self.logger.info(f"LLM response received", {
                "section_id": section.id,
                "section_index": section.section_index,
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "response_keys": list(response_data.keys()) if isinstance(response_data, dict) else "not_dict",
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            
            # Parse response and create feedback
            feedback_result = SingleSectionFeedbackResult(**response_data)
            
            feedback_text = feedback_result.feedback
            
            # ⚡ 如果是 VERBAL_PERFORMANCE，且 feedback 中不包含语速，则追加计算出的语速
            if super_metric.metadata.super_metric_type.value == "VERBAL_PERFORMANCE":
                # 尝试从 dialog section 中恢复语速数据
                # section.messages -> candidate message -> content
                candidate_msg = next((m for m in section.messages if m.role.value == "CANDIDATE"), None)
                if candidate_msg and candidate_msg.content:
                    transcript = candidate_msg.content
                    duration_sec = 0
                    if candidate_msg.end_time and candidate_msg.start_time:
                        duration_sec = (candidate_msg.end_time - candidate_msg.start_time).total_seconds()
                    
                    if duration_sec > 0:
                        cpm_info = None
                        if language.startswith("zh") or language.startswith("ja"):
                            count = len(transcript.replace(" ", "").replace("\n", ""))
                            cpm = int(count / (duration_sec / 60))
                            cpm_info = f"{cpm} CPM (Characters Per Minute)"
                        else:
                            count = len(transcript.split())
                            wpm = int(count / (duration_sec / 60))
                            cpm_info = f"{wpm} WPM (Words Per Minute)"
                        
                        # 如果文本中还没有语速信息，则追加
                        if cpm_info and cpm_info not in feedback_text:
                            label = "📊 平均話速："
                            if language.startswith("zh"):
                                label = "📊 平均语速："
                            elif language.startswith("en"):
                                label = "📊 Average Speaking Rate: "
                            
                            feedback_text = f"{feedback_text}\n\n{label}{cpm_info}"
                            self.logger.debug(f"Appended calculated speaking rate to verbal feedback: {cpm_info}")

            feedback = SuperMetricFeedback(
                brief_feedback=feedback_result.brief_feedback,
                revised_response=feedback_result.revised_response or "",
                feedback=feedback_text,
                section_index=section.section_index
            )
            
            self.logger.debug(f"Successfully generated feedback for super-metric {super_metric.metadata.super_metric_type.value}", {
                "section_id": section.id,
                "section_index": section.section_index,
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            
            return feedback
            
        except Exception as e:
            self.logger.error(f"Failed to generate feedback for super-metric {super_metric.metadata.super_metric_type.value}", e, {
                "section_id": section.id,
                "section_index": section.section_index,
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "service": "SimpleSectionFeedbackServiceImpl"
            })
            
            # Return placeholder feedback on error
            return self._create_placeholder_feedback(section, super_metric)
    
    def _create_placeholder_feedback(self, section: DialogSection, super_metric: SuperMetric) -> SuperMetricFeedback:
        """
        Create placeholder feedback when LLM call fails.
        
        Args:
            section: The dialog section
            super_metric: The super-metric
            
        Returns:
            SuperMetricFeedback: Placeholder feedback
        """
        return build_rule_based_feedback(super_metric, section)