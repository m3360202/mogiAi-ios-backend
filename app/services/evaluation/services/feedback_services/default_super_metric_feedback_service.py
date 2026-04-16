"""
Default super-metric feedback service implementation.
"""
import json
from pathlib import Path
from typing import List, Dict, Set, Any
from pydantic import BaseModel

from app.services.evaluation.utils.litellm_client import acompletion

from app.services.evaluation.business import (
    SuperMetricFeedbackService,
    SuperMetric,
    SuperMetricFeedback,
    SuperMetricFeedbackContributorSectionGroup,
    SuperMetricType,
    ScoreLabel,
    DialogSectionRepo,
    Logger
)

import random


class FeedbackResult(BaseModel):
    """
    Pydantic model for individual feedback result from LLM response.
    """
    section_index: int
    super_metric_type: str
    brief_feedback: str
    revised_response: str
    feedback: str


class FeedbackResponse(BaseModel):
    """
    Pydantic model for LLM feedback generation response.
    """
    results: List[FeedbackResult]

class DefaultSuperMetricFeedbackService(SuperMetricFeedbackService):
    """
    Implementation of SuperMetricFeedbackService that handles complete feedback generation 
    and updating process for all super-metrics.
    """
    
    def __init__(self, logger: Logger, dialog_section_repo: DialogSectionRepo, model: str = "gpt-4o"):
        """
        Initialize the default super-metric feedback service.
        
        Args:
            logger: Logger service for logging operations
            dialog_section_repo: Repository for retrieving dialog sections
            model: LLM model to use for feedback generation (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
        """
        self.logger = logger
        self.dialog_section_repo = dialog_section_repo
        self.model = model
        self.temperature = 0.7
        
        # Load prompts
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Load system and user prompts from files."""
        try:
            # Get the directory containing prompt files
            prompt_dir = Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts" / "evaluation" / "v1"
            
            # Load system prompt
            system_prompt_path = prompt_dir / "prompt_feedback_system_msg.md"
            with open(system_prompt_path, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read()
            
            # Load user prompt template
            user_prompt_path = prompt_dir / "prompt_feedback_user_msg.md" 
            with open(user_prompt_path, 'r', encoding='utf-8') as f:
                self.user_prompt_template = f.read()
                
            self.logger.debug("Successfully loaded feedback prompts", {
                "system_prompt_length": len(self.system_prompt),
                "user_prompt_template_length": len(self.user_prompt_template),
                "service": "DefaultSuperMetricFeedbackService"
            })
            
        except Exception as e:
            self.logger.error("Failed to load feedback prompts", e, {
                "service": "DefaultSuperMetricFeedbackService"
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
                "service": "DefaultSuperMetricFeedbackService"
            })
            raise
    
    async def generate_and_update_feedback(self, super_metrics: List[SuperMetric]) -> List[SuperMetric]:
        """
        Generate and update feedback for all super-metrics.
        Complete feedback generation and updating process for super-metrics.
        
        Steps:
        1. Call _pick_contributing_sections to identify contributing sections
        2. Call _generate_feedback to generate feedback text based on contributing sections
        3. Call _update_super_metrics to update SuperMetric entities with generated feedback
        4. Return updated SuperMetric list
        
        Args:
            super_metrics: List of super-metrics to generate feedback for
            
        Returns:
            List[SuperMetric]: Updated super-metrics with generated feedback
        """
        try:
            self.logger.info("Starting feedback generation and update process", {
                "super_metrics_count": len(super_metrics),
                "service": "DefaultSuperMetricFeedbackService"
            })

            # Step 1: Pick contributing sections for each super-metric
            contributing_section_groups = self._pick_contributing_sections(super_metrics)
            
            # Step 2: Generate feedback for all super-metrics at once
            # Step 3: Generate feedback for all super-metrics with contributing sections
            feedback_map = await self._generate_feedback(contributing_section_groups, super_metrics)
            
            # Step 3: Update SuperMetric entities with generated feedback
            updated_super_metrics = self._update_super_metrics(super_metrics, feedback_map)
            
            self.logger.info("Successfully completed feedback generation and update process", {
                "super_metrics_count": len(updated_super_metrics),
                "service": "DefaultSuperMetricFeedbackService"
            })
            
            return updated_super_metrics
            
        except Exception as e:
            self.logger.error("Failed to generate and update feedback", e, {
                "super_metrics_count": len(super_metrics),
                "service": "DefaultSuperMetricFeedbackService"
            })
            raise
    
    def _pick_contributing_sections(self, super_metrics: List[SuperMetric]) -> List[SuperMetricFeedbackContributorSectionGroup]:
        """
        Identify a single dialog section that contributes positively or negatively to each super-metric feedback.
        Ensures one section is only picked by one super-metric based on priority order determined by
        weight in evaluation strategy. For each super-metric, randomly picks one section from either 
        the highest scored sections (treated as positive examples) or the lowest scored sections (treated as negative examples).
        
        Args:
            super_metrics: List of super-metrics to analyze
            
        Returns:
            List[SuperMetricFeedbackContributorSectionGroup]: Contributing section groups for each super-metric
        """
        self.logger.debug("Picking contributing sections for feedback", {
            "super_metrics_count": len(super_metrics),
            "service": "DefaultSuperMetricFeedbackService"
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
                    # Both highest and lowest sections available, randomly choose type
                    if random.choice([True, False]):
                        candidate_sections = highest_sections
                        is_positive = True  # Highest scored sections are considered positive examples
                    else:
                        candidate_sections = lowest_sections
                        is_positive = False  # Lowest scored sections are considered negative examples
                elif highest_sections:
                    # Only highest sections available
                    candidate_sections = highest_sections
                    is_positive = True  # Highest scored sections are considered positive examples
                elif lowest_sections:
                    # Only lowest sections available
                    candidate_sections = lowest_sections
                    is_positive = False  # Lowest scored sections are considered negative examples
                
                # Pick one section randomly from candidates
                if candidate_sections and is_positive is not None:
                    chosen_section = random.choice(candidate_sections)
                    assigned_sections.add(chosen_section.section_id)
                    
                    contributing_group = SuperMetricFeedbackContributorSectionGroup(
                        super_metric_type=super_metric.metadata.super_metric_type,
                        section_id=chosen_section.section_id,
                        section_index=chosen_section.section_index,
                        is_positive=is_positive
                    )
            
            # Only add non-None groups
            if contributing_group is not None:
                contributing_groups.append(contributing_group)
            
            self.logger.debug("Picked contributing section for super-metric", {
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "section_picked": contributing_group.section_id if contributing_group else None,
                "is_positive": contributing_group.is_positive if contributing_group else None,
                "service": "DefaultSuperMetricFeedbackService"
            })
        
        return contributing_groups
    
    async def _generate_feedback(
        self, 
        contributing_section_groups: List[SuperMetricFeedbackContributorSectionGroup],
        super_metrics: List[SuperMetric]
    ) -> Dict[SuperMetricType, SuperMetricFeedback]:
        """
        Generate multiple feedback for each super-metric at once based on contributing 
        dialog sections using one LLM API call with a given prompt.
        
        Args:
            contributing_section_groups: Contributing section groups for each super-metric
            super_metrics: List of super-metrics for context
            
        Returns:
            Dict[SuperMetricType, SuperMetricFeedback]: Mapping from super-metric type to feedback object
        """
        self.logger.debug("Generating feedback for super-metrics", {
            "super_metrics_count": len(super_metrics),
            "contributing_sections_count": len(contributing_section_groups),
            "service": "DefaultSuperMetricFeedbackService"
        })

        try:
            # Step 1: Build dialog sections data in the format expected by the prompt
            dialog_sections_data = self._build_dialog_sections_data(contributing_section_groups)
            
            # Step 2: Build evaluation metrics data in the format expected by the prompt  
            evaluation_metrics_data = self._build_evaluation_metrics_data(contributing_section_groups, super_metrics)
            
            # Step 3: Make LLM API call
            user_content = self.user_prompt_template.format(
                messages=json.dumps(dialog_sections_data, ensure_ascii=False, indent=2),
                revision_data=json.dumps(evaluation_metrics_data, ensure_ascii=False, indent=2)
            )
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_content}
            ]
            
            response = await self._call_llm_with_json_response(messages)
            
            # Step 4: Parse response using Pydantic model
            feedback_response = FeedbackResponse(**response)
            
            # Step 5: Map results to super-metric types
            feedback_map: Dict[SuperMetricType, SuperMetricFeedback] = {}
            
            for result in feedback_response.results:
                # Parse the super_metric_type directly from the LLM response
                try:
                    super_metric_type = SuperMetricType(result.super_metric_type)
                    feedback_map[super_metric_type] = SuperMetricFeedback(
                        brief_feedback=result.brief_feedback,
                        revised_response=result.revised_response,
                        feedback=result.feedback,
                        section_index=result.section_index,
                    )
                except ValueError:
                    # If super_metric_type is invalid, skip this result
                    self.logger.warning("Invalid super_metric_type from LLM response", None, {
                        "super_metric_type": result.super_metric_type,
                        "section_index": result.section_index,
                        "service": "DefaultSuperMetricFeedbackService"
                    })
            
            # Step 6: Fill in any missing feedback with placeholder data
            for super_metric in super_metrics:
                if super_metric.metadata.super_metric_type not in feedback_map:
                    feedback_map[super_metric.metadata.super_metric_type] = self._create_placeholder_feedback(super_metric)
            
            self.logger.debug("Successfully generated feedback for all super-metrics", {
                "feedback_count": len(feedback_map),
                "service": "DefaultSuperMetricFeedbackService"
            })
            
            return feedback_map
            
        except Exception as e:
            self.logger.error("Failed to generate feedback using LLM", e, {
                "super_metrics_count": len(super_metrics),
                "service": "DefaultSuperMetricFeedbackService"
            })
            
            # Fallback: Create placeholder feedback for all super-metrics
            feedback_map = {}
            for super_metric in super_metrics:
                feedback_map[super_metric.metadata.super_metric_type] = self._create_placeholder_feedback(super_metric)
            
            return feedback_map
    
    def _build_dialog_sections_data(self, contributing_section_groups: List[SuperMetricFeedbackContributorSectionGroup]) -> List[Dict[str, Any]]:
        """
        Build dialog sections data in the format expected by the LLM prompt.
        
        Args:
            contributing_section_groups: Contributing section groups
            
        Returns:
            List of dialog section data formatted for the LLM prompt
        """
        # Get unique section IDs and retrieve dialog sections
        section_ids = list(set(cg.section_id for cg in contributing_section_groups))
        dialog_sections_data = []
        
        for section_id in section_ids:
            dialog_section = self.dialog_section_repo.get_by_id(section_id)
            if dialog_section:
                messages_data = []
                for message in dialog_section.messages:
                    messages_data.append({
                        "role": message.role.value.lower(),
                        "start_time": message.start_time.timestamp(),
                        "end_time": message.end_time.timestamp(),
                        "content": message.content
                    })
                
                dialog_sections_data.append({
                    "section_index": dialog_section.section_index,
                    "messages": messages_data
                })
        
        # Sort by section_index to maintain order
        dialog_sections_data.sort(key=lambda x: int(x["section_index"]))  # type: ignore
        return dialog_sections_data
    
    def _build_evaluation_metrics_data(
        self, 
        contributing_section_groups: List[SuperMetricFeedbackContributorSectionGroup],
        super_metrics: List[SuperMetric]
    ) -> List[Dict[str, Any]]:
        """
        Build evaluation metrics data in the format expected by the LLM prompt.
        
        Args:
            contributing_section_groups: Contributing section groups
            super_metrics: List of super-metrics
            
        Returns:
            List of evaluation metrics data formatted for the LLM prompt
        """
        evaluation_metrics_data = []
        
        for contributing_group in contributing_section_groups:
            # Find the corresponding super-metric
            super_metric = next(
                (sm for sm in super_metrics if sm.metadata.super_metric_type == contributing_group.super_metric_type),
                None
            )
            
            if super_metric:
                # Build metrics data from the super-metric's metric groups
                metrics_data = []
                for metric_group in super_metric.metric_groups:
                    for metric in metric_group.metrics:
                        metrics_data.append({
                            "metric": {
                                "metric_type": metric.metadata.metric_type.value,
                                "score_label": metric.score.score_label.value
                            },
                            "sub_metrics": metric.sub_metrics
                        })
                
                evaluation_metrics_data.append({
                    "super_metric_type": super_metric.metadata.super_metric_type.value,
                    "section_index": contributing_group.section_index,  # Use section_index directly from contributing_group
                    "metrics": metrics_data
                })
        
        return evaluation_metrics_data
    
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
            section_index=0,  # Placeholder index (first section)
        )
    
    def _update_super_metrics(
        self, 
        super_metrics: List[SuperMetric], 
        feedback_map: Dict[SuperMetricType, SuperMetricFeedback]
    ) -> List[SuperMetric]:
        """
        Update SuperMetric entities with the generated feedback by matching super-metric types.
        
        Args:
            super_metrics: List of super-metrics to update
            feedback_map: Mapping from super-metric type to feedback object
            
        Returns:
            List[SuperMetric]: Updated super-metrics with feedback
        """
        self.logger.debug("Updating super-metrics with feedback", {
            "super_metrics_count": len(super_metrics),
            "feedback_map_count": len(feedback_map),
            "service": "DefaultSuperMetricFeedbackService"
        })
        
        updated_super_metrics: List[SuperMetric] = []
        
        for super_metric in super_metrics:
            super_metric_type = super_metric.metadata.super_metric_type
            feedback = feedback_map.get(super_metric_type)
            
            # If no feedback is available, create placeholder
            if not feedback:
                feedback = self._create_placeholder_feedback(super_metric)
            
            # Create updated super-metric with feedback
            # Since SuperMetric is frozen, we need to create a new instance
            updated_super_metric = SuperMetric(
                metadata=super_metric.metadata,
                metric_groups=super_metric.metric_groups,
                score=super_metric.score,
                section_scores=super_metric.section_scores,
                feedback=feedback
            )
            
            updated_super_metrics.append(updated_super_metric)
            
            self.logger.debug("Updated super-metric with feedback", {
                "super_metric_type": super_metric_type.value,
                "brief_feedback_length": len(feedback.brief_feedback),
                "service": "DefaultSuperMetricFeedbackService"
            })
        
        return updated_super_metrics