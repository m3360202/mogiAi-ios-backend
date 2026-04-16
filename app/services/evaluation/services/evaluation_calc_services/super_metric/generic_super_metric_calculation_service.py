"""
Generic super-metric calculation service implementation.
"""
from typing import List, Dict, Tuple, Any
from app.services.evaluation.business import (
    SuperMetricCalculationService, MetricGroup, SuperMetricMetadata, SuperMetric,
    Score, SuperMetricSectionScore, ScoreTransformationService, Logger, SuperMetricFeedback
)


class GenericSuperMetricCalculationService(SuperMetricCalculationService):
    """
    Generic implementation of SuperMetricCalculationService that works for all super-metric types.
    Creates SuperMetric entities with scores and section scores, but without feedback text.
    """
    
    def __init__(self, logger: Logger, score_transformation_service: ScoreTransformationService):
        """
        Initialize the generic super-metric calculation service.
        
        Args:
            logger: Logger service for logging operations
            score_transformation_service: Service for transforming between score labels and numeric scores
        """
        self.logger = logger
        self.score_transformation_service = score_transformation_service
    
    def create_super_metric(
        self, 
        metric_groups: List[MetricGroup], 
        metadata: SuperMetricMetadata
    ) -> SuperMetric:
        """
        Create SuperMetric entity for any super-metric type based on metric groups.
        Internally implements score aggregation logic to calculate overall score by 
        aggregating metric scores with weights, and section scores by aggregating 
        metric scores for each dialog section. Does not generate feedback text.
        
        Args:
            metric_groups: List of metric groups to analyze
            metadata: The super-metric metadata defining the type and configuration
            
        Returns:
            SuperMetric: Super-metric with score and section scores, but empty feedback
        """
        try:
            self.logger.info("Creating generic super-metric", {
                "super_metric_type": metadata.super_metric_type.value,
                "metric_groups_count": len(metric_groups),
                "service": "GenericSuperMetricCalculationService"
            })
            
            # Calculate overall score by weighted aggregation of metric scores
            overall_score = self._calculate_overall_score(metric_groups, metadata)
            
            # Calculate section scores by aggregating metric scores for each dialog section
            section_scores = self._calculate_section_scores(metric_groups, metadata)
            
            # Create placeholder feedback (to be filled later by feedback service)
            placeholder_feedback = SuperMetricFeedback(
                brief_feedback="",
                revised_response="",
                feedback="",
                section_index=0  # Placeholder value
            )
            
            # Create super-metric with placeholder feedback
            super_metric = SuperMetric(
                metadata=metadata,
                metric_groups=metric_groups,
                score=overall_score,
                section_scores=section_scores,
                feedback=placeholder_feedback
            )
            
            self.logger.info("Successfully created generic super-metric", {
                "super_metric_type": metadata.super_metric_type.value,
                "overall_score_label": overall_score.score_label.value,
                "overall_numeric_score": overall_score.numeric_score,
                "section_scores_count": len(section_scores),
                "service": "GenericSuperMetricCalculationService"
            })
            
            return super_metric
            
        except Exception as e:
            self.logger.error("Failed to create generic super-metric", e, {
                "super_metric_type": metadata.super_metric_type.value,
                "metric_groups_count": len(metric_groups),
                "service": "GenericSuperMetricCalculationService"
            })
            raise
    
    def _calculate_overall_score(self, metric_groups: List[MetricGroup], metadata: SuperMetricMetadata) -> Score:
        """
        Calculate overall score by weighted aggregation of metric scores.
        
        Args:
            metric_groups: List of metric groups to aggregate
            metadata: Super-metric metadata containing weights
            
        Returns:
            Score: Aggregated overall score
        """
        # Create a mapping from metric type to weight
        metric_weights = {m.metric_type: m.weight for m in metadata.metric_metadata_list}
        
        # Calculate weighted sum of all metric scores
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for metric_group in metric_groups:
            weight = metric_weights.get(metric_group.metric_type, 1.0)  # Default weight of 1.0
            
            # Calculate average score for this metric group
            if metric_group.metrics:
                group_average_score = sum(metric.score.numeric_score for metric in metric_group.metrics) / len(metric_group.metrics)
                total_weighted_score += group_average_score * weight
                total_weight += weight
                # Log for debugging
                if group_average_score == 0.0:
                    self.logger.info("Zero score detected in metric group", {
                        "metric_type": metric_group.metric_type.value,
                        "group_average_score": group_average_score,
                        "metrics_count": len(metric_group.metrics),
                        "metric_scores": [m.score.numeric_score for m in metric_group.metrics],
                        "service": "GenericSuperMetricCalculationService"
                    })
        
        # Calculate final average score
        if total_weight > 0:
            final_numeric_score = total_weighted_score / total_weight
        else:
            final_numeric_score = 0.0
        
        # Use transformation service to determine score label and create consistent score
        score_label = self.score_transformation_service.numeric_score_to_label(final_numeric_score)
        return self.score_transformation_service.create_score(score_label, final_numeric_score)
    
    def _calculate_section_scores(
        self, 
        metric_groups: List[MetricGroup], 
        metadata: SuperMetricMetadata
    ) -> List[SuperMetricSectionScore]:
        """
        Calculate section scores by aggregating metric scores for each dialog section.
        
        Args:
            metric_groups: List of metric groups to aggregate
            metadata: Super-metric metadata containing weights
            
        Returns:
            List[SuperMetricSectionScore]: Section scores for each dialog section
        """
        # Create a mapping from metric type to weight
        metric_weights = {m.metric_type: m.weight for m in metadata.metric_metadata_list}
        
        # Group metrics by dialog section
        section_metrics: Dict[str, List[Tuple[Any, float]]] = {}  # section_id -> [(metric, weight), ...]
        
        for metric_group in metric_groups:
            weight = metric_weights.get(metric_group.metric_type, 1.0)  # Default weight of 1.0
            
            for metric in metric_group.metrics:
                section_id = metric.dialog_section_id
                if section_id not in section_metrics:
                    section_metrics[section_id] = []
                section_metrics[section_id].append((metric, weight))
        
        # Calculate aggregated score for each section
        section_scores: List[SuperMetricSectionScore] = []
        
        for section_id, metrics_with_weights in section_metrics.items():
            # Calculate weighted average for this section
            total_weighted_score = 0.0
            total_weight = 0.0
            section_index = 0  # We'll get this from the first metric
            
            for metric, weight in metrics_with_weights:
                total_weighted_score += metric.score.numeric_score * weight
                total_weight += weight
                # Get section index from the first metric in this section
                # All metrics in the same section should have the same section index
                section_index = metric.dialog_section_index
            
            # Calculate final section score
            if total_weight > 0:
                section_numeric_score = total_weighted_score / total_weight
            else:
                section_numeric_score = 0.0
            
            # Use transformation service to determine score label and create consistent score
            section_score_label = self.score_transformation_service.numeric_score_to_label(section_numeric_score)
            section_score_obj = self.score_transformation_service.create_score(section_score_label, section_numeric_score)
            
            section_score = SuperMetricSectionScore(
                section_id=section_id,
                section_index=section_index,
                score=section_score_obj
            )
            
            section_scores.append(section_score)
        
        # Sort by section_id for consistent ordering
        section_scores.sort(key=lambda x: x.section_id)
        
        return section_scores