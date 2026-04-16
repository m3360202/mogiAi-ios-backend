"""
Simple section feedback service builder implementation.
"""
from app.services.evaluation.business import (
    EvaluationStrategy,
    DialogSectionRepo,
    Logger,
)
from app.services.evaluation.business.services import (
    SimpleSectionFeedbackService, SimpleSectionFeedbackServiceBuilder
)
from .simple_section_feedback_service import SimpleSectionFeedbackServiceImpl


class DefaultSimpleSectionFeedbackServiceBuilder(SimpleSectionFeedbackServiceBuilder):
    """
    Default implementation of SimpleSectionFeedbackServiceBuilder.
    
    This builder creates SimpleSectionFeedbackServiceImpl instances configured
    with the necessary dependencies.
    """
    
    def __init__(
        self,
        logger: Logger,
        dialog_section_repo: DialogSectionRepo,
        model: str = "gpt-4o"
    ):
        """
        Initialize the simple section feedback service builder.
        
        Args:
            logger: Logger service for logging operations
            dialog_section_repo: Repository for retrieving dialog sections
            model: LLM model to use for feedback generation (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
        """
        self._logger = logger
        self._dialog_section_repo = dialog_section_repo
        self._model = model
    
    def build(self, strategy: EvaluationStrategy) -> SimpleSectionFeedbackService:
        """
        Build SimpleSectionFeedbackService based on EvaluationStrategy.
        
        The strategy can be used to customize the feedback service behavior
        in the future (e.g., different models, prompts, or configurations).
        
        Args:
            strategy: The evaluation strategy to use for configuration
            
        Returns:
            SimpleSectionFeedbackService: A configured simple section feedback service
        """
        self._logger.debug(
            "evaluation.DefaultSimpleSectionFeedbackServiceBuilder.build.start",
            {"strategy_id": strategy.strategy_id, "model": self._model}
        )
        
        # Create the simple section feedback service
        service = SimpleSectionFeedbackServiceImpl(
            logger=self._logger,
            dialog_section_repo=self._dialog_section_repo,
            model=self._model
        )

        self._logger.debug(
            "evaluation.DefaultSimpleSectionFeedbackServiceBuilder.build.end",
            {"strategy_id": strategy.strategy_id, "service_type": type(service).__name__}
        )
        
        return service