"""
Evaluation Use Case implementation.

This module contains the interface and implementation for the evaluation use case
as described in the technical design document.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from collections import defaultdict

from ..business.entities import (
    DialogSection, Metric, EvaluationRecord, EvaluationStrategy
)
from ..business.value_objects import (
    RawDialogInfo, MetricGroup, SuperMetric
)
from ..business.repositories import (
    DialogSectionRepo, MetricRepo, EvaluationRecordRepo, EvaluationStrategyRepo
)
from ..business.services import (
    MetricCalcServiceBuilder, SuperMetricCalcServiceBuilder, 
    EvaluationCalcServiceBuilder, SuperMetricFeedbackServiceBuilder, 
    DialogSectionBuilder, Logger, IdGenerator
)



class EvaluationUseCase(ABC):
    """
    Use case interface for handling evaluation-related operations.
    """
    
    @abstractmethod
    async def execute(self, raw_dialog_info: RawDialogInfo) -> EvaluationRecord:
        """
        Execute the evaluation process for a RawDialogInfo.
        
        Args:
            raw_dialog_info: The raw dialog information to evaluate
            
        Returns:
            EvaluationRecord: The completed evaluation record
        """
        raise NotImplementedError


class EvaluationUseCaseImpl(EvaluationUseCase):
    """
    Implementation of the EvaluationUseCase.
    
    This class orchestrates the entire evaluation process according to the
    technical design specifications.
    """
    
    def __init__(
        self,
        strategy_id: str,
        dialog_section_repo: DialogSectionRepo,
        metric_repo: MetricRepo,
        evaluation_record_repo: EvaluationRecordRepo,
        evaluation_strategy_repo: EvaluationStrategyRepo,
        dialog_section_builder: DialogSectionBuilder,
        metric_calc_service_builder: MetricCalcServiceBuilder,
        super_metric_calc_service_builder: SuperMetricCalcServiceBuilder,
        evaluation_calc_service_builder: EvaluationCalcServiceBuilder,
        super_metric_feedback_service_builder: SuperMetricFeedbackServiceBuilder,
        dialog_section_id_generator: IdGenerator,
        metric_id_generator: IdGenerator,
        evaluation_record_id_generator: IdGenerator,
        logger: Logger
    ):
        """
        Initialize the evaluation use case implementation.
        
        Args:
            strategy_id: The ID of the evaluation strategy to use
            dialog_section_repo: Repository for dialog sections
            metric_repo: Repository for metrics
            evaluation_record_repo: Repository for evaluation records
            evaluation_strategy_repo: Repository for evaluation strategies
            dialog_section_builder: Builder for creating dialog sections from raw dialog info
            metric_calc_service_builder: Builder for metric calculation services
            super_metric_calc_service_builder: Builder for super-metric calculation services
            evaluation_calc_service_builder: Builder for evaluation calculation services
            super_metric_feedback_service_builder: Builder for creating super-metric feedback services
            dialog_section_id_generator: ID generator for dialog sections
            metric_id_generator: ID generator for metrics
            evaluation_record_id_generator: ID generator for evaluation records
            logger: Logger service
        """
        self._dialog_section_repo = dialog_section_repo
        self._metric_repo = metric_repo
        self._evaluation_record_repo = evaluation_record_repo
        self._evaluation_strategy_repo = evaluation_strategy_repo
        self._dialog_section_builder = dialog_section_builder
        self._metric_calc_service_builder = metric_calc_service_builder
        self._super_metric_calc_service_builder = super_metric_calc_service_builder
        self._evaluation_calc_service_builder = evaluation_calc_service_builder
        self._super_metric_feedback_service_builder = super_metric_feedback_service_builder
        self._dialog_section_id_generator = dialog_section_id_generator
        self._metric_id_generator = metric_id_generator
        self._evaluation_record_id_generator = evaluation_record_id_generator
        self._logger = logger
        
        # Retrieve strategy and prepare calculation services during initialization
        self._strategy = self._get_evaluation_strategy(strategy_id)
        self._calculation_services = self._prepare_calculation_services(self._strategy)
    
    async def execute(self, raw_dialog_info: RawDialogInfo) -> EvaluationRecord:
        """
        Execute the evaluation process for a RawDialogInfo.
        
        This method implements the complete evaluation workflow as described 
        in the technical design document.
        
        Args:
            raw_dialog_info: The raw dialog information to evaluate
            
        Returns:
            EvaluationRecord: The completed evaluation record
        """
        self._logger.info(
            "evaluation.EvaluationUseCaseImpl.execute.start", 
            {
                "dialog_id": raw_dialog_info.dialog_id,
                "strategy_id": self._strategy.strategy_id,
                "message_count": len(raw_dialog_info.messages)
            }
        )
        
        try:
            # Step 1: Prepare DialogSections
            dialog_sections = self._dialog_section_builder.build_dialog_sections(raw_dialog_info)
            
            # Persist dialog sections
            for section in dialog_sections:
                self._dialog_section_repo.save(section)
            
            # **Part 1: Compute Scores**
            
            # Step 2: Build metrics
            all_metrics = await self._build_metrics(dialog_sections, self._strategy, self._calculation_services)
            
            # Step 3: Build super-metrics (scores only)
            super_metrics_without_feedback = self._build_super_metrics(all_metrics, self._strategy, self._calculation_services)
            
            # Step 4: Calculate overall score
            overall_score = self._calculation_services["evaluation"].calculate_score(super_metrics_without_feedback)
            
            # **Part 2: Generate Feedback**
            
            # Step 5: Build feedback service and generate feedback for all super-metrics
            super_metric_feedback_service = self._super_metric_feedback_service_builder.build(self._strategy)
            super_metrics = await super_metric_feedback_service.generate_and_update_feedback(super_metrics_without_feedback)
            
            # Step 6: Create and persist evaluation record
            evaluation_record = EvaluationRecord(
                id=self._evaluation_record_id_generator.generate(),
                strategy=self._strategy,
                interview_record_id=raw_dialog_info.dialog_id,  # Assuming dialog_id maps to interview_record_id
                super_metrics=super_metrics,
                overall_score=overall_score
            )
            
            self._evaluation_record_repo.save(evaluation_record)
            
            self._logger.info(
                "evaluation.EvaluationUseCaseImpl.execute.end",
                {
                    "evaluation_record_id": evaluation_record.id,
                    "overall_score": overall_score.numeric_score,
                    "super_metrics_count": len(super_metrics)
                }
            )
            
            return evaluation_record
            
        except Exception as e:
            self._logger.error(
                "evaluation.EvaluationUseCaseImpl.execute.error",
                e,
                {
                    "dialog_id": raw_dialog_info.dialog_id,
                    "strategy_id": self._strategy.strategy_id,
                    "error": str(e)
                }
            )
            raise
    

    
    def _get_evaluation_strategy(self, strategy_id: str) -> EvaluationStrategy:
        """
        Retrieve the evaluation strategy.
        
        Args:
            strategy_id: The strategy ID
            
        Returns:
            EvaluationStrategy: The evaluation strategy
            
        Raises:
            ValueError: If strategy is not found
        """
        strategy = self._evaluation_strategy_repo.get_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"Evaluation strategy not found: {strategy_id}")
        
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.get_evaluation_strategy.end",
            {
                "strategy_id": strategy_id,
                "strategy_name": strategy.name,
                "super_metrics_count": len(strategy.super_metric_metadata_list)
            }
        )
        
        return strategy
    
    def _prepare_calculation_services(self, strategy: EvaluationStrategy) -> Dict[str, Any]:
        """
        Prepare all calculation services needed for the evaluation.
        
        Args:
            strategy: The evaluation strategy
            
        Returns:
            Dict containing all calculation services organized by type
        """
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.prepare_calculation_services.start",
            {"strategy_id": strategy.strategy_id}
        )
        
        # Build evaluation calculation service
        evaluation_service = self._evaluation_calc_service_builder.build(strategy)
        
        # Build super-metric calculation services
        super_metric_services = {}
        for super_metric_metadata in strategy.super_metric_metadata_list:
            service = self._super_metric_calc_service_builder.build(super_metric_metadata)
            super_metric_services[super_metric_metadata.super_metric_type] = service
        
        # Build metric calculation services
        metric_services = {}
        for super_metric_metadata in strategy.super_metric_metadata_list:
            for metric_metadata in super_metric_metadata.metric_metadata_list:
                if metric_metadata.metric_type not in metric_services:
                    metric_service = self._metric_calc_service_builder.build(metric_metadata)
                    metric_services[metric_metadata.metric_type] = metric_service
        
        services = {
            "evaluation": evaluation_service,
            "super_metrics": super_metric_services,
            "metrics": metric_services
        }
        
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.prepare_calculation_services.end",
            {
                "strategy_id": strategy.strategy_id,
                "super_metric_services": len(super_metric_services),
                "metric_services": len(metric_services)
            }
        )
        
        return services
    
    async def _build_metrics(
        self, 
        dialog_sections: List[DialogSection], 
        strategy: EvaluationStrategy,
        calculation_services: Dict[str, Any]
    ) -> List[Metric]:
        """
        Build metrics for all dialog sections and metric types.
        
        Args:
            dialog_sections: The dialog sections to analyze
            strategy: The evaluation strategy
            calculation_services: The calculation services
            
        Returns:
            List[Metric]: All created metrics
        """
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.build_metrics.start",
            {
                "dialog_sections_count": len(dialog_sections),
                "strategy_id": strategy.strategy_id
            }
        )
        
        all_metrics = []
        
        # Get all unique metric metadata from the strategy
        all_metric_metadata = []
        for super_metric_metadata in strategy.super_metric_metadata_list:
            all_metric_metadata.extend(super_metric_metadata.metric_metadata_list)
        
        # Remove duplicates while preserving order
        unique_metric_metadata = []
        seen_types = set()
        for metadata in all_metric_metadata:
            if metadata.metric_type not in seen_types:
                unique_metric_metadata.append(metadata)
                seen_types.add(metadata.metric_type)
        
        # Build metric groups for each metric type in parallel
        async def create_metric_group_safe(metric_metadata):
            """Create metric group with error handling for continue-on-fail."""
            try:
                metric_service = calculation_services["metrics"][metric_metadata.metric_type]
                # Create metric group using the async interface
                metric_group = await metric_service.create_metric_group(
                    dialog_sections=dialog_sections,
                    metadata=metric_metadata
                )
                
                # Save all metrics within the group
                for metric in metric_group.metrics:
                    self._metric_repo.save(metric)
                
                self._logger.info("Successfully created metric group", {
                    "metric_type": metric_metadata.metric_type.value,
                    "metrics_count": len(metric_group.metrics),
                    "service": "EvaluationUseCaseImpl"
                })
                
                return metric_group.metrics
                
            except Exception as e:
                self._logger.error(f"Failed to create metric group for {metric_metadata.metric_type}", e, {
                    "metric_type": metric_metadata.metric_type,
                    "service": "EvaluationUseCaseImpl"
                })
                # Continue on fail - return placeholder metrics for this metric type
                return self._create_placeholder_metrics(dialog_sections, metric_metadata)
        
        # Execute all metric services in parallel
        metric_tasks = [create_metric_group_safe(metadata) for metadata in unique_metric_metadata]
        metric_results = await asyncio.gather(*metric_tasks, return_exceptions=False)
        
        # Flatten results into single list
        for metrics_list in metric_results:
            all_metrics.extend(metrics_list)
        
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.build_metrics.end",
            {
                "total_metrics": len(all_metrics),
                "dialog_sections": len(dialog_sections),
                "metric_types": len(unique_metric_metadata)
            }
        )
        
        return all_metrics
    
    def _create_placeholder_metrics(self, dialog_sections: List[DialogSection], metric_metadata: Any) -> List[Metric]:
        """
        Create placeholder metrics when a metric service fails.
        
        Args:
            dialog_sections: Dialog sections to create placeholders for
            metric_metadata: Metadata for the metric type
            
        Returns:
            List[Metric]: Placeholder metrics with neutral scores
        """
        from ..business.value_objects import Score
        from ..business.enums import ScoreLabel
        
        placeholder_metrics = []
        
        for dialog_section in dialog_sections:
            # Create a placeholder metric with neutral/default values
            placeholder_metric = Metric(
                id=self._metric_id_generator.generate(),
                metadata=metric_metadata,
                dialog_section_id=dialog_section.id,
                dialog_section_index=dialog_section.section_index,
                sub_metrics={"error": "Service unavailable - placeholder metric"},
                score=Score(score_label=ScoreLabel.FAIR, numeric_score=50.0),  # Neutral score
                revision=""
            )
            
            # Save the placeholder metric
            self._metric_repo.save(placeholder_metric)
            placeholder_metrics.append(placeholder_metric)
        
        self._logger.warning(f"Created {len(placeholder_metrics)} placeholder metrics for {metric_metadata.metric_type}", None, {
            "metric_type": metric_metadata.metric_type,
            "dialog_sections_count": len(dialog_sections),
            "service": "EvaluationUseCaseImpl"
        })
        
        return placeholder_metrics
    
    def _build_super_metrics(
        self, 
        all_metrics: List[Metric], 
        strategy: EvaluationStrategy,
        calculation_services: Dict[str, Any]
    ) -> List[SuperMetric]:
        """
        Build super-metrics from grouped metrics.
        
        Args:
            all_metrics: All metrics created in the previous step
            strategy: The evaluation strategy
            calculation_services: The calculation services
            
        Returns:
            List[SuperMetric]: The created super-metrics
        """
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.build_super_metrics.start",
            {
                "total_metrics": len(all_metrics),
                "strategy_id": strategy.strategy_id
            }
        )
        
        super_metrics = []
        
        for super_metric_metadata in strategy.super_metric_metadata_list:
            # Group metrics by metric type for this super-metric
            metric_groups_dict = defaultdict(list)
            
            for metric in all_metrics:
                # Check if this metric belongs to this super-metric
                for metadata in super_metric_metadata.metric_metadata_list:
                    if metric.metadata.metric_type == metadata.metric_type:
                        metric_groups_dict[metadata.metric_type].append(metric)
            
            # Create MetricGroup objects
            metric_groups = [
                MetricGroup(metric_type=metric_type, metrics=metrics)
                for metric_type, metrics in metric_groups_dict.items()
            ]
            
            # Get super-metric calculation service
            super_metric_service = calculation_services["super_metrics"][super_metric_metadata.super_metric_type]
            
            # Create super-metric using the new merged interface
            super_metric = super_metric_service.create_super_metric(
                metric_groups=metric_groups,
                metadata=super_metric_metadata
            )
            
            super_metrics.append(super_metric)
        
        self._logger.debug(
            "evaluation.EvaluationUseCaseImpl.build_super_metrics.end",
            {
                "super_metrics_count": len(super_metrics),
                "strategy_id": strategy.strategy_id
            }
        )
        
        return super_metrics