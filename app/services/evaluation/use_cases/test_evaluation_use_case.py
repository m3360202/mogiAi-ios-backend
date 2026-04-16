"""
Tests for the evaluation use cases.
"""
import pytest
from unittest.mock import Mock
from datetime import datetime

from .evaluation_use_case import EvaluationUseCase, EvaluationUseCaseImpl
from ..business.entities import DialogSection, Metric, EvaluationRecord, EvaluationStrategy
from ..business.value_objects import (
    RawDialogInfo, DialogMessage, SuperMetric, Score,
    MetricMetadata, SuperMetricMetadata, MetricGroup
)
from ..business.enums import MessageRole, ScoreLabel, MetricType, SuperMetricType


class TestEvaluationUseCase:
    """Test suite for EvaluationUseCase implementation."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock repositories
        self.dialog_section_repo = Mock()
        self.metric_repo = Mock()
        self.evaluation_record_repo = Mock()
        self.evaluation_strategy_repo = Mock()
        
        # Create mock services
        self.dialog_section_builder = Mock()
        
        # Create mock service builders
        self.metric_calc_service_builder = Mock()
        self.super_metric_calc_service_builder = Mock()
        self.evaluation_calc_service_builder = Mock()
        
        # Create mock ID generators
        self.dialog_section_id_generator = Mock()
        self.metric_id_generator = Mock()
        self.evaluation_record_id_generator = Mock()
        
        # Create mock logger
        self.logger = Mock()
        
        # Set up ID generation
        self.dialog_section_id_generator.generate.side_effect = ["ds1", "ds2", "ds3"]
        self.metric_id_generator.generate.side_effect = ["m1", "m2", "m3", "m4"]
        self.evaluation_record_id_generator.generate.return_value = "eval1"
        
        # Create the use case implementation
        self.use_case = EvaluationUseCaseImpl(
            dialog_section_repo=self.dialog_section_repo,
            metric_repo=self.metric_repo,
            evaluation_record_repo=self.evaluation_record_repo,
            evaluation_strategy_repo=self.evaluation_strategy_repo,
            dialog_section_builder=self.dialog_section_builder,
            metric_calc_service_builder=self.metric_calc_service_builder,
            super_metric_calc_service_builder=self.super_metric_calc_service_builder,
            evaluation_calc_service_builder=self.evaluation_calc_service_builder,
            dialog_section_id_generator=self.dialog_section_id_generator,
            metric_id_generator=self.metric_id_generator,
            evaluation_record_id_generator=self.evaluation_record_id_generator,
            logger=self.logger
        )
    
    def test_interface_definition(self) -> None:
        """Test that EvaluationUseCase is properly defined as an interface."""
        # Test that it's an abstract base class
        with pytest.raises(TypeError):
            EvaluationUseCase()  # Should not be instantiable
        
        # Test that execute method is abstract
        assert hasattr(EvaluationUseCase, 'execute')
        assert getattr(EvaluationUseCase.execute, '__isabstractmethod__', False)
    
    def test_execute_full_workflow(self) -> None:
        """Test the complete evaluation workflow."""
        # Create test data
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",  # Will be updated
                    role=MessageRole.INTERVIEWER,
                    content="Tell me about yourself",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                ),
                DialogMessage(
                    section_id="",  # Will be updated
                    role=MessageRole.CANDIDATE,
                    content="I am a software engineer",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
            ]
        )
        
        # Create test strategy
        strategy = EvaluationStrategy(
            strategy_id="strategy1",
            name="Test Strategy",
            description="Test evaluation strategy",
            super_metric_metadata_list=[
                SuperMetricMetadata(
                    super_metric_type=SuperMetricType.CLARITY,
                    metric_metadata_list=[
                        MetricMetadata(metric_type=MetricType.CONCISENESS)
                    ]
                )
            ]
        )
        
        # Set up mock responses
        self.evaluation_strategy_repo.get_by_id.return_value = strategy
        
        # Mock dialog section builder to return sample dialog sections
        mock_dialog_sections = [
            DialogSection(
                id="ds1",
                dialog_id="test_dialog",
                section_index=0,
                messages=[
                    DialogMessage(
                        section_id="ds1",
                        role=MessageRole.INTERVIEWER,
                        content="Tell me about yourself",
                        start_time=datetime.now(),
                        end_time=datetime.now()
                    ),
                    DialogMessage(
                        section_id="ds1",
                        role=MessageRole.CANDIDATE,
                        content="I am a software engineer",
                        start_time=datetime.now(),
                        end_time=datetime.now()
                    )
                ],
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ]
        self.dialog_section_builder.build_dialog_sections.return_value = mock_dialog_sections
        
        # Mock calculation services
        mock_metric_service = Mock()
        mock_score = Score(score_label=ScoreLabel.GOOD, numeric_score=85.0)
        
        # Mock the new create_metric_group method that returns a complete MetricGroup
        mock_metric = Metric(
            id="test_metric_1",
            metadata=MetricMetadata(metric_type=MetricType.CONCISENESS),
            dialog_section_id="ds1",
            dialog_section_index=1,
            sub_metrics={
                "is_core_idea_presented": True,
                "core_idea": "I am a software engineer",
                "filter_words": ["basically"],
                "strong_words": ["engineer"],
                "sentence_count": 1,
                "filter_words_count": 1,
                "strong_words_count": 1,
                "filter_words_frequency": 1.0,
                "strong_words_frequency": 1.0
            },
            score=mock_score,
            revision="Great answer!"
        )
        mock_metric_group = MetricGroup(
            metric_type=MetricType.CONCISENESS,
            metrics=[mock_metric]
        )
        mock_metric_service.create_metric_group.return_value = mock_metric_group
        
        self.metric_calc_service_builder.build.return_value = mock_metric_service
        
        mock_super_metric_service = Mock()
        
        # Mock the new create_super_metric method that returns a complete SuperMetric
        mock_super_metric = SuperMetric(
            metadata=SuperMetricMetadata(
                super_metric_type=SuperMetricType.CLARITY,
                metric_metadata_list=[MetricMetadata(metric_type=MetricType.CONCISENESS)]
            ),
            metric_groups=[],  # Will be populated by use case
            score=mock_score,
            feedback="Clear communication"
        )
        mock_super_metric_service.create_super_metric.return_value = mock_super_metric
        
        self.super_metric_calc_service_builder.build.return_value = mock_super_metric_service
        
        mock_evaluation_service = Mock()
        mock_overall_score = Score(score_label=ScoreLabel.GOOD, numeric_score=88.0)
        mock_evaluation_service.calculate_score.return_value = mock_overall_score
        
        self.evaluation_calc_service_builder.build.return_value = mock_evaluation_service
        
        # Execute the use case
        result = self.use_case.execute(raw_dialog_info, "strategy1")
        
        # Verify the result
        assert isinstance(result, EvaluationRecord)
        assert result.id == "eval1"
        assert result.strategy == strategy
        assert result.interview_record_id == "test_dialog"
        assert len(result.super_metrics) == 1
        assert result.overall_score == mock_overall_score
        
        # Verify repositories were called
        self.dialog_section_builder.build_dialog_sections.assert_called_once_with(raw_dialog_info)
        self.dialog_section_repo.save.assert_called()  # Should be called to persist dialog sections
        self.metric_repo.save.assert_called()
        self.evaluation_record_repo.save.assert_called_once_with(result)
        self.evaluation_strategy_repo.get_by_id.assert_called_once_with("strategy1")
        
        # Verify logging
        assert self.logger.info.called
        assert self.logger.debug.called
    
    def test_strategy_not_found(self) -> None:
        """Test error handling when strategy is not found."""
        # Set up mock to return None
        self.evaluation_strategy_repo.get_by_id.return_value = None
        
        # Mock dialog section builder (it should be called first)
        self.dialog_section_builder.build_dialog_sections.return_value = []
        
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[]
        )
        
        # Execute and expect ValueError
        with pytest.raises(ValueError, match="Evaluation strategy not found: invalid_strategy"):
            self.use_case.execute(raw_dialog_info, "invalid_strategy")
        
        # Verify dialog section builder was called before the error
        self.dialog_section_builder.build_dialog_sections.assert_called_once_with(raw_dialog_info)
        
        # Verify error logging
        self.logger.error.assert_called()
    
    def test_dialog_section_builder_integration(self) -> None:
        """Test integration with dialog section builder."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Question 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Answer 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 10),
                    end_time=datetime(2023, 1, 1, 10, 0, 15)
                )
            ]
        )
        
        # Set up minimal strategy
        strategy = EvaluationStrategy(
            strategy_id="strategy1",
            name="Test",
            description="Test",
            super_metric_metadata_list=[]
        )
        self.evaluation_strategy_repo.get_by_id.return_value = strategy
        
        # Mock dialog section builder to return test sections
        mock_dialog_sections = [
            DialogSection(
                id="ds1",
                dialog_id="test_dialog",
                section_index=0,
                messages=[
                    DialogMessage(
                        section_id="ds1",
                        role=MessageRole.INTERVIEWER,
                        content="Question 1",
                        start_time=datetime(2023, 1, 1, 10, 0, 0),
                        end_time=datetime(2023, 1, 1, 10, 0, 5)
                    ),
                    DialogMessage(
                        section_id="ds1",
                        role=MessageRole.CANDIDATE,
                        content="Answer 1",
                        start_time=datetime(2023, 1, 1, 10, 0, 10),
                        end_time=datetime(2023, 1, 1, 10, 0, 15)
                    )
                ],
                start_time=datetime(2023, 1, 1, 10, 0, 0),
                end_time=datetime(2023, 1, 1, 10, 0, 15)
            )
        ]
        self.dialog_section_builder.build_dialog_sections.return_value = mock_dialog_sections
        
        # Mock other services to avoid complex setup
        self.evaluation_calc_service_builder.build.return_value = Mock()
        mock_overall_score = Score(score_label=ScoreLabel.GOOD, numeric_score=80.0)
        self.evaluation_calc_service_builder.build.return_value.calculate_score.return_value = mock_overall_score
        
        # Execute
        self.use_case.execute(raw_dialog_info, "strategy1")
        
        # Verify dialog section builder was called with correct arguments
        self.dialog_section_builder.build_dialog_sections.assert_called_once_with(raw_dialog_info)
        
        # Verify the dialog sections are processed correctly (no direct repo saves in use case anymore)
        # The actual dialog section creation and saving is now delegated to the DialogSectionBuilder


if __name__ == "__main__":
    pytest.main([__file__])