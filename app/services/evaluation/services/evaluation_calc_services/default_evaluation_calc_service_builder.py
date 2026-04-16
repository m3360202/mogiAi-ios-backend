"""
Default evaluation calculation service builder implementation.
"""
from app.services.evaluation.business import (
    EvaluationCalcServiceBuilder, EvaluationCalculationService, EvaluationStrategy, ScoreTransformationService, Logger
)
from .generic_evaluation_calculation_service import GenericEvaluationCalculationService


class DefaultEvaluationCalcServiceBuilder(EvaluationCalcServiceBuilder):
    """
    Default implementation of EvaluationCalcServiceBuilder.
    Creates GenericEvaluationCalculationService for all evaluation strategies.
    """
    
    def __init__(self, logger: Logger, score_transformation_service: ScoreTransformationService):
        """
        Initialize the default evaluation calculation service builder.
        
        Args:
            logger: Logger service for logging operations
            score_transformation_service: Service for transforming between score labels and numeric scores
        """
        self.logger = logger
        self.score_transformation_service = score_transformation_service
    
    def build(self, strategy: EvaluationStrategy) -> EvaluationCalculationService:
        """
        Build EvaluationCalculationService based on EvaluationStrategy.
        Returns GenericEvaluationCalculationService for all evaluation strategies.
        
        Args:
            strategy: The evaluation strategy defining the configuration
            
        Returns:
            EvaluationCalculationService: Generic service that works for all evaluation strategies
        """
        self.logger.debug("Building evaluation calculation service", {
            "strategy_id": strategy.strategy_id,
            "strategy_name": strategy.name,
            "super_metrics_count": len(strategy.super_metric_metadata_list),
            "service": "DefaultEvaluationCalcServiceBuilder"
        })
        
        # Return generic service for all evaluation strategies
        return GenericEvaluationCalculationService(
            logger=self.logger, 
            score_transformation_service=self.score_transformation_service
        )