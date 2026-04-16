"""
Brief lookup super-metric feedback service implementation.
"""
import json
import random
from pathlib import Path
from typing import List, Dict, Set, Any, Optional

from app.services.evaluation.business import (
    SuperMetricFeedbackService,
    SuperMetric,
    SuperMetricFeedback,
    SuperMetricFeedbackContributorSectionGroup,
    SuperMetricType,
    DialogSectionRepo,
    Logger
)


class BriefLookupSuperMetricFeedbackService(SuperMetricFeedbackService):
    """
    Implementation of SuperMetricFeedbackService that generates feedback by looking up 
    brief feedback from a JSON file instead of calling LLM APIs.
    """
    
    def __init__(self, logger: Logger, dialog_section_repo: DialogSectionRepo):
        """
        Initialize the brief lookup super-metric feedback service.
        
        Args:
            logger: Logger service for logging operations
            dialog_section_repo: Repository for retrieving dialog sections
        """
        self.logger = logger
        self.dialog_section_repo = dialog_section_repo
        self.brief_feedback_data: Dict[str, Any] = {}
        
        # Load brief feedback lookup data
        self._load_brief_feedback_lookup()
    
    def _load_brief_feedback_lookup(self) -> None:
        """Load brief feedback lookup data from JSON file."""
        try:
            # Get the directory containing the brief feedback lookup file
            config_dir = Path(__file__).parent.parent.parent.parent.parent / "config"
            lookup_file_path = config_dir / "brief_feedback_lookup.json"
            
            with open(lookup_file_path, 'r', encoding='utf-8') as f:
                self.brief_feedback_data = json.load(f)
            
            self.logger.debug("Successfully loaded brief feedback lookup data", {
                "lookup_entries": len(self.brief_feedback_data.get("brief_lookup", [])),
                "service": "BriefLookupSuperMetricFeedbackService"
            })
            
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            self.logger.error("Failed to load brief feedback lookup data", e, {
                "service": "BriefLookupSuperMetricFeedbackService"
            })
            # Initialize with empty data as fallback
            self.brief_feedback_data = {"brief_lookup": []}
    
    async def generate_and_update_feedback(self, super_metrics: List[SuperMetric]) -> List[SuperMetric]:
        """
        Generate and update feedback for all super-metrics by looking up brief feedback
        from the JSON file instead of calling LLM APIs.
        
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
            self.logger.info("Starting brief lookup feedback generation and update process", {
                "super_metrics_count": len(super_metrics),
                "service": "BriefLookupSuperMetricFeedbackService"
            })

            # Step 1: Pick contributing sections for each super-metric
            contributing_section_groups = self._pick_contributing_sections(super_metrics)
            
            # Step 2: Generate feedback for all super-metrics based on lookup
            feedback_map = self._generate_feedback(contributing_section_groups, super_metrics)
            
            # Step 3: Update SuperMetric entities with generated feedback
            updated_super_metrics = self._update_super_metrics(super_metrics, feedback_map)
            
            self.logger.info("Successfully completed brief lookup feedback generation and update process", {
                "super_metrics_count": len(updated_super_metrics),
                "service": "BriefLookupSuperMetricFeedbackService"
            })
            
            return updated_super_metrics
            
        except Exception as e:
            self.logger.error("Failed to generate and update feedback", e, {
                "super_metrics_count": len(super_metrics),
                "service": "BriefLookupSuperMetricFeedbackService"
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
            "service": "BriefLookupSuperMetricFeedbackService"
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
                "service": "BriefLookupSuperMetricFeedbackService"
            })
        
        return contributing_groups
    
    def _generate_feedback(
        self, 
        contributing_section_groups: List[SuperMetricFeedbackContributorSectionGroup],
        super_metrics: List[SuperMetric]
    ) -> Dict[SuperMetricType, SuperMetricFeedback]:
        """
        Generate feedback for each super-metric by looking up brief feedback from the JSON file
        instead of calling LLM APIs.
        
        Args:
            contributing_section_groups: Contributing section groups for each super-metric
            super_metrics: List of super-metrics for context
            
        Returns:
            Dict[SuperMetricType, SuperMetricFeedback]: Mapping from super-metric type to feedback object
        """
        self.logger.debug("Generating feedback using brief lookup", {
            "super_metrics_count": len(super_metrics),
            "contributing_sections_count": len(contributing_section_groups),
            "service": "BriefLookupSuperMetricFeedbackService"
        })

        feedback_map: Dict[SuperMetricType, SuperMetricFeedback] = {}
        
        try:
            # Create a mapping from super-metric type to contributing section for easy lookup
            contributing_map = {
                csg.super_metric_type: csg for csg in contributing_section_groups
            }
            
            for super_metric in super_metrics:
                super_metric_type = super_metric.metadata.super_metric_type
                contributing_section = contributing_map.get(super_metric_type)
                
                # Look up brief feedback from JSON data
                brief_feedback = self._lookup_brief_feedback(super_metric)
                
                # Create feedback with brief feedback only (empty strings for other fields)
                feedback = SuperMetricFeedback(
                    brief_feedback=brief_feedback,
                    revised_response="",  # Empty string as requested
                    feedback="",  # Empty string as requested
                    section_index=contributing_section.section_index if contributing_section else 0,
                )
                
                feedback_map[super_metric_type] = feedback
                
                self.logger.debug("Generated brief feedback for super-metric", {
                    "super_metric_type": super_metric_type.value,
                    "brief_feedback_length": len(brief_feedback),
                    "service": "BriefLookupSuperMetricFeedbackService"
                })
            
            return feedback_map
            
        except (KeyError, IndexError, AttributeError) as e:
            self.logger.error("Failed to generate feedback using brief lookup", e, {
                "super_metrics_count": len(super_metrics),
                "service": "BriefLookupSuperMetricFeedbackService"
            })
            
            # Fallback: Create empty feedback for all super-metrics
            for super_metric in super_metrics:
                feedback_map[super_metric.metadata.super_metric_type] = self._create_empty_feedback()
            
            return feedback_map
    
    def _lookup_brief_feedback(
        self, 
        super_metric: SuperMetric
    ) -> str:
        """
        Look up brief feedback from the JSON data based on super-metric scores.
        
        Args:
            super_metric: The super-metric to look up feedback for
            
        Returns:
            str: Brief feedback message
        """
        try:
            # Find the lookup entry for this super-metric type
            lookup_entry: Optional[Dict[str, Any]] = None
            brief_lookup_entries = self.brief_feedback_data.get("brief_lookup", [])
            
            for entry in brief_lookup_entries:
                if (isinstance(entry, dict) and 
                    str(entry.get("super_metric_type", "")) == super_metric.metadata.super_metric_type.value):  # type: ignore
                    lookup_entry = entry  # type: ignore
                    break
            
            if not lookup_entry:
                self.logger.warning("No lookup entry found for super-metric type", None, {
                    "super_metric_type": super_metric.metadata.super_metric_type.value,
                    "service": "BriefLookupSuperMetricFeedbackService"
                })
                return ""
            
            # Build the lookup key based on metric scores
            lookup_key = self._build_lookup_key(super_metric, lookup_entry)
            
            # Get brief feedbacks for the lookup key
            brief_feedbacks_dict = lookup_entry.get("brief_feedbacks", {})
            if isinstance(brief_feedbacks_dict, dict):
                brief_feedbacks_list = brief_feedbacks_dict.get(lookup_key, [])  # type: ignore
                
                if (isinstance(brief_feedbacks_list, list) and 
                    len(brief_feedbacks_list) > 0):  # type: ignore
                    # Randomly select one feedback from the list
                    selected_feedback = random.choice(brief_feedbacks_list)  # type: ignore
                    return str(selected_feedback) if selected_feedback else ""  # type: ignore
                else:
                    self.logger.warning("No brief feedback found for lookup key", None, {
                        "super_metric_type": super_metric.metadata.super_metric_type.value,
                        "lookup_key": lookup_key,
                        "service": "BriefLookupSuperMetricFeedbackService"
                    })
                    return ""
            else:
                self.logger.warning("Invalid brief_feedbacks structure", None, {
                    "super_metric_type": super_metric.metadata.super_metric_type.value,
                    "service": "BriefLookupSuperMetricFeedbackService"
                })
                return ""
                
        except (KeyError, IndexError, AttributeError, TypeError) as e:
            self.logger.error("Failed to lookup brief feedback", e, {
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "service": "BriefLookupSuperMetricFeedbackService"
            })
            return ""
    
    def _build_lookup_key(self, super_metric: SuperMetric, lookup_entry: Dict[str, Any]) -> str:
        """
        Build the lookup key based on the super-metric's metric scores and the lookup entry's metric order.
        
        Args:
            super_metric: The super-metric to build key for
            lookup_entry: The lookup entry containing metric order
            
        Returns:
            str: Lookup key in format like "GOOD-FAIR-POOR"
        """
        try:
            metric_type_order = lookup_entry.get("metric_type_order", [])
            
            if not metric_type_order:
                # If no metric order specified, use the super-metric's overall score
                return super_metric.score.score_label.value
            
            # Build key parts based on metric order
            key_parts: List[str] = []
            
            for metric_type_str in metric_type_order:
                # Find the metric group with this metric type
                score_label = None
                for metric_group in super_metric.metric_groups:
                    if metric_group.metric_type.value == metric_type_str:
                        # Get the first metric's score (assuming one metric per group for simplicity)
                        if metric_group.metrics:
                            score_label = metric_group.metrics[0].score.score_label.value
                        break
                
                if score_label:
                    key_parts.append(score_label)
                else:
                    # Fallback to overall super-metric score if metric not found
                    key_parts.append(super_metric.score.score_label.value)
            
            return "-".join(key_parts)
            
        except (KeyError, IndexError, AttributeError) as e:
            self.logger.error("Failed to build lookup key", e, {
                "super_metric_type": super_metric.metadata.super_metric_type.value,
                "service": "BriefLookupSuperMetricFeedbackService"
            })
            # Fallback to overall score
            return super_metric.score.score_label.value
    
    def _create_empty_feedback(self) -> SuperMetricFeedback:
        """
        Create empty feedback when lookup fails.
        
        Returns:
            SuperMetricFeedback with empty content
        """
        return SuperMetricFeedback(
            brief_feedback="",
            revised_response="",
            feedback="",
            section_index=0,
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
        self.logger.debug("Updating super-metrics with brief feedback", {
            "super_metrics_count": len(super_metrics),
            "feedback_map_count": len(feedback_map),
            "service": "BriefLookupSuperMetricFeedbackService"
        })
        
        updated_super_metrics: List[SuperMetric] = []
        
        for super_metric in super_metrics:
            super_metric_type = super_metric.metadata.super_metric_type
            feedback = feedback_map.get(super_metric_type)
            
            # If no feedback is available, create empty feedback
            if not feedback:
                feedback = self._create_empty_feedback()
            
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
            
            self.logger.debug("Updated super-metric with brief feedback", {
                "super_metric_type": super_metric_type.value,
                "brief_feedback_length": len(feedback.brief_feedback),
                "service": "BriefLookupSuperMetricFeedbackService"
            })
        
        return updated_super_metrics