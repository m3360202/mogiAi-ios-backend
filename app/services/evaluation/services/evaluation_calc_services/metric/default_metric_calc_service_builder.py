"""
Default Metric Calculation Service Builder.

This builder service creates metric calculation services based on metadata specifications.
"""


from app.services.evaluation.business import (
    MetricCalcServiceBuilder,
    MetricCalculationService, 
    MetricMetadata,
    MetricType,
    ScoreTransformationService,
    Logger,
    IdGenerator
)
from .conciseness_metric_calculation_service import ConcisenessMetricCalculationService
from .logical_structure_metric_calculation_service import LogicalStructureMetricCalculationService
from .evidence_metric_calculation_service import EvidenceMetricCalculationService
from .quantifiable_results_metric_calculation_service import QuantifiableResultsMetricCalculationService
from .audience_appropriateness_metric_calculation_service import AudienceAppropriatenessMetricCalculationService
from .active_listening_metric_calculation_service import ActiveListeningMetricCalculationService
from .company_research_metric_calculation_service import CompanyResearchMetricCalculationService
from .personal_ownership_metric_calculation_service import PersonalOwnershipMetricCalculationService
from .growth_metric_calculation_service import GrowthMetricCalculationService
from .verbal_visual_metric_calculation_service import VerbalVisualMetricCalculationService

class DefaultMetricCalcServiceBuilder(MetricCalcServiceBuilder):
    """
    Default implementation of MetricCalcServiceBuilder.
    
    Creates appropriate metric calculation services based on metric type.
    """
    
    def __init__(self, logger: Logger, id_generator: IdGenerator, score_transformation_service: ScoreTransformationService):
        """
        Initialize the builder.
        
        Args:
            logger: Logger instance for logging operations
            id_generator: ID generator for creating unique metric IDs
            score_transformation_service: Service for transforming between score labels and numeric scores
        """
        self.logger = logger
        self.id_generator = id_generator
        self.score_transformation_service = score_transformation_service
    
    def build(self, metadata: MetricMetadata) -> MetricCalculationService:
        """
        Build MetricCalculationService based on MetricMetadata.
        
        Args:
            metadata: Metadata specifying the metric type
            
        Returns:
            MetricCalculationService instance for the specified metric type
            
        Raises:
            ValueError: If metric type is not supported
        """
        try:
            self.logger.info("Building metric calculation service", {
                "metric_type": metadata.metric_type.value,
                "service": "DefaultMetricCalcServiceBuilder"
            })
            
            if metadata.metric_type == MetricType.CONCISENESS:
                conciseness_service = ConcisenessMetricCalculationService(
                    self.logger, 
                    self.id_generator,
                    self.score_transformation_service,
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built conciseness metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return conciseness_service
            
            elif metadata.metric_type == MetricType.LOGICAL_STRUCTURE:
                logical_structure_service = LogicalStructureMetricCalculationService(
                    self.logger, 
                    self.id_generator,
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built logical structure metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return logical_structure_service
            
            elif metadata.metric_type == MetricType.EVIDENCE:
                evidence_service = EvidenceMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built evidence metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return evidence_service
            
            elif metadata.metric_type == MetricType.QUANTIFIABLE_RESULTS:
                quantifiable_results_service = QuantifiableResultsMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    custom_eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built quantifiable results metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return quantifiable_results_service
            
            elif metadata.metric_type == MetricType.AUDIENCE_APPROPRIATENESS:
                audience_appropriateness_service = AudienceAppropriatenessMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built audience appropriateness metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return audience_appropriateness_service
            
            elif metadata.metric_type == MetricType.ACTIVE_LISTENING:
                active_listening_service = ActiveListeningMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built active listening metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return active_listening_service
            
            elif metadata.metric_type == MetricType.COMPANY_RESEARCH:
                company_research_service = CompanyResearchMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built company research metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return company_research_service
            
            elif metadata.metric_type == MetricType.PERSONAL_OWNERSHIP:
                personal_ownership_service = PersonalOwnershipMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    custom_eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built personal ownership metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return personal_ownership_service
            
            elif metadata.metric_type == MetricType.GROWTH:
                growth_service = GrowthMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    metadata.model,
                    eval_system_prompt_path=metadata.eval_system_prompt_path
                )
                self.logger.info("Successfully built growth metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "eval_system_prompt_path": metadata.eval_system_prompt_path,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return growth_service
            
            elif metadata.metric_type in [
                MetricType.PACE,
                MetricType.INTONATION,
                MetricType.VOLUME,
                MetricType.PRONOUNCIATION,
                MetricType.PAUSE,
                MetricType.EYE_CONTACT,
                MetricType.FACIAL_EXPRESSION,
                MetricType.POSTURE,
                MetricType.PERSONAL_APPEARANCE
            ]:
                # Use VerbalVisualMetricCalculationService for verbal and visual performance related metrics
                verbal_visual_service = VerbalVisualMetricCalculationService(
                    self.logger, 
                    self.id_generator, 
                    self.score_transformation_service
                )
                self.logger.info("Successfully built verbal visual metric calculation service", {
                    "metric_type": metadata.metric_type.value,
                    "model": metadata.model,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                return verbal_visual_service
            
            # Add other metric types here as they are implemented
            
            else:
                error_msg = f"Unsupported metric type: {metadata.metric_type.value}"
                self.logger.error("Unsupported metric type", None, {
                    "metric_type": metadata.metric_type.value,
                    "service": "DefaultMetricCalcServiceBuilder"
                })
                raise ValueError(error_msg)
                
        except Exception as e:
            self.logger.error("Failed to build metric calculation service", e, {
                "metric_type": metadata.metric_type.value if metadata else "unknown",
                "service": "DefaultMetricCalcServiceBuilder"
            })
            raise