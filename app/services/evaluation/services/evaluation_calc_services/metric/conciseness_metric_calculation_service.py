"""
Conciseness Metric Calculation Service.

This service implements the conciseness metric calculation based on three criteria:
1. Core Idea Presented
2. Filter Words Frequency  
3. Strong Words Frequency

The service uses LLM APIs to analyze dialog sections and generate sub-metrics,
calculate scores, and provide revision suggestions.
"""
import json
import re
from typing import List, Dict, Any, Optional
from enum import Enum
from pathlib import Path

try:
    # Keep a direct import for dependency/availability checks.
    import litellm  # type: ignore
    from app.services.evaluation.utils.litellm_client import acompletion
except Exception:  # pragma: no cover
    litellm = None  # type: ignore
from pydantic import BaseModel

from app.services.evaluation.business import (
    MetricCalculationService,
    DialogSection, 
    Metric,
    MetricGroup,
    Score, 
    ScoreLabel,
    MetricMetadata,
    ScoreTransformationService,
    Logger,
    IdGenerator
)

class FrequencyCategory(Enum):
    LOW = "low"
    HIGH = "high"

class ConcisenessSubMetrics(BaseModel):
    """
    Internal data structure for conciseness sub-metrics.
    Field names are aligned with LLM prompts to avoid conversion.
    This is only used within the service implementation.
    """
    # Fields that come directly from LLM response
    is_core_idea_presented: bool  # Aligned with prompt field name
    core_idea: Optional[str] = ""
    filter_words: List[str] = []
    strong_words: List[str] = []
    
    # Computed fields
    sentence_count: int
    filter_words_count: int
    strong_words_count: int
    filter_words_frequency: float
    strong_words_frequency: float
    filter_words_frequency_category: Optional[FrequencyCategory] = None
    strong_words_frequency_category: Optional[FrequencyCategory] = None

    model_config = {"frozen": True}


class ConcisenessMetricCalculationService(MetricCalculationService):
    """
    Conciseness metric calculation service implementation.
    
    Evaluates candidate responses based on:
    - Core idea presentation
    - Filter words frequency
    - Strong words frequency
    """
    
    def __init__(
        self, 
        logger: Logger, 
        id_generator: IdGenerator,
        score_transformation_service: ScoreTransformationService,
        model: str = "gpt-4o", 
        enable_revision: bool = False,
        eval_system_prompt_path: Optional[str] = None,
        eval_user_prompt_path: Optional[str] = None,
        revise_system_prompt_path: Optional[str] = None,
        revise_user_prompt_path: Optional[str] = None
    ):
        """
        Initialize the service.
        
        Args:
            logger: Logger instance for logging operations
            id_generator: ID generator for creating unique metric IDs
            score_transformation_service: Service for transforming between score labels and numeric scores
            model: LLM model to use for evaluation (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            enable_revision: Whether to generate revision suggestions (default: False)
            eval_system_prompt_path: Full path to custom evaluation system prompt file (optional)
            eval_user_prompt_path: Full path to custom evaluation user prompt file (optional)
            revise_system_prompt_path: Full path to custom revision system prompt file (optional)
            revise_user_prompt_path: Full path to custom revision user prompt file (optional)
        """
        self.logger = logger
        self.id_generator = id_generator
        self.score_transformation_service = score_transformation_service
        self.model = model
        self.temperature = 0.3
        self.enable_revision = enable_revision
        
        # Store custom prompt paths (full paths)
        self.custom_eval_system_prompt_path = eval_system_prompt_path
        self.custom_eval_user_prompt_path = eval_user_prompt_path
        self.custom_revise_system_prompt_path = revise_system_prompt_path
        self.custom_revise_user_prompt_path = revise_user_prompt_path
        
        # LiteLLM will automatically read API keys from environment variables
        
        # Load prompts
        self._load_prompts()

        if litellm is None:
            raise RuntimeError(
                "LiteLLM dependency is not installed. Install via 'pip install litellm'"
            )
    
    async def create_metric_group(
        self, 
        dialog_sections: List[DialogSection], 
        metadata: MetricMetadata
    ) -> MetricGroup:
        """
        Create a complete MetricGroup entity for conciseness evaluation.
        
        Args:
            dialog_sections: The dialog sections to analyze
            metadata: The metric metadata 
            
        Returns:
            MetricGroup: Complete metric group with metrics for each section
        """
        try:
            self.logger.info("Creating conciseness metric group", {
                "dialog_sections_count": len(dialog_sections),
                "service": "ConcisenessMetricCalculationService"
            })
            
            # Process all dialog sections in a single LLM API call
            all_section_results = await self._generate_sub_metrics_for_all_sections(dialog_sections)
            
            # Calculate scores for all sections and prepare revision data
            sections_needing_revision = []
            section_scores = []
            section_sub_metrics = []
            
            for i, dialog_section in enumerate(dialog_sections):
                sub_metrics = all_section_results[i]
                score = self._calculate_score(sub_metrics)
                
                section_scores.append(score)
                section_sub_metrics.append(sub_metrics)
                
                # Collect sections that need revision (Poor and Fair scores)
                if score.score_label != ScoreLabel.GOOD:
                    sections_needing_revision.append((i, dialog_section, sub_metrics, score))
            
            # Generate revisions for all sections needing them in a single API call (if enabled)
            all_revisions = []
            if self.enable_revision and sections_needing_revision:
                all_revisions = await self._generate_revisions_for_all_sections(sections_needing_revision)
            
            # Create metrics from the batch results
            metrics = []
            revision_index = 0
            
            for i, dialog_section in enumerate(dialog_sections):
                # Generate unique metric ID for each section
                metric_id = self.id_generator.generate()
                
                self.logger.info("Processing dialog section result for conciseness", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "service": "ConcisenessMetricCalculationService"
                })
                
                # Get data for this specific section from batch results
                sub_metrics = section_sub_metrics[i]
                score = section_scores[i]
                
                # Get revision (either from batch results or empty string)
                if not self.enable_revision or score.score_label == ScoreLabel.GOOD:
                    revision = ""
                else:
                    revision = all_revisions[revision_index] if revision_index < len(all_revisions) else ""
                    revision_index += 1
                
                # Convert internal sub-metrics to dictionary
                sub_metrics_dict = self._convert_sub_metrics_to_dict(sub_metrics)
                
                # Create metric entity for this section
                metric = Metric(
                    id=metric_id,
                    metadata=metadata,
                    dialog_section_id=dialog_section.id,
                    dialog_section_index=dialog_section.section_index,
                    sub_metrics=sub_metrics_dict,
                    score=score,
                    revision=revision
                )
                
                metrics.append(metric)
                
                self.logger.info("Successfully created conciseness metric for section", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "score_label": score.score_label.value,
                    "numeric_score": score.numeric_score,
                    "has_revision": bool(revision),
                    "service": "ConcisenessMetricCalculationService"
                })
            
            # Create metric group
            metric_group = MetricGroup(
                metric_type=metadata.metric_type,
                metrics=metrics
            )
            
            self.logger.info("Successfully created conciseness metric group", {
                "dialog_sections_count": len(dialog_sections),
                "metrics_count": len(metrics),
                "service": "ConcisenessMetricCalculationService"
            })
            
            return metric_group
            
        except Exception as e:
            self.logger.error("Failed to create conciseness metric group", e, {
                "dialog_sections_count": len(dialog_sections),
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    def _load_prompts(self) -> None:
        """Load prompt templates from files."""
        try:
            # Default prompt directory
            default_prompt_dir = (
                Path(__file__).resolve().parent.parent.parent.parent.parent.parent
                / "config"
                / "prompts"
                / "evaluation"
                / "v1"
            )
            
            # Load evaluation prompts with custom paths if provided, otherwise use defaults
            if self.custom_eval_system_prompt_path:
                eval_system_path = Path(self.custom_eval_system_prompt_path)
            else:
                eval_system_path = default_prompt_dir / "prompt_conciseness_eval_system_msg.md"
                
            if self.custom_eval_user_prompt_path:
                eval_user_path = Path(self.custom_eval_user_prompt_path)
            else:
                eval_user_path = default_prompt_dir / "prompt_eval_user_msg.md"
                
            if self.custom_revise_system_prompt_path:
                revise_system_path = Path(self.custom_revise_system_prompt_path)
            else:
                revise_system_path = default_prompt_dir / "prompt_conciseness_revise_system_msg.md"
                
            if self.custom_revise_user_prompt_path:
                revise_user_path = Path(self.custom_revise_user_prompt_path)
            else:
                revise_user_path = default_prompt_dir / "prompt_revise_user_msg.md"
            
            with open(eval_system_path, 'r', encoding='utf-8') as f:
                self.eval_system_prompt = f.read()
            
            with open(eval_user_path, 'r', encoding='utf-8') as f:
                self.eval_user_prompt = f.read()
            
            # Load revision prompts  
            with open(revise_system_path, 'r', encoding='utf-8') as f:
                self.revise_system_prompt = f.read()
            
            with open(revise_user_path, 'r', encoding='utf-8') as f:
                self.revise_user_prompt = f.read()
                
            self.logger.info("Conciseness prompts loaded successfully", {
                "service": "ConcisenessMetricCalculationService",
                "custom_prompts": {
                    "eval_system": str(eval_system_path),
                    "eval_user": str(eval_user_path),
                    "revise_system": str(revise_system_path),
                    "revise_user": str(revise_user_path)
                }
            })
        except FileNotFoundError as e:
            # Fail with a clearer message; this should be a deploy-time asset.
            self.logger.error("Conciseness prompt file not found", e, {
                "service": "ConcisenessMetricCalculationService",
                "default_prompt_dir": str(default_prompt_dir),
            })
            raise
        except Exception as e:
            self.logger.error("Failed to load conciseness prompts", e, {
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    async def _generate_sub_metrics_for_all_sections(self, dialog_sections: List[DialogSection]) -> List[ConcisenessSubMetrics]:
        """
        Generate sub-metrics for all dialog sections in a single LLM API call.
        
        Args:
            dialog_sections: List of dialog sections to analyze
            
        Returns:
            List[ConcisenessSubMetrics]: List containing evaluation results for each section
        """
        try:
            self.logger.info("Generating conciseness sub-metrics for all sections", {
                "dialog_sections_count": len(dialog_sections),
                "service": "ConcisenessMetricCalculationService"
            })
            
            # Format all dialog sections for LLM
            all_sections_json = []
            for dialog_section in dialog_sections:
                messages_json = []
                for msg in dialog_section.messages:
                    messages_json.append({
                        "role": msg.role.value.lower(),
                        "start_time": msg.start_time.timestamp(),
                        "end_time": msg.end_time.timestamp(),
                        "speakerId": 0 if msg.role.value == "CANDIDATE" else None,
                        "content": msg.content
                    })
                
                section_json = {
                    "section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "messages": messages_json
                }
                all_sections_json.append(section_json)
            
            # Prepare user prompt for all sections
            user_content = self.eval_user_prompt.format(
                dialog_sections=json.dumps(all_sections_json, ensure_ascii=False, indent=2)
            )
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.eval_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Process results for each section
            section_results = []
            
            # Handle different response formats from LLM
            if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                # Expected case: LLM returned {"results": [array]} 
                result_list = result["results"]
                if len(result_list) != len(dialog_sections):
                    error_msg = f"Expected {len(dialog_sections)} section results, got {len(result_list)} results in wrapped array"
                    raise ValueError(error_msg)
                self.logger.info("LLM returned expected dictionary format with results array", {
                    "dialog_sections_count": len(dialog_sections),
                    "results_count": len(result_list),
                    "service": "ConcisenessMetricCalculationService"
                })
            elif isinstance(result, list) and len(result) == len(dialog_sections):
                # Legacy fallback case: LLM returned raw array
                self.logger.warning("LLM returned legacy array format instead of dictionary", None, {
                    "dialog_sections_count": len(dialog_sections),
                    "service": "ConcisenessMetricCalculationService"
                })
                result_list = result
            elif isinstance(result, dict) and len(dialog_sections) == 1:
                # Fallback case: LLM returned single object for single section
                self.logger.warning("LLM returned single object instead of dictionary format for single section", None, {
                    "dialog_sections_count": len(dialog_sections),
                    "service": "ConcisenessMetricCalculationService"
                })
                result_list = [result]
            else:
                # Error case: unexpected response format
                if isinstance(result, list):
                    error_msg = f"Expected {len(dialog_sections)} section results, got {len(result)} array elements in wrong format"
                elif isinstance(result, dict) and "results" in result:
                    error_msg = f"Expected {len(dialog_sections)} section results, got wrapped results with wrong format"
                else:
                    error_msg = f"Expected {len(dialog_sections)} section results, got unexpected format: {type(result).__name__}"
                raise ValueError(error_msg)
                
            # Process each result
            for i, section_result in enumerate(result_list):
                dialog_section = dialog_sections[i]
                
                # Calculate additional computed fields for this section
                candidate_content = ""
                for msg in dialog_section.messages:
                    if msg.role.value == "CANDIDATE":
                        candidate_content += msg.content + " "
                
                sentence_count = self._count_sentences(candidate_content)
                filter_words = section_result.get("filter_words", [])
                strong_words = section_result.get("strong_words", [])
                
                # Validate section_index matches expected (if present)
                expected_section_index = dialog_section.section_index
                actual_section_index = section_result.get("section_index")
                if actual_section_index is not None and actual_section_index != expected_section_index:
                    self.logger.warning("Section index mismatch in evaluation result", None, {
                        "expected_index": expected_section_index,
                        "actual_index": actual_section_index,
                        "dialog_section_id": dialog_section.id,
                        "service": "ConcisenessMetricCalculationService"
                    })
                
                # priority: llm_result > computed
                filter_words_count = section_result.get("filter_words_count", len(filter_words))

                # priority: llm_result > computed
                strong_words_count = section_result.get("strong_words_count", len(strong_words))
                
                # Add computed fields to result
                section_result.update({
                    "sentence_count": sentence_count,
                    "filter_words_count": filter_words_count,
                    "strong_words_count": strong_words_count,
                    "filter_words_frequency": len(filter_words) / sentence_count if sentence_count > 0 else 0,
                    "strong_words_frequency": len(strong_words) / sentence_count if sentence_count > 0 else 0
                })
                
                # Use Pydantic's model_validate to parse LLM response
                sub_metrics = ConcisenessSubMetrics.model_validate(section_result)
                section_results.append(sub_metrics)
            
            self.logger.info("Successfully generated conciseness sub-metrics for all sections", {
                "dialog_sections_count": len(dialog_sections),
                "service": "ConcisenessMetricCalculationService"
            })
            
            return section_results
            
        except Exception as e:
            self.logger.error("Failed to generate conciseness sub-metrics for all sections", e, {
                "dialog_sections_count": len(dialog_sections),
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    async def _generate_revisions_for_all_sections(self, sections_needing_revision: List[tuple]) -> List[str]:
        """
        Generate revisions for all sections needing them in a single LLM API call.
        
        Args:
            sections_needing_revision: List of tuples (index, dialog_section, sub_metrics, score)
            
        Returns:
            List[str]: List of revision texts in the same order as input
        """
        if not sections_needing_revision:
            return []
            
        try:
            self.logger.info("Generating conciseness revisions for all sections", {
                "sections_count": len(sections_needing_revision),
                "service": "ConcisenessMetricCalculationService"
            })
            
            # Format all sections needing revision for LLM
            all_revision_data = []
            for _, dialog_section, sub_metrics, score in sections_needing_revision:
                # Format dialog section
                section_messages = []
                for msg in dialog_section.messages:
                    section_messages.append({
                        "role": msg.role.value.lower(),
                        "content": msg.content
                    })
                
                section_data = {
                    "section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "messages": section_messages
                }
                
                # Prepare evaluation data
                evaluation_data = self._prepare_evaluation_data(sub_metrics, score)
                
                revision_item = {
                    "dialog_section": section_data,
                    "evaluation": evaluation_data
                }
                all_revision_data.append(revision_item)
            
            # Prepare revision prompt for all sections
            user_content = self.revise_user_prompt.format(
                revision_data=json.dumps(all_revision_data, ensure_ascii=False, indent=2)
            )
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.revise_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Process revision results
            # Handle different response formats from LLM
            if isinstance(result, dict) and "results" in result and isinstance(result["results"], list):
                # Expected case: LLM returned {"results": [array]}
                revision_list = result["results"]
                if len(revision_list) != len(sections_needing_revision):
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got {len(revision_list)} results in wrapped array"
                    raise ValueError(error_msg)
                self.logger.info("LLM returned expected dictionary format for revisions", {
                    "sections_count": len(sections_needing_revision),
                    "results_count": len(revision_list),
                    "service": "ConcisenessMetricCalculationService"
                })
            elif isinstance(result, list) and len(result) == len(sections_needing_revision):
                # Legacy fallback case: LLM returned raw array
                self.logger.warning("LLM returned legacy array format for revisions", None, {
                    "sections_count": len(sections_needing_revision),
                    "service": "ConcisenessMetricCalculationService"
                })
                revision_list = result
            else:
                # Error case: unexpected response format
                if isinstance(result, list):
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got {len(result)} array elements"
                elif isinstance(result, dict) and "results" in result:
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got wrapped results with wrong format"
                else:
                    error_msg = f"Expected {len(sections_needing_revision)} revision results, got unexpected format: {type(result).__name__}"
                raise ValueError(error_msg)
                
            # Process each revision result
            revisions = []
            for i, revision_result in enumerate(revision_list):
                if isinstance(revision_result, dict):
                    # Validate section_index if present
                    if "section_index" in revision_result:
                        expected_section_index = sections_needing_revision[i][1].section_index
                        actual_section_index = revision_result["section_index"]
                        if actual_section_index != expected_section_index:
                            self.logger.warning("Section index mismatch in revision result", None, {
                                "expected_index": expected_section_index,
                                "actual_index": actual_section_index,
                                "revision_item_index": i,
                                "service": "ConcisenessMetricCalculationService"
                            })
                    
                    if "revised_speech" in revision_result:
                        revised_speech = revision_result["revised_speech"]
                        revisions.append(revised_speech if revised_speech is not None else "")
                    else:
                        revisions.append("")
                else:
                    revisions.append("")
            
            self.logger.info("Successfully generated conciseness revisions for all sections", {
                "sections_count": len(sections_needing_revision),
                "revisions_generated": len([r for r in revisions if r]),
                "service": "ConcisenessMetricCalculationService"
            })
            
            return revisions
                
        except Exception as e:
            self.logger.error("Failed to generate conciseness revisions for all sections", e, {
                "sections_count": len(sections_needing_revision),
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    async def _generate_sub_metrics(self, dialog_section: DialogSection) -> ConcisenessSubMetrics:
        """
        Generate sub-metrics for conciseness evaluation using LLM API.
        
        Args:
            dialog_section: The dialog section to analyze
            
        Returns:
            ConcisenessSubMetrics containing evaluation results
        """
        try:
            self.logger.info("Generating conciseness sub-metrics", {
                "dialog_section_id": dialog_section.id,
                "service": "ConcisenessMetricCalculationService"
            })
            
            # Format dialog section for LLM
            messages_json = []
            for msg in dialog_section.messages:
                messages_json.append({
                    "role": msg.role.value.lower(),
                    "start_time": msg.start_time.timestamp(),
                    "end_time": msg.end_time.timestamp(),
                    "speakerId": 0 if msg.role.value == "CANDIDATE" else None,
                    "content": msg.content
                })
            
            dialog_section_json = {
                "section_id": dialog_section.id,
                "section_index": dialog_section.section_index,
                "messages": messages_json
            }
            
            # Prepare user prompt
            user_content = self.eval_user_prompt.format(dialog_section=json.dumps(dialog_section_json, ensure_ascii=False, indent=2))
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.eval_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            # Calculate additional computed fields
            candidate_content = ""
            for msg in dialog_section.messages:
                if msg.role.value == "CANDIDATE":
                    candidate_content += msg.content + " "
            
            sentence_count = self._count_sentences(candidate_content)
            filter_words = result.get("filter_words", [])
            strong_words = result.get("strong_words", [])
            
            # Add computed fields to result
            result.update({
                "sentence_count": sentence_count,
                "filter_words_count": len(filter_words),
                "strong_words_count": len(strong_words),
                "filter_words_frequency": len(filter_words) / sentence_count if sentence_count > 0 else 0,
                "strong_words_frequency": len(strong_words) / sentence_count if sentence_count > 0 else 0
            })
            
            # Use Pydantic's model_validate to parse LLM response directly
            sub_metrics = ConcisenessSubMetrics.model_validate(result)
            
            self.logger.info("Successfully generated conciseness sub-metrics", {
                "dialog_section_id": dialog_section.id,
                "service": "ConcisenessMetricCalculationService",
                **result  # Merge the result dictionary
            })
            
            return sub_metrics
            
        except Exception as e:
            self.logger.error("Failed to generate conciseness sub-metrics", e, {
                "dialog_section_id": dialog_section.id,
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    def _calculate_score(self, sub_metrics: ConcisenessSubMetrics) -> Score:
        """
        Calculate conciseness score based on sub-metrics.
        
        Scoring logic:
        - Poor: Core idea not presented (regardless of other metrics)
        - Good: All three metrics pass 
        - Fair: Core idea presented but other metrics fail
        
        Args:
            sub_metrics: ConcisenessSubMetrics from _generate_sub_metrics
            
        Returns:
            Score object with label and numeric value
        """
        try:
            self.logger.info("Calculating conciseness score", {
                "core_idea_presented": sub_metrics.is_core_idea_presented,
                "service": "ConcisenessMetricCalculationService"
            })
            
            # Apply scoring rubric
            if not sub_metrics.is_core_idea_presented:
                score_label = ScoreLabel.POOR
            else:
                # Check other criteria
                filter_words_pass = sub_metrics.strong_words_frequency_category == FrequencyCategory.LOW if sub_metrics.strong_words_frequency_category is not None else sub_metrics.filter_words_frequency <= 0.5
                strong_words_pass = sub_metrics.strong_words_frequency_category == FrequencyCategory.HIGH if sub_metrics.strong_words_frequency_category is not None else sub_metrics.strong_words_frequency >= 0.5
                
                if filter_words_pass and strong_words_pass:
                    score_label = ScoreLabel.GOOD
                else:
                    score_label = ScoreLabel.FAIR
            
            # Use transformation service to create consistent score
            score = self.score_transformation_service.create_score(score_label)
            
            self.logger.info("Successfully calculated conciseness score", {
                "score_label": score.score_label.value,
                "numeric_score": score.numeric_score,
                "core_idea_presented": sub_metrics.is_core_idea_presented,
                "filter_words_frequency": sub_metrics.filter_words_frequency,
                "strong_words_frequency": sub_metrics.strong_words_frequency,
                "service": "ConcisenessMetricCalculationService"
            })
            
            return score
            
        except Exception as e:
            self.logger.error("Failed to calculate conciseness score", e, {
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    async def _generate_revision(self, sub_metrics: ConcisenessSubMetrics, score: Score, dialog_section: DialogSection) -> str:
        """
        Generate revision text for conciseness improvement using LLM API.
        
        Args:
            sub_metrics: List of sub-metrics 
            score: Calculated score
            dialog_section: Original dialog section
            
        Returns:
            Revision text or empty string for Good scores or when revision is disabled
        """
        try:
            self.logger.info("Generating conciseness revision", {
                "dialog_section_id": dialog_section.id,
                "score_label": score.score_label.value,
                "enable_revision": self.enable_revision,
                "service": "ConcisenessMetricCalculationService"
            })
            
            # No revision if disabled or for Good scores
            if not self.enable_revision or score.score_label == ScoreLabel.GOOD:
                self.logger.info("No revision needed - disabled or Good score", {
                    "dialog_section_id": dialog_section.id,
                    "enable_revision": self.enable_revision,
                    "score_label": score.score_label.value,
                    "service": "ConcisenessMetricCalculationService"
                })
                return ""
            
            # Prepare evaluation data for revision prompt
            evaluation_data = self._prepare_evaluation_data(sub_metrics, score)
            
            # Format dialog section
            section_messages: List[Dict[str, str]] = []
            for msg in dialog_section.messages:
                section_messages.append({
                    "role": msg.role.value.lower(),
                    "content": msg.content
                })
            
            section_data: Dict[str, Any] = {
                "section_id": dialog_section.id,
                "section_index": dialog_section.section_index,
                "messages": section_messages
            }
            
            # Prepare revision prompt
            user_content = self.revise_user_prompt.format(
                dialog_section=json.dumps(section_data, ensure_ascii=False, indent=2),
                evaluation=json.dumps(evaluation_data, ensure_ascii=False, indent=2)
            )
            
            # Call LLM using LiteLLM
            messages = [
                {"role": "system", "content": self.revise_system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            result = await self._call_llm_with_json_response(messages)
            
            revision = result.get("revised_speech", "") or ""
            
            self.logger.info("Successfully generated conciseness revision", {
                "dialog_section_id": dialog_section.id,
                "revision_length": len(revision),
                "service": "ConcisenessMetricCalculationService"
            })
            
            return revision
            
        except Exception as e:
            self.logger.error("Failed to generate conciseness revision", e, {
                "dialog_section_id": dialog_section.id,
                "service": "ConcisenessMetricCalculationService"
            })
            raise
    
    def _count_sentences(self, text: str) -> int:
        """Count sentences in text."""
        if not text:
            return 0
        # Simple sentence counting - can be improved
        sentences = re.split(r'[。！？]', text.strip())
        return len([s for s in sentences if s.strip()])
    
    def _prepare_evaluation_data(self, sub_metrics: ConcisenessSubMetrics, score: Score) -> Dict[str, Any]:
        """Prepare evaluation data for revision prompt."""
        # Use Pydantic's model_dump() to serialize sub-metrics
        data = sub_metrics.model_dump()
        
        # Add score information
        data["score_label"] = score.score_label.value
        
        return data
    
    def _convert_sub_metrics_to_dict(self, sub_metrics: ConcisenessSubMetrics) -> Dict[str, Any]:
        """Convert internal ConcisenessSubMetrics to dictionary format for Metric entity."""
        # Use Pydantic's model_dump() to serialize to dictionary - all fields are already included
        return sub_metrics.model_dump()
    
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
            self.logger.error("LiteLLM API call failed", e, {
                "model": self.model,
                "service": "ConcisenessMetricCalculationService"
            })
            raise