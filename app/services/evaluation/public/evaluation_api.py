"""
Evaluation API interface and implementation.

This module provides the public API for the evaluation service, encapsulating
all the complexity of use case setup and dependency management.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from pathlib import Path
import logging.handlers

from ..business.entities import EvaluationRecord, EvaluationStrategy
from ..business.value_objects import RawDialogInfo
from ..business.enums import StrategyId

# Use Case
from ..use_cases.evaluation_use_case import EvaluationUseCaseImpl

# Repositories  
from ..repositories import (
    InMemoryDialogSectionRepo, InMemoryMetricRepo, InMemoryEvaluationRecordRepo,
    JsonFileEvaluationStrategyRepo
)

# Services
from ..services.dialog_section_builders.default_dialog_section_builder import (
    DefaultDialogSectionBuilder
)
from ..services.evaluation_calc_services.metric.default_metric_calc_service_builder import (
    DefaultMetricCalcServiceBuilder
)
from ..services.evaluation_calc_services.super_metric.default_super_metric_calc_service_builder import (
    DefaultSuperMetricCalcServiceBuilder
)
from ..services.feedback_services import (
    DefaultSuperMetricFeedbackServiceBuilder
)
from ..services.id_generators import (
    SnowflakeDialogSectionIDGenerator, SnowflakeMetricIDGenerator, SnowflakeEvaluationRecordIDGenerator
)
from ..services.evaluation_calc_services import (
    DefaultEvaluationCalcServiceBuilder,
)
from ..services.score_transformation_service import (
    DefaultScoreTransformationService
)

# Logger
from ..loggers.simple_logger import SimpleLogger


class EvaluationAPI(ABC):
    """
    Public API interface for evaluation operations.
    
    This interface provides a simplified way to evaluate dialog information
    without needing to understand the internal complexity of the evaluation system.
    """

    @abstractmethod
    async def evaluate(self, raw_dialog_info: RawDialogInfo) -> EvaluationRecord:
        """
        Evaluate a raw dialog and return the evaluation record.
        
        Args:
            raw_dialog_info: The raw dialog information to evaluate
            
        Returns:
            EvaluationRecord: The completed evaluation record
            
        Raises:
            ValueError: If no strategies are available or use case is not properly initialized
            Exception: If evaluation fails
        """
        raise NotImplementedError

def get_evaluation_api() -> EvaluationAPI:
    """
    Factory function to get an instance of the EvaluationAPI implementation.
    
    Returns:
        EvaluationAPI: An instance of the EvaluationAPI implementation
    """
    return EvaluationAPIImpl()

class EvaluationAPIImpl(EvaluationAPI):
    """
    Implementation of the EvaluationAPI.
    
    This class manages all the dependencies required by the evaluation use case
    and provides a simple interface for external modules to use.
    """

    def __init__(
        self, 
        evaluation_strategies_file_path: Optional[str] = None
    ):
        """
        Initialize the EvaluationAPI implementation.
        
        Args:
            evaluation_strategies_file_path: Path to evaluation strategies JSON file.
                                           If not provided, uses default path.
        """
        self._logger = SimpleLogger()
        self._setup_litellm_logging()
        
        # Set default strategies file path if not provided
        if evaluation_strategies_file_path is None:
            current_dir = Path(__file__).parent
            # Navigate from public -> evaluation -> config
            config_dir = current_dir.parent.parent.parent / "config"
            evaluation_strategies_file_path = str(config_dir / "evaluation_strategies.json")
        
        self._evaluation_strategies_file_path = evaluation_strategies_file_path
        
        # Attributes will be set in _setup_dependencies - declared here for type checking
        self._dialog_section_id_generator: SnowflakeDialogSectionIDGenerator
        self._metric_id_generator: SnowflakeMetricIDGenerator  
        self._evaluation_record_id_generator: SnowflakeEvaluationRecordIDGenerator
        self._dialog_section_repo: InMemoryDialogSectionRepo
        self._metric_repo: InMemoryMetricRepo
        self._evaluation_record_repo: InMemoryEvaluationRecordRepo
        self._evaluation_strategy_repo: JsonFileEvaluationStrategyRepo
        self._dialog_section_builder: DefaultDialogSectionBuilder
        self._metric_calc_service_builder: DefaultMetricCalcServiceBuilder
        self._super_metric_calc_service_builder: DefaultSuperMetricCalcServiceBuilder
        self._evaluation_calc_service_builder: DefaultEvaluationCalcServiceBuilder
        self._super_metric_feedback_service_builder: DefaultSuperMetricFeedbackServiceBuilder
        self._score_transformation_service: DefaultScoreTransformationService
        self._evaluation_use_case: EvaluationUseCaseImpl
        
        # Initialize dependencies
        self._setup_dependencies()

    def _setup_dependencies(self) -> None:
        """
        Set up all dependencies required by the evaluation use case.
        
        This method creates and configures all repositories, services, and ID generators
        based on the pattern used in the integration test.
        """
        self._logger.info("evaluation.EvaluationAPIImpl.setup_dependencies.start")
        
        # Create ID generators
        self._dialog_section_id_generator = SnowflakeDialogSectionIDGenerator()
        self._metric_id_generator = SnowflakeMetricIDGenerator()
        self._evaluation_record_id_generator = SnowflakeEvaluationRecordIDGenerator()
        
        # Create core services
        self._score_transformation_service = DefaultScoreTransformationService(self._logger)
        
        # Create repositories
        self._dialog_section_repo = InMemoryDialogSectionRepo()
        self._metric_repo = InMemoryMetricRepo()
        self._evaluation_record_repo = InMemoryEvaluationRecordRepo()
        self._evaluation_strategy_repo = JsonFileEvaluationStrategyRepo(
            self._evaluation_strategies_file_path
        )
        
        # Create service implementations
        self._dialog_section_builder = DefaultDialogSectionBuilder(
            dialog_section_id_generator=self._dialog_section_id_generator,
            logger=self._logger
        )
        
        self._metric_calc_service_builder = DefaultMetricCalcServiceBuilder(
            logger=self._logger,
            id_generator=self._metric_id_generator,
            score_transformation_service=self._score_transformation_service
        )
        
        self._super_metric_calc_service_builder = DefaultSuperMetricCalcServiceBuilder(
            logger=self._logger,
            score_transformation_service=self._score_transformation_service
        )
        
        self._evaluation_calc_service_builder = DefaultEvaluationCalcServiceBuilder(
            logger=self._logger,
            score_transformation_service=self._score_transformation_service
        )
        
        # Get non-visual model configuration
        from app.core.llm_factory import llm_factory
        from app.core.config import settings
        import os
        
        # Get config to set up environment for litellm
        config = llm_factory.get_non_visual_config()
        if config["provider"] == "deepseek" and settings.DEEPSEEK_API_KEY:
             os.environ["DEEPSEEK_API_KEY"] = settings.DEEPSEEK_API_KEY
        
        # Use model from factory
        _, non_visual_model = llm_factory.get_non_visual_client()

        self._super_metric_feedback_service_builder = DefaultSuperMetricFeedbackServiceBuilder(
            logger=self._logger,
            dialog_section_repo=self._dialog_section_repo,
            model=non_visual_model
        )
        
        # Create the evaluation use case with default strategy
        default_strategy_id = self._get_default_strategy_id()
        self._evaluation_use_case = EvaluationUseCaseImpl(
            strategy_id=default_strategy_id,
            dialog_section_repo=self._dialog_section_repo,
            metric_repo=self._metric_repo,
            evaluation_record_repo=self._evaluation_record_repo,
            evaluation_strategy_repo=self._evaluation_strategy_repo,
            dialog_section_builder=self._dialog_section_builder,
            metric_calc_service_builder=self._metric_calc_service_builder,
            super_metric_calc_service_builder=self._super_metric_calc_service_builder,
            evaluation_calc_service_builder=self._evaluation_calc_service_builder,
            super_metric_feedback_service_builder=self._super_metric_feedback_service_builder,
            dialog_section_id_generator=self._dialog_section_id_generator,
            metric_id_generator=self._metric_id_generator,
            evaluation_record_id_generator=self._evaluation_record_id_generator,
            logger=self._logger
        )
        
        self._logger.info("evaluation.EvaluationAPIImpl.setup_dependencies.end")

    def _setup_litellm_logging(self) -> None:
        logger = logging.getLogger("LiteLLM")
        # Set to WARNING to reduce console output (DEBUG logs are too verbose)
        logger.setLevel(logging.WARNING)
        # Use delay=True to avoid file locking issues on Windows with multiple processes
        handler = logging.handlers.TimedRotatingFileHandler(
                filename="logs/litellm.log",
                when='midnight',
                interval=1,
                backupCount=30,
                encoding='utf-8',
                delay=True  # Delay file opening until first write
            )
        handler.setLevel(logging.DEBUG)  # File handler still captures DEBUG logs
        logger.addHandler(handler)
        # Prevent propagation to root logger to avoid console output
        logger.propagate = False

    async def evaluate(self, raw_dialog_info: RawDialogInfo) -> EvaluationRecord:
        """
        Evaluate a raw dialog and return the evaluation record.
        
        Args:
            raw_dialog_info: The raw dialog information to evaluate
            
        Returns:
            EvaluationRecord: The completed evaluation record
            
        Raises:
            ValueError: If no strategies are available or use case is not properly initialized
            Exception: If evaluation fails
        """
        self._logger.info(
            "evaluation.EvaluationAPIImpl.evaluate.start",
            {
                "dialog_id": raw_dialog_info.dialog_id,
                "message_count": len(raw_dialog_info.messages)
            }
        )
        
        try:
            # Execute evaluation using the pre-initialized use case
            evaluation_record = await self._evaluation_use_case.execute(raw_dialog_info)
            
            self._logger.info(
                "evaluation.EvaluationAPIImpl.evaluate.end",
                {
                    "dialog_id": raw_dialog_info.dialog_id,
                    "evaluation_record_id": evaluation_record.id,
                    "overall_score": evaluation_record.overall_score.numeric_score
                }
            )
            
            return evaluation_record
            
        except Exception as e:
            self._logger.error(
                "evaluation.EvaluationAPIImpl.evaluate.error",
                e,
                {
                    "dialog_id": raw_dialog_info.dialog_id,
                    "error": str(e)
                }
            )
            raise

    def _get_default_strategy_id(self) -> str:
        """
        Get the default strategy ID ("strategy_1").
        
        Returns:
            str: The default strategy ID "strategy_1"
            
        Raises:
            ValueError: If "strategy_1" is not available
        """
        # Use "strategy_1" as the default strategy (LLM-based feedback generation)
        default_strategy_id = StrategyId.STRATEGY_1.value
        
        # Verify that the default strategy exists
        strategy = self._evaluation_strategy_repo.get_by_id(default_strategy_id)
        if strategy is None:
            raise ValueError(f"Default strategy '{default_strategy_id}' not found in available strategies")
        
        return default_strategy_id

    def get_available_strategies(self) -> List[EvaluationStrategy]:
        """
        Get list of available evaluation strategies.
        
        Returns:
            List[EvaluationStrategy]: List of available evaluation strategies
        """
        return self._evaluation_strategy_repo.get_all()

    def reset_repositories(self) -> None:
        """
        Reset all in-memory repositories to clean state.
        
        This is useful for testing or when you want to start fresh
        without creating a new API instance.
        """
        self._logger.info("evaluation.EvaluationAPIImpl.reset_repositories")
        
        # Clear all in-memory repositories
        self._dialog_section_repo = InMemoryDialogSectionRepo()
        self._metric_repo = InMemoryMetricRepo()
        self._evaluation_record_repo = InMemoryEvaluationRecordRepo()
        
        # Update service builders with the new repositories
        self._super_metric_feedback_service_builder = DefaultSuperMetricFeedbackServiceBuilder(
            logger=self._logger,
            dialog_section_repo=self._dialog_section_repo
        )
        
        # Recreate service builders with score transformation service
        self._metric_calc_service_builder = DefaultMetricCalcServiceBuilder(
            logger=self._logger,
            id_generator=self._metric_id_generator,
            score_transformation_service=self._score_transformation_service
        )
        
        self._super_metric_calc_service_builder = DefaultSuperMetricCalcServiceBuilder(
            logger=self._logger,
            score_transformation_service=self._score_transformation_service
        )
        
        self._evaluation_calc_service_builder = DefaultEvaluationCalcServiceBuilder(
            logger=self._logger,
            score_transformation_service=self._score_transformation_service
        )
        
        # Recreate the use case with updated repositories
        default_strategy_id = self._get_default_strategy_id()
        self._evaluation_use_case = EvaluationUseCaseImpl(
            strategy_id=default_strategy_id,
            dialog_section_repo=self._dialog_section_repo,
            metric_repo=self._metric_repo,
            evaluation_record_repo=self._evaluation_record_repo,
            evaluation_strategy_repo=self._evaluation_strategy_repo,
            dialog_section_builder=self._dialog_section_builder,
            metric_calc_service_builder=self._metric_calc_service_builder,
            super_metric_calc_service_builder=self._super_metric_calc_service_builder,
            evaluation_calc_service_builder=self._evaluation_calc_service_builder,
            super_metric_feedback_service_builder=self._super_metric_feedback_service_builder,
            dialog_section_id_generator=self._dialog_section_id_generator,
            metric_id_generator=self._metric_id_generator,
            evaluation_record_id_generator=self._evaluation_record_id_generator,
            logger=self._logger
        )