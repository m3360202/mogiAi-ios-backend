"""
Section-based super-metric feedback service implementation.
"""
import json
import random
from app.services.evaluation.utils.litellm_client import acompletion
from pathlib import Path
from typing import List, Dict, Set, Any
from pydantic import BaseModel

from app.services.evaluation.business import (
    SuperMetricFeedbackService,
    SuperMetric,
    SuperMetricFeedback,
    SuperMetricSectionFeedback,
    SuperMetricFeedbackContributorSectionGroup,
    SuperMetricType,
    DialogSectionRepo,
    Logger
)


class SectionFeedbackResult(BaseModel):
    """
    Pydantic model for individual section feedback result from LLM response.
    """
    section_index: int
    super_metric_type: str
    brief_feedback: str
    revised_response: str
    feedback: str


class SectionBasedSuperMetricFeedbackService(SuperMetricFeedbackService):
    """
    Implementation of SuperMetricFeedbackService that generates feedback for each section 
    independently and then selects the best feedback as overall feedback.
    
    Process flow:
    1. Generate feedback for each section of each super-metric independently using LLM
    2. Pick contributing sections from the generated section feedbacks
    3. Use the feedback from contributing sections as overall super-metric feedback (no additional LLM call)
    """
    
    def __init__(self, logger: Logger, dialog_section_repo: DialogSectionRepo, model: str = "gpt-4o"):
        """
        Initialize the section-based super-metric feedback service.
        
        Args:
            logger: Logger service for logging operations
            dialog_section_repo: Repository for retrieving dialog sections
            model: LLM model to use for feedback generation (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
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
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            
        except Exception as e:
            self.logger.error("Failed to load feedback prompts", e, {
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            raise
    
    async def _call_llm_with_json_response(self, messages: List[Dict[str, str]]) -> Any:
        """
        Helper method to call LiteLLM and parse JSON response.
        
        Args:
            messages: List of message dictionaries for the LLM
            
        Returns:
            Parsed JSON response as dictionary
        """
        try:
            # Note: LiteLLM doesn't have comprehensive type stubs yet
            response = await acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                response_format={"type": "json_object"},  # Force JSON output
            )
            
            # Extract content and parse as JSON
            content = response.choices[0].message.content  # type: ignore
            if isinstance(content, str):
                return json.loads(content)
            else:
                raise ValueError("Unexpected response content type - expected string")
                
        except Exception as e:
            self.logger.error("LiteLLM API call failed for feedback generation", e, {
                "model": self.model,
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            raise
    
    async def generate_and_update_feedback(self, super_metrics: List[SuperMetric], language: str = "ja") -> List[SuperMetric]:
        """
        Generate and update feedback for all super-metrics with section-based approach.
        
        Steps:
        1. Generate feedback for each section of each super-metric independently
        2. Pick contributing sections from the generated section feedbacks
        3. Generate and update overall super-metric feedback
        4. Return updated SuperMetric list
        
        Args:
            super_metrics: List of super-metrics to generate feedback for
            language: Language for the feedback (ja/en/zh)
            
        Returns:
            List[SuperMetric]: Updated super-metrics with generated feedback
        """
        try:
            self.logger.info("Starting section-based feedback generation and update process", {
                "super_metrics_count": len(super_metrics),
                "language": language,
                "service": "SectionBasedSuperMetricFeedbackService"
            })

            # Step 1: Generate section-level feedback for each super-metric
            updated_super_metrics_with_section_feedback = await self._generate_section_feedbacks(super_metrics, language)
            
            # Step 2: Pick contributing sections from the generated section feedbacks
            contributing_section_groups = self._pick_contributing_sections_from_feedbacks(updated_super_metrics_with_section_feedback)
            
            # Step 3: Generate overall feedback for all super-metrics
            overall_feedback_map = self._generate_overall_feedback(contributing_section_groups, updated_super_metrics_with_section_feedback)
            
            # Step 4: Update SuperMetric entities with overall feedback
            final_updated_super_metrics = self._update_super_metrics_with_overall_feedback(updated_super_metrics_with_section_feedback, overall_feedback_map)
            
            self.logger.info("Successfully completed section-based feedback generation and update process", {
                "super_metrics_count": len(final_updated_super_metrics),
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            
            return final_updated_super_metrics
            
        except Exception as e:
            self.logger.error("Failed to generate and update section-based feedback", e, {
                "super_metrics_count": len(super_metrics),
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            raise
    
    async def _generate_section_feedbacks(self, super_metrics: List[SuperMetric], language: str = "ja") -> List[SuperMetric]:
        """
        Generate feedback for each section of each super-metric independently.
        
        Args:
            super_metrics: List of super-metrics to generate section feedbacks for
            language: Language for the feedback
            
        Returns:
            List[SuperMetric]: Super-metrics updated with section feedbacks
        """
        self.logger.debug("Generating section-level feedbacks for super-metrics", {
            "super_metrics_count": len(super_metrics),
            "language": language,
            "service": "SectionBasedSuperMetricFeedbackService"
        })
        
        updated_super_metrics = []
        
        for super_metric in super_metrics:
            section_feedbacks = []
            
            # Generate feedback for each section in this super-metric
            for section_score in super_metric.section_scores:
                section_feedback = await self._generate_single_section_feedback(
                    super_metric, section_score.section_id, section_score.section_index, language
                )
                if section_feedback:
                    section_feedbacks.append(section_feedback)
            
            # Create updated super-metric with section feedbacks
            updated_super_metric = super_metric.model_copy(
                update={"section_feedbacks": section_feedbacks}
            )
            updated_super_metrics.append(updated_super_metric)
        
        return updated_super_metrics
    
    async def _generate_single_section_feedback(
        self, 
        super_metric: SuperMetric, 
        section_id: str, 
        section_index: int,
        language: str = "ja"
    ) -> SuperMetricSectionFeedback | None:
        """
        Generate feedback for a single section of a super-metric.
        
        Args:
            super_metric: The super-metric this section belongs to
            section_id: ID of the dialog section
            section_index: Index of the dialog section
            language: Language for the feedback
            
        Returns:
            SuperMetricSectionFeedback if successful, None if failed
        """
        try:
            # Get dialog section data
            dialog_section = self.dialog_section_repo.get_by_id(section_id)
            if not dialog_section:
                self.logger.warning("Dialog section not found", context={
                    "section_id": section_id,
                    "service": "SectionBasedSuperMetricFeedbackService"
                })
                return None
            
            # Build section data for prompt
            section_data = {
                "section_index": section_index,
                "messages": []
            }
            
            for message in dialog_section.messages:
                section_data["messages"].append({
                    "role": message.role.value.lower(),
                    "start_time": message.start_time.timestamp(),
                    "end_time": message.end_time.timestamp(),
                    "content": message.content
                })
            
            # Build evaluation data for this section
            evaluation_data = {
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "section_index": section_index,
                "metrics": []
            }
            
            # Find metrics for this section from the super-metric's metric groups
            for metric_group in super_metric.metric_groups:
                for metric in metric_group.metrics:
                    if metric.dialog_section_index == section_index:
                        evaluation_data["metrics"].append({
                            "metric": {
                                "metric_type": metric.metadata.metric_type.value,
                                "score_label": metric.score.score_label.value
                            },
                            "sub_metrics": metric.sub_metrics
                        })
            
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
            
            # Create prompt messages
            # For v3/content prompts, format with transcript, question, and previous_scores
            if super_metric_type in content_dimension_map:
                # Extract transcript and question from section_data
                transcript = ""
                question = ""
                for msg in section_data.get("messages", []):
                    if msg.get("role") == "candidate" or msg.get("role") == "user":
                        transcript = msg.get("content", "")
                    elif msg.get("role") == "interviewer" or msg.get("role") == "system":
                        question = msg.get("content", "")
                
                # Format v3/content user prompt
                user_prompt = user_prompt_template.format(
                    language=target_lang,
                    transcript=transcript,
                    question=question or "（なし）",
                    previous_scores="（なし）"  # Could be enhanced to pass actual previous scores
                )
            else:
                # Use generic format for non-content dimensions
                user_prompt = user_prompt_template.format(
                    section_data=json.dumps(section_data, indent=2, ensure_ascii=False),
                    evaluation_data=json.dumps(evaluation_data, indent=2, ensure_ascii=False)
                )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Call LLM
            response_data = await self._call_llm_with_json_response(messages)
            
            # Create section feedback
            return SuperMetricSectionFeedback(
                section_id=section_id,
                section_index=section_index,
                brief_feedback=response_data["brief_feedback"],
                revised_response=response_data["revised_response"],
                feedback=response_data["feedback"]
            )
            
        except Exception as e:
            self.logger.error("Failed to generate section feedback", e, {
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "section_id": section_id,
                "section_index": section_index,
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            return None
    
    def _pick_contributing_sections_from_feedbacks(self, super_metrics: List[SuperMetric]) -> List[SuperMetricFeedbackContributorSectionGroup]:
        """
        Pick contributing sections from the already generated section feedbacks.
        Uses the same logic as DefaultSuperMetricFeedbackService but works with section_feedbacks.
        
        Args:
            super_metrics: List of super-metrics with section feedbacks
            
        Returns:
            List[SuperMetricFeedbackContributorSectionGroup]: Contributing section groups for each super-metric
        """
        self.logger.debug("Picking contributing sections from generated feedbacks", {
            "super_metrics_count": len(super_metrics),
            "service": "SectionBasedSuperMetricFeedbackService"
        })
        
        # Sort super-metrics by weight in descending order (higher weight = higher priority)
        sorted_super_metrics = sorted(super_metrics, key=lambda sm: sm.metadata.weight, reverse=True)
        
        # Track which sections have already been assigned
        assigned_sections: Set[str] = set()
        
        contributing_groups: List[SuperMetricFeedbackContributorSectionGroup] = []
        
        for super_metric in sorted_super_metrics:
            # Find available sections (not yet assigned to other super-metrics)
            available_sections = [
                section_score for section_score in super_metric.section_scores
                if section_score.section_id not in assigned_sections
            ]
            
            contributing_group = None
            
            if available_sections:
                # Sort by numeric score
                available_sections_sorted = sorted(available_sections, key=lambda s: s.score.numeric_score, reverse=True)
                
                # Find highest scored sections
                highest_score = available_sections_sorted[0].score.numeric_score
                highest_sections = [
                    section for section in available_sections_sorted 
                    if section.score.numeric_score == highest_score
                ]
                
                # Find lowest scored sections
                lowest_score = available_sections_sorted[-1].score.numeric_score
                lowest_sections = [
                    section for section in available_sections_sorted 
                    if section.score.numeric_score == lowest_score
                ]
                
                # Randomly choose between highest and lowest scored sections, then randomly pick one section
                candidate_sections = []
                is_positive = None
                
                if highest_sections and lowest_sections:
                    # Randomly choose between positive (high score) and negative (low score) examples
                    if random.choice([True, False]):
                        candidate_sections = highest_sections
                        is_positive = True
                    else:
                        candidate_sections = lowest_sections
                        is_positive = False
                elif highest_sections:
                    # Only high scoring sections available
                    candidate_sections = highest_sections
                    is_positive = True
                elif lowest_sections:
                    # Only low scoring sections available
                    candidate_sections = lowest_sections
                    is_positive = False
                
                if candidate_sections and is_positive is not None:
                    # Randomly pick one section from candidates
                    chosen_section = random.choice(candidate_sections)
                    
                    contributing_group = SuperMetricFeedbackContributorSectionGroup(
                        super_metric_type=super_metric.metadata.super_metric_type,
                        section_id=chosen_section.section_id,
                        section_index=chosen_section.section_index,
                        is_positive=is_positive
                    )
                    
                    # Mark this section as assigned
                    assigned_sections.add(chosen_section.section_id)
            
            if contributing_group:
                contributing_groups.append(contributing_group)
            else:
                self.logger.warning("No available sections found for super-metric", context={
                    "super_metric_type": super_metric.metadata.super_metric_type.value,
                    "service": "SectionBasedSuperMetricFeedbackService"
                })
        
        return contributing_groups
    
    def _generate_overall_feedback(
        self, 
        contributing_section_groups: List[SuperMetricFeedbackContributorSectionGroup],
        super_metrics: List[SuperMetric]
    ) -> Dict[SuperMetricType, SuperMetricFeedback]:
        """
        Generate overall feedback for each super-metric by picking feedback from contributing sections.
        Since we've already generated feedback for each section, we just pick the feedback 
        from the contributing section for each super-metric.
        
        Args:
            contributing_section_groups: Contributing section groups for each super-metric
            super_metrics: List of super-metrics with section feedbacks
            
        Returns:
            Dict[SuperMetricType, SuperMetricFeedback]: Mapping from super-metric type to feedback object
        """
        self.logger.debug("Generating overall feedback from contributing sections", {
            "super_metrics_count": len(super_metrics),
            "contributing_sections_count": len(contributing_section_groups),
            "service": "SectionBasedSuperMetricFeedbackService"
        })

        feedback_map: Dict[SuperMetricType, SuperMetricFeedback] = {}
        
        try:
            for contributing_group in contributing_section_groups:
                # Find the super-metric this group belongs to
                super_metric = next(
                    (sm for sm in super_metrics if sm.metadata.super_metric_type == contributing_group.super_metric_type),
                    None
                )
                
                if super_metric:
                    # Find the section feedback for the contributing section
                    section_feedback = next(
                        (sf for sf in super_metric.section_feedbacks 
                         if sf.section_id == contributing_group.section_id),
                        None
                    )
                    
                    if section_feedback:
                        # Create overall feedback from the section feedback
                        overall_feedback = SuperMetricFeedback(
                            brief_feedback=section_feedback.brief_feedback,
                            revised_response=section_feedback.revised_response,
                            feedback=section_feedback.feedback,
                            section_index=section_feedback.section_index
                        )
                        feedback_map[contributing_group.super_metric_type] = overall_feedback
                        
                        self.logger.debug("Created overall feedback from section feedback", {
                            "super_metric_type": contributing_group.super_metric_type.value,
                            "section_id": contributing_group.section_id,
                            "section_index": contributing_group.section_index,
                            "service": "SectionBasedSuperMetricFeedbackService"
                        })
                    else:
                        self.logger.warning("Section feedback not found for contributing section", context={
                            "super_metric_type": contributing_group.super_metric_type.value,
                            "section_id": contributing_group.section_id,
                            "service": "SectionBasedSuperMetricFeedbackService"
                        })
                else:
                    self.logger.warning("Super-metric not found for contributing group", context={
                        "super_metric_type": contributing_group.super_metric_type.value,
                        "service": "SectionBasedSuperMetricFeedbackService"
                    })
            
            # Create placeholder feedback for missing super-metrics
            for super_metric in super_metrics:
                if super_metric.metadata.super_metric_type not in feedback_map:
                    feedback_map[super_metric.metadata.super_metric_type] = self._create_placeholder_feedback(super_metric)
                    self.logger.debug("Created placeholder feedback for super-metric", {
                        "super_metric_type": super_metric.metadata.super_metric_type.value,
                        "service": "SectionBasedSuperMetricFeedbackService"
                    })
            
            return feedback_map
            
        except Exception as e:
            self.logger.error("Failed to generate overall feedback from sections", e, {
                "service": "SectionBasedSuperMetricFeedbackService"
            })
            
            # Return placeholder feedback for all super-metrics
            feedback_map = {}
            for super_metric in super_metrics:
                feedback_map[super_metric.metadata.super_metric_type] = self._create_placeholder_feedback(super_metric)
            return feedback_map
    

    
    def _create_placeholder_feedback(self, super_metric: SuperMetric) -> SuperMetricFeedback:
        """
        Create placeholder feedback for a super-metric when LLM generation fails.
        
        Args:
            super_metric: The super-metric to create feedback for
            
        Returns:
            SuperMetricFeedback with placeholder content
        """
        
        return SuperMetricFeedback(
            brief_feedback="",
            revised_response="",
            feedback="",
            section_index=0,  # Default section index
        )
    
    def _update_super_metrics_with_overall_feedback(
        self, 
        super_metrics: List[SuperMetric], 
        feedback_map: Dict[SuperMetricType, SuperMetricFeedback]
    ) -> List[SuperMetric]:
        """
        Update SuperMetric entities with the generated overall feedback by matching super-metric types.
        
        Args:
            super_metrics: List of super-metrics to update
            feedback_map: Mapping from super-metric type to feedback object
            
        Returns:
            List[SuperMetric]: Updated super-metrics with overall feedback
        """
        self.logger.debug("Updating super-metrics with overall feedback", {
            "super_metrics_count": len(super_metrics),
            "feedback_map_count": len(feedback_map),
            "service": "SectionBasedSuperMetricFeedbackService"
        })
        
        updated_super_metrics: List[SuperMetric] = []
        
        for super_metric in super_metrics:
            feedback = feedback_map.get(super_metric.metadata.super_metric_type)
            if feedback:
                # Update the super-metric with the overall feedback
                updated_super_metric = super_metric.model_copy(
                    update={"feedback": feedback}
                )
                updated_super_metrics.append(updated_super_metric)
            else:
                # Keep original if no feedback found
                updated_super_metrics.append(super_metric)
        
        return updated_super_metrics