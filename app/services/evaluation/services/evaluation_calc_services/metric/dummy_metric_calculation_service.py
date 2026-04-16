"""
Dummy Metric Calculation Service.

This service provides a basic implementation of MetricCalculationService for testing
and development purposes. It generates dummy metrics with fixed scores and empty revisions.
"""
from typing import List, Dict, Any
from app.services.evaluation.business import (
    MetricCalculationService,
    DialogSection, 
    Metric,
    MetricGroup,
    Score, 
    ScoreLabel,
    MetricMetadata,
    Logger,
    IdGenerator
)


class DummyMetricCalculationService(MetricCalculationService):
    """
    Dummy implementation of MetricCalculationService for testing purposes.
    
    This service creates metrics with:
    - Fixed dummy sub-metrics
    - Predetermined scores based on section index
    - Empty revision text
    """
    
    def __init__(self, logger: Logger, id_generator: IdGenerator):
        """
        Initialize the dummy service.
        
        Args:
            logger: Logger instance for logging operations
            id_generator: ID generator for creating unique metric IDs
        """
        self.logger = logger
        self.id_generator = id_generator
    
    async def create_metric_group(
        self, 
        dialog_sections: List[DialogSection], 
        metadata: MetricMetadata
    ) -> MetricGroup:
        """
        Create a MetricGroup with dummy metrics for each dialog section.
        
        Args:
            dialog_sections: The dialog sections to analyze
            metadata: The metric metadata 
            
        Returns:
            MetricGroup: Complete metric group with dummy metrics for each section
        """
        try:
            self.logger.info("Creating dummy metric group", {
                "dialog_sections_count": len(dialog_sections),
                "metric_type": metadata.metric_type.value,
                "service": "DummyMetricCalculationService"
            })
            
            metrics: List[Metric] = []
            
            for dialog_section in dialog_sections:
                # Generate unique metric ID for each section
                metric_id = self.id_generator.generate()
                
                self.logger.info("Processing dialog section for dummy metric", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "service": "DummyMetricCalculationService"
                })
                
                # Create metric entity for this section
                metric = Metric(
                    id=metric_id,
                    metadata=metadata,
                    dialog_section_id=dialog_section.id,
                    dialog_section_index=dialog_section.section_index,
                    sub_metrics={},
                    score=Score(
                        numeric_score=0,
                        score_label=ScoreLabel.POOR
                    ),
                    revision=""
                )
                
                metrics.append(metric)
                
                self.logger.info("Successfully created dummy metric for section", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "service": "DummyMetricCalculationService"
                })
            
            # Create metric group
            metric_group = MetricGroup(
                metric_type=metadata.metric_type,
                metrics=metrics
            )
            
            self.logger.info("Successfully created dummy metric group", {
                "dialog_sections_count": len(dialog_sections),
                "metrics_count": len(metrics),
                "metric_type": metadata.metric_type.value,
                "service": "DummyMetricCalculationService"
            })
            
            return metric_group
            
        except Exception as e:
            self.logger.error("Failed to create dummy metric group", e, {
                "dialog_sections_count": len(dialog_sections),
                "metric_type": metadata.metric_type.value if metadata else "unknown",
                "service": "DummyMetricCalculationService"
            })
            raise