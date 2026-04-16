"""
Two-Phase Evaluation API interface and implementation.

This module provides the public API for the two-phase evaluation service, which separates
section-level evaluation from overall evaluation for better performance and flexibility.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pathlib import Path
from uuid import UUID

import logging.handlers

from ..business.entities import EvaluationRecord, EvaluationStrategy, DialogSection
from ..business.value_objects import RawDialogInfo, SectionEvaluationResult
from ..business.enums import StrategyId

# Use Case
from ..use_cases.two_phase_evaluation_use_case import TwoPhaseEvaluationUseCaseImpl

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
from ..services.feedback_services.simple_section_feedback_service_builder import (
    DefaultSimpleSectionFeedbackServiceBuilder
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


class TwoPhaseEvaluationAPI(ABC):
    """
    Public API interface for two-phase evaluation operations.
    
    This interface provides a simplified way to evaluate dialogs using a two-phase approach:
    Phase 1: Evaluate individual sections with scores and feedback
    Phase 2: Generate overall evaluation from section results
    """

    @abstractmethod
    async def evaluate_full_workflow(self, raw_dialog_info: RawDialogInfo) -> EvaluationRecord:
        """
        Execute the complete two-phase evaluation workflow.
        
        This method combines both phases:
        1. Build dialog sections from raw dialog info
        2. Evaluate each section individually (Phase 1)
        3. Generate overall evaluation from section results (Phase 2)
        
        Args:
            raw_dialog_info: The raw dialog information to evaluate
            
        Returns:
            EvaluationRecord: The completed evaluation record
        """
        raise NotImplementedError

    @abstractmethod
    async def evaluate_section(
        self, 
        section: DialogSection, 
        user_id: Optional[UUID] = None,
        cached_feedback: Optional[Dict[str, Any]] = None
    ) -> SectionEvaluationResult:
        """
        Phase 1: Evaluate a single dialog section.
        
        Args:
            section: The dialog section to evaluate
            user_id: Optional user ID for querying previous scores
            cached_feedback: Optional cached feedback from unified evaluation
            
        Returns:
            SectionEvaluationResult: Evaluation result for the section
        """
        raise NotImplementedError

    @abstractmethod
    async def evaluate_overall(self, section_results: List[SectionEvaluationResult]) -> EvaluationRecord:
        """
        Phase 2: Generate overall evaluation from section results.
        
        Args:
            section_results: List of section evaluation results from Phase 1
            
        Returns:
            EvaluationRecord: The completed overall evaluation record
        """
        raise NotImplementedError

    @abstractmethod
    async def build_sections(self, raw_dialog_info: RawDialogInfo) -> List[DialogSection]:
        """
        Build dialog sections from raw dialog information.
        
        Args:
            raw_dialog_info: The raw dialog information
            
        Returns:
            List[DialogSection]: List of dialog sections
        """
        raise NotImplementedError


def get_two_phase_evaluation_api() -> TwoPhaseEvaluationAPI:
    """
    Factory function to get an instance of the TwoPhaseEvaluationAPI implementation.
    
    Returns:
        TwoPhaseEvaluationAPI: An instance of the TwoPhaseEvaluationAPI implementation
    """
    return TwoPhaseEvaluationAPIImpl()


class TwoPhaseEvaluationAPIImpl(TwoPhaseEvaluationAPI):
    """
    Implementation of the TwoPhaseEvaluationAPI.
    
    This class manages all the dependencies required by the two-phase evaluation use case
    and provides a simple interface for external modules to use.
    """

    def __init__(
        self,
        evaluation_strategies_file_path: Optional[str] = None,
        default_strategy_id: Optional[str] = None,
    ):
        """
        Initialize the TwoPhaseEvaluationAPI implementation.
        
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
        self._default_strategy_id = default_strategy_id
        
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
        self._simple_section_feedback_service_builder: DefaultSimpleSectionFeedbackServiceBuilder
        self._two_phase_evaluation_use_case: TwoPhaseEvaluationUseCaseImpl
        
        # Initialize dependencies
        self._setup_dependencies()

    def _setup_dependencies(self) -> None:
        """
        Set up all dependencies required by the two-phase evaluation use case.
        
        This method creates and configures all repositories, services, and ID generators
        based on the pattern used in the single-phase evaluation API.
        """
        self._logger.info("evaluation.TwoPhaseEvaluationAPIImpl.setup_dependencies.start")
        
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
        
        self._simple_section_feedback_service_builder = DefaultSimpleSectionFeedbackServiceBuilder(
            logger=self._logger,
            dialog_section_repo=self._dialog_section_repo,
            model=non_visual_model
        )
        
        # Create the two-phase evaluation use case with default strategy
        default_strategy_id = self._get_default_strategy_id()
        self._two_phase_evaluation_use_case = TwoPhaseEvaluationUseCaseImpl(
            strategy_id=default_strategy_id,
            dialog_section_repo=self._dialog_section_repo,
            metric_repo=self._metric_repo,
            evaluation_record_repo=self._evaluation_record_repo,
            evaluation_strategy_repo=self._evaluation_strategy_repo,
            dialog_section_builder=self._dialog_section_builder,
            metric_calc_service_builder=self._metric_calc_service_builder,
            super_metric_calc_service_builder=self._super_metric_calc_service_builder,
            evaluation_calc_service_builder=self._evaluation_calc_service_builder,
            simple_section_feedback_service_builder=self._simple_section_feedback_service_builder,
            dialog_section_id_generator=self._dialog_section_id_generator,
            metric_id_generator=self._metric_id_generator,
            evaluation_record_id_generator=self._evaluation_record_id_generator,
            logger=self._logger
        )
        
        self._logger.info("evaluation.TwoPhaseEvaluationAPIImpl.setup_dependencies.end")

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

    async def evaluate_full_workflow(self, raw_dialog_info: RawDialogInfo) -> EvaluationRecord:
        """
        Execute the complete two-phase evaluation workflow.
        
        This is the main entry point that combines both phases:
        1. Build dialog sections from raw dialog info
        2. Evaluate each section individually (Phase 1)
        3. Generate overall evaluation from section results (Phase 2)
        
        Args:
            raw_dialog_info: The raw dialog information to evaluate
            
        Returns:
            EvaluationRecord: The completed evaluation record
        """
        self._logger.info(
            "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_full_workflow.start",
            {
                "dialog_id": raw_dialog_info.dialog_id,
                "message_count": len(raw_dialog_info.messages)
            }
        )
        
        try:
            # Step 1: Build dialog sections
            dialog_sections = await self.build_sections(raw_dialog_info)
            
            # Step 2: Evaluate each section (Phase 1)
            section_results = []
            for section in dialog_sections:
                section_result = await self.evaluate_section(section)
                section_results.append(section_result)
            
            # Step 3: Generate overall evaluation (Phase 2)
            evaluation_record = await self.evaluate_overall(section_results)
            
            self._logger.info(
                "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_full_workflow.end",
                {
                    "dialog_id": raw_dialog_info.dialog_id,
                    "sections_count": len(dialog_sections),
                    "evaluation_record_id": evaluation_record.id,
                    "overall_score": evaluation_record.overall_score.numeric_score
                }
            )
            
            return evaluation_record
            
        except Exception as e:
            self._logger.error(
                "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_full_workflow.error",
                e,
                {
                    "dialog_id": raw_dialog_info.dialog_id,
                    "error": str(e)
                }
            )
            raise

    async def evaluate_section(
        self, 
        section: DialogSection, 
        user_id: Optional[UUID] = None,
        cached_feedback: Optional[Dict[str, Any]] = None
    ) -> SectionEvaluationResult:
        """
        Phase 1: Evaluate a single dialog section.
        
        Args:
            section: The dialog section to evaluate
            user_id: Optional user ID for querying previous scores for comparison
            cached_feedback: Optional cached feedback from unified evaluation
            
        Returns:
            SectionEvaluationResult: Evaluation result for the section
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_section.start",
            {
                "section": section.model_dump(),
                "user_id": str(user_id) if user_id else "N/A",
                "has_cached_feedback": bool(cached_feedback)
            }
        )
        
        try:
            result = await self._two_phase_evaluation_use_case.evaluate_section(
                section, 
                user_id=user_id,
                cached_feedback=cached_feedback
            )
            
            self._logger.debug(
                "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_section.end",
                {
                    "section": section.model_dump(),
                    "result": result.model_dump(),
                }
            )
            
            return result
            
        except Exception as e:
            self._logger.error(
                "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_section.error",
                e,
                {
                    "section": section.model_dump(),
                    "error": str(e)
                }
            )
            raise

    async def evaluate_overall(self, section_results: List[SectionEvaluationResult]) -> EvaluationRecord:
        """
        Phase 2: Generate overall evaluation from section results.
        
        Args:
            section_results: List of section evaluation results from Phase 1
            
        Returns:
            EvaluationRecord: The completed overall evaluation record
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_overall.start",
            {
                "section_results": [section.model_dump() for section in section_results],
            }
        )
        
        try:
            result = await self._two_phase_evaluation_use_case.evaluate_overall(section_results)
            
            self._logger.debug(
                "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_overall.end",
                {
                    "section_results": [section.model_dump() for section in section_results],
                    "result": result.model_dump(),
                }
            )
            
            return result
            
        except Exception as e:
            self._logger.error(
                "evaluation.TwoPhaseEvaluationAPIImpl.evaluate_overall.error",
                e,
                {
                    "section_results": [section.model_dump() for section in section_results],
                    "error": str(e)
                }
            )
            raise

    async def build_sections(self, raw_dialog_info: RawDialogInfo) -> List[DialogSection]:
        """
        Build dialog sections from raw dialog information.
        
        Args:
            raw_dialog_info: The raw dialog information
            
        Returns:
            List[DialogSection]: List of dialog sections
        """
        self._logger.debug(
            "evaluation.TwoPhaseEvaluationAPIImpl.build_sections.start",
            {
                "dialog_id": raw_dialog_info.dialog_id,
                "message_count": len(raw_dialog_info.messages)
            }
        )
        
        try:
            dialog_sections = self._dialog_section_builder.build_dialog_sections(raw_dialog_info)
            
            # Save dialog sections to repository
            for section in dialog_sections:
                self._dialog_section_repo.save(section)
            
            self._logger.debug(
                "evaluation.TwoPhaseEvaluationAPIImpl.build_sections.end",
                {
                    "dialog_id": raw_dialog_info.dialog_id,
                    "sections_count": len(dialog_sections)
                }
            )
            
            return dialog_sections
            
        except Exception as e:
            self._logger.error(
                "evaluation.TwoPhaseEvaluationAPIImpl.build_sections.error",
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
        # Use caller-provided strategy id first (for specific flows like streaming),
        # otherwise fallback to legacy default.
        default_strategy_id = self._default_strategy_id or "strategy_1"
        
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
        self._logger.info("evaluation.TwoPhaseEvaluationAPIImpl.reset_repositories")
        
        # Clear all in-memory repositories
        self._dialog_section_repo = InMemoryDialogSectionRepo()
        self._metric_repo = InMemoryMetricRepo()
        self._evaluation_record_repo = InMemoryEvaluationRecordRepo()
        
        # Update service builders with the new repositories
        self._super_metric_feedback_service_builder = DefaultSuperMetricFeedbackServiceBuilder(
            logger=self._logger,
            dialog_section_repo=self._dialog_section_repo
        )
        
        self._simple_section_feedback_service_builder = DefaultSimpleSectionFeedbackServiceBuilder(
            logger=self._logger,
            dialog_section_repo=self._dialog_section_repo
        )
        
        # Recreate the use case with updated repositories
        default_strategy_id = self._get_default_strategy_id()
        self._two_phase_evaluation_use_case = TwoPhaseEvaluationUseCaseImpl(
            strategy_id=default_strategy_id,
            dialog_section_repo=self._dialog_section_repo,
            metric_repo=self._metric_repo,
            evaluation_record_repo=self._evaluation_record_repo,
            evaluation_strategy_repo=self._evaluation_strategy_repo,
            dialog_section_builder=self._dialog_section_builder,
            metric_calc_service_builder=self._metric_calc_service_builder,
            super_metric_calc_service_builder=self._super_metric_calc_service_builder,
            evaluation_calc_service_builder=self._evaluation_calc_service_builder,
            simple_section_feedback_service_builder=self._simple_section_feedback_service_builder,
            dialog_section_id_generator=self._dialog_section_id_generator,
            metric_id_generator=self._metric_id_generator,
            evaluation_record_id_generator=self._evaluation_record_id_generator,
            logger=self._logger
        )