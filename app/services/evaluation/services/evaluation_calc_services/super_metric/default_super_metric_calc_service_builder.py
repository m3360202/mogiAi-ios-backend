"""
Default super-metric calculation service builder implementation.
"""
from app.services.evaluation.business import (
    SuperMetricCalcServiceBuilder, SuperMetricCalculationService, SuperMetricMetadata, ScoreTransformationService, Logger
)
from .generic_super_metric_calculation_service import GenericSuperMetricCalculationService


class DefaultSuperMetricCalcServiceBuilder(SuperMetricCalcServiceBuilder):
    """
    Default implementation of SuperMetricCalcServiceBuilder.
    Creates GenericSuperMetricCalculationService for all super-metric types.
    """
    
    def __init__(self, logger: Logger, score_transformation_service: ScoreTransformationService):
        """
        Initialize the default super-metric calculation service builder.
        
        Args:
            logger: Logger service for logging operations
            score_transformation_service: Service for transforming between score labels and numeric scores
        """
        self.logger = logger
        self.score_transformation_service = score_transformation_service
    
    def build(self, metadata: SuperMetricMetadata) -> SuperMetricCalculationService:
        """
        Build SuperMetricCalculationService based on SuperMetricMetadata.
        Returns GenericSuperMetricCalculationService for all super-metric types.
        
        Args:
            metadata: The super-metric metadata defining the type and configuration
            
        Returns:
            SuperMetricCalculationService: Generic service that works for all super-metric types
        """
        self.logger.debug("Building super-metric calculation service", {
            "super_metric_type": metadata.super_metric_type.value,
            "metric_count": len(metadata.metric_metadata_list),
            "service": "DefaultSuperMetricCalcServiceBuilder"
        })
        
        # Return generic service for all super-metric types
        return GenericSuperMetricCalculationService(
            logger=self.logger, 
            score_transformation_service=self.score_transformation_service
        )