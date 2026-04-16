"""
Two-Phase Evaluation Use Case implementation.

This module contains the interface and implementation for the two-phase evaluation use case
that separates section-level evaluation from overall evaluation.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from collections import defaultdict
from uuid import UUID

from ..business.entities import (
    DialogSection, Metric, EvaluationRecord, EvaluationStrategy
)
from ..business.value_objects import (
    RawDialogInfo, MetricGroup, SuperMetric, SectionEvaluationResult
)
from ..business.repositories import (
    DialogSectionRepo, MetricRepo, EvaluationRecordRepo, EvaluationStrategyRepo
)
from ..business.services import (
    DialogSectionBuilder,
    EvaluationCalcServiceBuilder,
    IdGenerator,
    Logger,
    MetricCalcServiceBuilder,
    SimpleSectionFeedbackServiceBuilder,
    SuperMetricCalcServiceBuilder,
)
from ..business.enums import ScoreLabel
from app.services.evaluation.services.feedback_services.rule_based_feedback import (
    build_rule_based_feedback,
)


class TwoPhaseEvaluationUseCase(ABC):
    """
    Use case interface for two-phase evaluation operations.
    
    Phase 1: Evaluate individual sections with scores and feedback
    Phase 2: Generate overall evaluation from section results
    """
    
    @abstractmethod
    async def evaluate_section(
        self, 
        section: DialogSection, 
        user_id: Optional[UUID] = None,
        cached_feedback: Optional[Dict[str, Any]] = None
    ) -> SectionEvaluationResult:
        """
        Phase 1: Evaluate a single section with scores and feedback.
        
        Args:
            section: The dialog section to evaluate
            user_id: Optional user ID for querying previous scores
            cached_feedback: Optional cached feedback from unified evaluation (avoids re-generation)
            
        Returns:
            SectionEvaluationResult: Evaluation result for the section
        """
        raise NotImplementedError
    
    @abstractmethod 
    async def evaluate_overall(self, section_results: List[SectionEvaluationResult]) -> EvaluationRecord:
        """
        Phase 2: Generate overall evaluation record from section results.
        
        Args:
            section_results: List of section evaluation results from Phase 1
            
        Returns:
            EvaluationRecord: The completed overall evaluation record
        """
        raise NotImplementedError


class TwoPhaseEvaluationUseCaseImpl(TwoPhaseEvaluationUseCase):
    """
    Implementation of the TwoPhaseEvaluationUseCase.
    
    This class implements a two-phase evaluation process:
    1. Section-level evaluation with parallel scoring and feedback
    2. Overall evaluation combining section results
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
        simple_section_feedback_service_builder: SimpleSectionFeedbackServiceBuilder,
        dialog_section_id_generator: IdGenerator,
        metric_id_generator: IdGenerator,
        evaluation_record_id_generator: IdGenerator,
        logger: Logger
    ):
        """
        Initialize the two-phase evaluation use case implementation.
        
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
            simple_section_feedback_service_builder: Builder for simple section feedback services
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
        self._simple_section_feedback_service_builder = simple_section_feedback_service_builder
        self._dialog_section_id_generator = dialog_section_id_generator
        self._metric_id_generator = metric_id_generator
        self._evaluation_record_id_generator = evaluation_record_id_generator
        self._logger = logger
        
        # Retrieve strategy and prepare calculation services during initialization
        self._strategy = self._get_evaluation_strategy(strategy_id)
        self._calculation_services = self._prepare_calculation_services(self._strategy)
    
    async def evaluate_section(
        self, 
        section: DialogSection, 
        user_id: Optional[UUID] = None,
        cached_feedback: Optional[Dict[str, Any]] = None
    ) -> SectionEvaluationResult:
        """
        Phase 1: Evaluate a single section with scores and feedback.
        
        This method:
        1. Builds metrics for the section in parallel
        2. Builds super-metrics from the metrics
        3. Generates feedback for all super-metrics in parallel (using cache if available)
        
        Args:
            section: The dialog section to evaluate
            user_id: Optional user ID for querying previous scores
            cached_feedback: Optional cached feedback from unified evaluation
            
        Returns:
            SectionEvaluationResult: Evaluation result for the section
        """
        self._logger.info(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.evaluate_section.start", 
            {
                "section_id": section.id,
                "section_index": section.section_index,
                "strategy_id": self._strategy.strategy_id,
                "user_id": str(user_id) if user_id else None,
                "has_cached_feedback": bool(cached_feedback)
            }
        )
        
        try:
            # Step 1: Build metrics for this section (parallel processing)
            section_metrics = await self._build_metrics_for_section(section, self._strategy, self._calculation_services)
            
            # Step 2: Build super-metrics from the metrics (scores only)
            super_metrics_without_feedback = self._build_super_metrics_from_metrics(
                section_metrics, self._strategy, self._calculation_services
            )
            
            # Step 3: Generate feedback for all super-metrics in parallel
            # For each super-metric, we'll query its previous score individually
            # (since different super-metrics may have different previous scores)
            
            super_metrics_with_feedback = await self._generate_section_feedback_parallel(
                section=section,
                super_metrics=super_metrics_without_feedback,
                language=section.language,
                current_score=None,  # Will be calculated per super-metric in the feedback service
                previous_score=None,  # Will be queried per super-metric in the feedback service
                user_id=user_id,  # Pass user_id to query previous scores
                cached_feedback=cached_feedback  # Pass cached feedback
            )
            
            result = SectionEvaluationResult(
                section_id=section.id,
                section_index=section.section_index,
                super_metrics=super_metrics_with_feedback
            )
            
            self._logger.info(
                "evaluation.TwoPhaseEvaluationUseCaseImpl.evaluate_section.end",
                {
                    "section_id": section.id,
                    "section_index": section.section_index,
                    "super_metrics_count": len(super_metrics_with_feedback)
                }
            )
            
            return result
            
        except Exception as e:
            self._logger.error(
                "evaluation.TwoPhaseEvaluationUseCaseImpl.evaluate_section.error",
                e,
                {
                    "section_id": section.id,
                    "section_index": section.section_index,
                    "strategy_id": self._strategy.strategy_id,
                    "error": str(e)
                }
            )
            raise
    
    async def evaluate_overall(self, section_results: List[SectionEvaluationResult]) -> EvaluationRecord:
        """
        Phase 2: Generate overall evaluation record from section results.
        
        This method:
        1. Combines super-metrics from all sections
        2. Calculates overall score using existing logic
        3. Generates overall feedback by picking contributing section feedbacks
        4. Creates and persists the final evaluation record
        
        Args:
            section_results: List of section evaluation results from Phase 1
            
        Returns:
            EvaluationRecord: The completed overall evaluation record
        """
        self._logger.info(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.evaluate_overall.start", 
            {
                "section_results_count": len(section_results),
                "strategy_id": self._strategy.strategy_id
            }
        )
        
        try:
            # Step 1: Combine super-metrics from all sections
            all_super_metrics = []
            for section_result in section_results:
                all_super_metrics.extend(section_result.super_metrics)
            
            # Step 2: Calculate overall score
            overall_score = self._calculation_services["evaluation"].calculate_score(all_super_metrics)
            
            # Step 3: Generate overall feedback by picking contributing section feedbacks
            super_metrics_with_overall_feedback = self._generate_overall_feedback_from_sections(
                all_super_metrics, section_results
            )
            
            # Step 4: Create evaluation record
            evaluation_record = EvaluationRecord(
                id=self._evaluation_record_id_generator.generate(),
                strategy=self._strategy,
                interview_record_id=f"combined_{len(section_results)}_sections",  # Placeholder
                super_metrics=super_metrics_with_overall_feedback,
                overall_score=overall_score
            )
            
            # Step 5: Persist evaluation record
            self._evaluation_record_repo.save(evaluation_record)
            
            self._logger.info(
                "evaluation.TwoPhaseEvaluationUseCaseImpl.evaluate_overall.end",
                {
                    "evaluation_record_id": evaluation_record.id,
                    "overall_score": overall_score.numeric_score,
                    "super_metrics_count": len(super_metrics_with_overall_feedback)
                }
            )
            
            return evaluation_record
            
        except Exception as e:
            self._logger.error(
                "evaluation.TwoPhaseEvaluationUseCaseImpl.evaluate_overall.error",
                e,
                {
                    "section_results_count": len(section_results),
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
            "evaluation.TwoPhaseEvaluationUseCaseImpl.get_evaluation_strategy.end",
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
            "evaluation.TwoPhaseEvaluationUseCaseImpl.prepare_calculation_services.start",
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
            "evaluation.TwoPhaseEvaluationUseCaseImpl.prepare_calculation_services.end",
            {
                "strategy_id": strategy.strategy_id,
                "super_metric_services": len(super_metric_services),
                "metric_services": len(metric_services)
            }
        )
        
        return services
    
    async def _build_metrics_for_section(
        self, 
        section: DialogSection, 
        strategy: EvaluationStrategy,
        calculation_services: Dict[str, Any]
    ) -> List[Metric]:
        """
        Build metrics for a single section (parallel processing like original).
        
        Args:
            section: The dialog section to analyze
            strategy: The evaluation strategy
            calculation_services: The calculation services
            
        Returns:
            List[Metric]: All created metrics for the section
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.build_metrics_for_section.start",
            {
                "section_id": section.id,
                "section_index": section.section_index,
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
                # Create metric group using single section (pass as list)
                metric_group = await metric_service.create_metric_group(
                    dialog_sections=[section],  # Single section in list
                    metadata=metric_metadata
                )
                
                # Save all metrics within the group
                for metric in metric_group.metrics:
                    self._metric_repo.save(metric)
                
                self._logger.info("Successfully created metric group for section", {
                    "metric_type": metric_metadata.metric_type.value,
                    "metrics_count": len(metric_group.metrics),
                    "section_id": section.id,
                    "service": "TwoPhaseEvaluationUseCaseImpl"
                })
                
                return metric_group.metrics
                
            except Exception as e:
                self._logger.error(f"Failed to create metric group for section {section.id}", e, {
                    "metric_type": metric_metadata.metric_type,
                    "section_id": section.id,
                    "service": "TwoPhaseEvaluationUseCaseImpl"
                })
                # Continue on fail - return placeholder metrics for this metric type
                return self._create_placeholder_metrics_for_section(section, metric_metadata)
        
        # Execute all metric services in parallel
        metric_tasks = [create_metric_group_safe(metadata) for metadata in unique_metric_metadata]
        metric_results = await asyncio.gather(*metric_tasks, return_exceptions=False)
        
        # Flatten results into single list
        for metrics_list in metric_results:
            all_metrics.extend(metrics_list)
        
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.build_metrics_for_section.end",
            {
                "total_metrics": len(all_metrics),
                "section_id": section.id,
                "metric_types": len(unique_metric_metadata)
            }
        )
        
        return all_metrics
    
    def _create_placeholder_metrics_for_section(self, section: DialogSection, metric_metadata: Any) -> List[Metric]:
        """
        Create placeholder metrics when a metric service fails for a section.
        
        Args:
            section: Dialog section to create placeholder for
            metric_metadata: Metadata for the metric type
            
        Returns:
            List[Metric]: Placeholder metrics with neutral scores
        """
        from ..business.value_objects import Score
        from ..business.enums import ScoreLabel
        
        # Create a placeholder metric with neutral/default values
        placeholder_metric = Metric(
            id=self._metric_id_generator.generate(),
            metadata=metric_metadata,
            dialog_section_id=section.id,
            dialog_section_index=section.section_index,
            sub_metrics={"error": "Service unavailable - placeholder metric"},
            score=Score(score_label=ScoreLabel.FAIR, numeric_score=50.0),  # Neutral score
            revision=""
        )
        
        # Save the placeholder metric
        self._metric_repo.save(placeholder_metric)
        
        self._logger.warning(f"Created placeholder metric for section {section.id}", None, {
            "metric_type": metric_metadata.metric_type,
            "section_id": section.id,
            "service": "TwoPhaseEvaluationUseCaseImpl"
        })
        
        return [placeholder_metric]
    
    def _build_super_metrics_from_metrics(
        self, 
        section_metrics: List[Metric], 
        strategy: EvaluationStrategy,
        calculation_services: Dict[str, Any]
    ) -> List[SuperMetric]:
        """
        Build super-metrics from section metrics (same logic as original).
        
        Args:
            section_metrics: All metrics for a section
            strategy: The evaluation strategy
            calculation_services: The calculation services
            
        Returns:
            List[SuperMetric]: The created super-metrics
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.build_super_metrics_from_metrics.start",
            {
                "section_metrics_count": len(section_metrics),
                "strategy_id": strategy.strategy_id
            }
        )
        
        super_metrics = []
        
        for super_metric_metadata in strategy.super_metric_metadata_list:
            # Group metrics by metric type for this super-metric
            metric_groups_dict = defaultdict(list)
            
            for metric in section_metrics:
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
            
            # Create super-metric using the existing interface
            super_metric = super_metric_service.create_super_metric(
                metric_groups=metric_groups,
                metadata=super_metric_metadata
            )
            
            super_metrics.append(super_metric)
        
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.build_super_metrics_from_metrics.end",
            {
                "super_metrics_count": len(super_metrics),
                "strategy_id": strategy.strategy_id
            }
        )
        
        return super_metrics
    
    async def _generate_section_feedback_parallel(
        self, 
        section: DialogSection, 
        super_metrics: List[SuperMetric],
        language: str = "ja",
        current_score: Optional[float] = None,
        previous_score: Optional[float] = None,
        user_id: Optional[UUID] = None,
        cached_feedback: Optional[Dict[str, Any]] = None
    ) -> List[SuperMetric]:
        """
        Generate feedback for all super-metrics in parallel for a section.
        
        Args:
            section: The dialog section
            super_metrics: Super-metrics without feedback
            language: Language for feedback generation
            cached_feedback: Optional cached feedback from unified evaluation
            
        Returns:
            List[SuperMetric]: Super-metrics with feedback included
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.generate_section_feedback_parallel.start",
            {
                "section_id": section.id,
                "super_metrics_count": len(super_metrics),
                "language": language,
                "has_cached_feedback": bool(cached_feedback)
            }
        )
        
        # Build simple section feedback service
        simple_feedback_service = self._simple_section_feedback_service_builder.build(self._strategy)
        
        # ⚡ 优化：只查询一次数据库，获取所有维度的历史得分
        previous_scores_dict: Optional[Dict[str, float]] = None
        # 如果有cached_feedback，我们可能不需要查询 previous_scores（因为已经用过了）
        # 但为了保险起见（可能某些维度缺失），还是查询一下，除非所有维度都有缓存
        
        need_db_query = True
        if cached_feedback:
            # 检查是否覆盖了所有super_metrics
            covered_count = sum(1 for sm in super_metrics if sm.metadata.super_metric_type.value.lower() in cached_feedback)
            if covered_count == len(super_metrics):
                need_db_query = False
        
        if user_id is not None and need_db_query:
            try:
                from app.services.interview_evaluation_orchestrator import get_previous_scores_for_user
                from datetime import datetime
                previous_scores_dict = await get_previous_scores_for_user(
                    user_id=user_id,
                    current_time=datetime.utcnow()
                )
                if previous_scores_dict:
                    self._logger.debug(f"Loaded previous scores for {len(previous_scores_dict)} dimensions: {list(previous_scores_dict.keys())}")
            except Exception as query_err:
                self._logger.warning(f"Failed to query previous scores: {query_err}")
                previous_scores_dict = None
        
        async def generate_feedback_for_super_metric_safe(super_metric: SuperMetric) -> SuperMetric:
            """Generate feedback for a super-metric with error handling."""
            try:
                # 1. 尝试使用 Cached Feedback
                if cached_feedback:
                    dim_key = super_metric.metadata.super_metric_type.value.lower()
                    if dim_key in cached_feedback:
                        cached_data = cached_feedback[dim_key]
                        # 构造 SuperMetricFeedback 对象
                        from ..business.value_objects import SuperMetricFeedback
                        
                        feedback_obj = SuperMetricFeedback(
                            brief_feedback=cached_data.get("brief_feedback", ""),
                            revised_response=cached_data.get("revised_response", "") or "",
                            feedback=cached_data.get("detailed_feedback", "") or cached_data.get("feedback", ""),
                            section_index=section.section_index
                        )
                        
                        # 如果缓存中有score，甚至可以更新score（虽然这里只负责feedback）
                        # 但为了保持一致性，score 通常在 _build_metrics_for_section 阶段计算
                        # 这里我们只使用 feedback
                        
                        return SuperMetric(
                            metadata=super_metric.metadata,
                            metric_groups=super_metric.metric_groups,
                            score=super_metric.score,
                            section_scores=super_metric.section_scores,
                            section_feedbacks=super_metric.section_feedbacks,
                            feedback=feedback_obj
                        )

                # 2. 如果没有缓存，走原有逻辑（调用LLM）
                # 从缓存的 previous_scores_dict 中获取对应维度的得分
                metric_previous_score = previous_score
                if previous_scores_dict:
                    dim_key = super_metric.metadata.super_metric_type.value.lower()
                    metric_previous_score = previous_scores_dict.get(dim_key) or previous_scores_dict.get("overall")
                
                feedback = await simple_feedback_service.generate_feedback_for_super_metric(
                    section=section,
                    super_metric=super_metric,
                    language=language,
                    current_score=current_score,
                    previous_score=metric_previous_score
                )
                
                # Create new SuperMetric with feedback
                return SuperMetric(
                    metadata=super_metric.metadata,
                    metric_groups=super_metric.metric_groups,
                    score=super_metric.score,
                    section_scores=super_metric.section_scores,
                    section_feedbacks=super_metric.section_feedbacks,
                    feedback=feedback
                )
                
            except Exception as e:
                self._logger.error(f"Failed to generate feedback for super-metric {super_metric.metadata.super_metric_type}", e, {
                    "super_metric_type": super_metric.metadata.super_metric_type,
                    "section_id": section.id,
                    "service": "TwoPhaseEvaluationUseCaseImpl"
                })
                # Return original super-metric with placeholder feedback
                return self._create_placeholder_feedback_super_metric(super_metric, section)
        
        # Generate feedback for all super-metrics in parallel
        feedback_tasks = [generate_feedback_for_super_metric_safe(sm) for sm in super_metrics]
        super_metrics_with_feedback = await asyncio.gather(*feedback_tasks, return_exceptions=False)
        
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.generate_section_feedback_parallel.end",
            {
                "section_id": section.id,
                "super_metrics_with_feedback_count": len(super_metrics_with_feedback)
            }
        )
        
        return super_metrics_with_feedback
    
    def _create_placeholder_feedback_super_metric(self, super_metric: SuperMetric, section: DialogSection) -> SuperMetric:
        """
        Create a super-metric with placeholder feedback when feedback generation fails.
        
        Args:
            super_metric: Original super-metric without feedback
            section: The dialog section
            
        Returns:
            SuperMetric: Super-metric with placeholder feedback
        """
        return SuperMetric(
            metadata=super_metric.metadata,
            metric_groups=super_metric.metric_groups,
            score=super_metric.score,
            section_scores=super_metric.section_scores,
            section_feedbacks=super_metric.section_feedbacks,
            feedback=build_rule_based_feedback(super_metric, section)
        )
    
    def _generate_overall_feedback_from_sections(
        self, 
        all_super_metrics: List[SuperMetric],
        section_results: List[SectionEvaluationResult]
    ) -> List[SuperMetric]:
        """
        Generate overall feedback by picking contributing section feedbacks.
        
        This reuses the contributing section logic but works with existing section feedbacks
        instead of generating new ones.
        
        Args:
            all_super_metrics: All super-metrics from all sections
            section_results: Section evaluation results
            
        Returns:
            List[SuperMetric]: Super-metrics with overall feedback
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.generate_overall_feedback_from_sections.start",
            {
                "all_super_metrics_count": len(all_super_metrics),
                "section_results_count": len(section_results)
            }
        )
        
        # Group super-metrics by type
        super_metrics_by_type = defaultdict(list)
        for super_metric in all_super_metrics:
            super_metrics_by_type[super_metric.metadata.super_metric_type].append(super_metric)
        
        # For each super-metric type, pick the best feedback from contributing sections
        overall_super_metrics = []
        
        for super_metric_type, type_super_metrics in super_metrics_by_type.items():
            best_super_metric = max(type_super_metrics, key=lambda sm: sm.score.numeric_score)
            worst_super_metric = min(type_super_metrics, key=lambda sm: sm.score.numeric_score)

            # 如果存在明显的负面表现（Poor），优先保留这段的反馈，避免重要警告被淹没
            if worst_super_metric.score.score_label == ScoreLabel.POOR:
                chosen_super_metric = worst_super_metric
            else:
                chosen_super_metric = best_super_metric
            
            overall_super_metrics.append(chosen_super_metric)
        
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationUseCaseImpl.generate_overall_feedback_from_sections.end",
            {
                "overall_super_metrics_count": len(overall_super_metrics)
            }
        )
        
        return overall_super_metrics