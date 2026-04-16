"""
Default super-metric feedback service builder implementation.
"""
from app.services.evaluation.business import (
    SuperMetricFeedbackService,
    EvaluationStrategy,
    DialogSectionRepo,
    Logger,
    StrategyId,
)
from app.services.evaluation.business.services import SuperMetricFeedbackServiceBuilder
from .default_super_metric_feedback_service import DefaultSuperMetricFeedbackService
from .verbal_visual_super_metric_feedback_adapter_service import VerbalVisualSuperMetricFeedbackAdapterService
from .brief_lookup_super_metric_feedback_service import BriefLookupSuperMetricFeedbackService


class DefaultSuperMetricFeedbackServiceBuilder(SuperMetricFeedbackServiceBuilder):
    """
    Default implementation of SuperMetricFeedbackServiceBuilder.
    
    This builder creates DefaultSuperMetricFeedbackService instances configured
    with the necessary dependencies.
    """
    
    def __init__(
        self,
        logger: Logger,
        dialog_section_repo: DialogSectionRepo,
        model: str = "gpt-4o"
    ):
        """
        Initialize the default super-metric feedback service builder.
        
        Args:
            logger: Logger service for logging operations
            dialog_section_repo: Repository for retrieving dialog sections
            model: LLM model to use for feedback generation (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
        """
        self._logger = logger
        self._dialog_section_repo = dialog_section_repo
        self._model = model
    
    def build(self, strategy: EvaluationStrategy) -> SuperMetricFeedbackService:
        """
        Build SuperMetricFeedbackService based on EvaluationStrategy.
        
        The strategy can be used to customize the feedback service behavior
        in the future (e.g., different models, prompts, or configurations).
        
        Args:
            strategy: The evaluation strategy to use for configuration
            
        Returns:
            SuperMetricFeedbackService: Configured feedback service instance
        """
        self._logger.debug(
            "Building SuperMetricFeedbackService",
            {
                "strategy_id": strategy.strategy_id,
                "strategy_name": strategy.name,
                "model": self._model,
                "service": "DefaultSuperMetricFeedbackServiceBuilder"
            }
        )
        
        # For now, we use the same configuration for all strategies
        # In the future, we could customize based on strategy properties
        service: SuperMetricFeedbackService
        if strategy.strategy_id == StrategyId.STRATEGY_1.value:
            service = DefaultSuperMetricFeedbackService(
                logger=self._logger,
                dialog_section_repo=self._dialog_section_repo,
                model=self._model
            )
        elif strategy.strategy_id == StrategyId.STRATEGY_BRIEF_LOOKUP.value:
            service = BriefLookupSuperMetricFeedbackService(
                logger=self._logger,
                dialog_section_repo=self._dialog_section_repo
            )
        else:
            raise ValueError(f"Unsupported strategy ID: {strategy.strategy_id}")
        
        self._logger.debug(
            "Successfully built SuperMetricFeedbackService",
            {
                "strategy_id": strategy.strategy_id,
                "service": "DefaultSuperMetricFeedbackServiceBuilder"
            }
        )
        
        return service