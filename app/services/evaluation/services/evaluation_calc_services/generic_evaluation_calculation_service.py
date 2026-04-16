"""
Generic evaluation calculation service implementation.
"""
from typing import List
from app.services.evaluation.business import (
    EvaluationCalculationService, SuperMetric, Score, ScoreLabel, ScoreTransformationService, Logger
)


class GenericEvaluationCalculationService(EvaluationCalculationService):
    """
    Generic implementation of EvaluationCalculationService.
    Calculates overall evaluation score by aggregating super-metric scores with their weights.
    """
    
    def __init__(self, logger: Logger, score_transformation_service: ScoreTransformationService):
        """
        Initialize the generic evaluation calculation service.
        
        Args:
            logger: Logger service for logging operations
            score_transformation_service: Service for transforming between score labels and numeric scores
        """
        self.logger = logger
        self.score_transformation_service = score_transformation_service
    
    def calculate_score(self, super_metrics: List[SuperMetric]) -> Score:
        """
        Calculate overall evaluation score based on super-metrics.
        Aggregates super-metric scores using their weights to produce a final evaluation score.
        
        Args:
            super_metrics: List of super-metrics to aggregate
            
        Returns:
            Score: Overall evaluation score
        """
        try:
            self.logger.info("Calculating overall evaluation score", {
                "super_metrics_count": len(super_metrics),
                "service": "GenericEvaluationCalculationService"
            })
            
            if not super_metrics:
                self.logger.warning("No super-metrics provided for evaluation score calculation", None, {
                    "service": "GenericEvaluationCalculationService"
                })
                return self.score_transformation_service.create_score(ScoreLabel.POOR, 0.0)
            
            # Calculate weighted sum of super-metric scores
            total_weighted_score = 0.0
            total_weight = 0.0
            
            for super_metric in super_metrics:
                weight = super_metric.metadata.weight
                numeric_score = super_metric.score.numeric_score
                
                total_weighted_score += numeric_score * weight
                total_weight += weight
                
                self.logger.debug("Processing super-metric for evaluation score", {
                    "super_metric_type": super_metric.metadata.super_metric_type.value,
                    "weight": weight,
                    "numeric_score": numeric_score,
                    "score_label": super_metric.score.score_label.value,
                    "service": "GenericEvaluationCalculationService"
                })
            
            # Calculate final average score
            if total_weight > 0:
                final_numeric_score = total_weighted_score / total_weight
            else:
                final_numeric_score = 0.0
                self.logger.warning("Total weight is zero for evaluation score calculation", None, {
                    "service": "GenericEvaluationCalculationService"
                })
            
            # Use transformation service to determine score label and create consistent score
            score_label = self.score_transformation_service.numeric_score_to_label(final_numeric_score)
            final_score = self.score_transformation_service.create_score(score_label, final_numeric_score)
            
            self.logger.info("Successfully calculated overall evaluation score", {
                "final_score_label": final_score.score_label.value,
                "final_numeric_score": final_score.numeric_score,
                "total_weight": total_weight,
                "super_metrics_count": len(super_metrics),
                "service": "GenericEvaluationCalculationService"
            })
            
            return final_score
            
        except Exception as e:
            self.logger.error("Failed to calculate overall evaluation score", e, {
                "super_metrics_count": len(super_metrics) if super_metrics else 0,
                "service": "GenericEvaluationCalculationService"
            })
            raise