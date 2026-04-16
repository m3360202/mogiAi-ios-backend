"""
Unit tests for in-memory repository implementations.
Tests all repository classes for correctness, thread safety, and edge cases.
"""
import pytest
from threading import Thread
from datetime import datetime, timezone

from app.services.evaluation.business import (
    EvaluationRecord,
    DialogSection,
    Metric,
    EvaluationStrategy,
    DialogMessage,
    Score,
    MetricMetadata,
    SuperMetricMetadata,
    SuperMetric,
    MetricGroup,
    MessageRole,
    ScoreLabel,
    MetricType,
    SuperMetricType,
)

from app.services.evaluation.repositories import (
    InMemoryEvaluationRecordRepo,
    InMemoryDialogSectionRepo,
    InMemoryMetricRepo,
    InMemoryEvaluationStrategyRepo,
)


class TestInMemoryEvaluationRecordRepo:
    """Test cases for InMemoryEvaluationRecordRepo."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.repo = InMemoryEvaluationRecordRepo()
        
        # Create test data
        self.score = Score(score_label=ScoreLabel.GOOD, numeric_score=85.0)
        self.strategy = EvaluationStrategy(
            strategy_id="test_strategy",
            name="Test Strategy",
            description="Test description",
            super_metric_metadata_list=[]
        )
        self.evaluation_record = EvaluationRecord(
            id="eval_1",
            strategy=self.strategy,
            interview_record_id="interview_1",
            super_metrics=[],
            overall_score=self.score
        )
    
    def test_save_and_get_by_interview_record_id(self):
        """Test saving and retrieving by interview record ID."""
        self.repo.save(self.evaluation_record)
        
        retrieved = self.repo.get_by_interview_record_id("interview_1")
        assert retrieved is not None
        assert retrieved.id == "eval_1"
        assert retrieved.interview_record_id == "interview_1"
        assert retrieved.overall_score.numeric_score == 85.0
    
    def test_get_by_id(self):
        """Test retrieving by evaluation record ID."""
        self.repo.save(self.evaluation_record)
        
        retrieved = self.repo.get_by_id("eval_1")
        assert retrieved is not None
        assert retrieved.id == "eval_1"
        assert retrieved.interview_record_id == "interview_1"
    
    def test_get_nonexistent_record(self):
        """Test retrieving non-existent records."""
        assert self.repo.get_by_interview_record_id("nonexistent") is None
        assert self.repo.get_by_id("nonexistent") is None
    
    def test_get_all(self):
        """Test retrieving all records."""
        # Initially empty
        assert self.repo.get_all() == []
        
        # Add record
        self.repo.save(self.evaluation_record)
        all_records = self.repo.get_all()
        assert len(all_records) == 1
        assert all_records[0].id == "eval_1"
    
    def test_clear(self):
        """Test clearing all records."""
        self.repo.save(self.evaluation_record)
        assert len(self.repo.get_all()) == 1
        
        self.repo.clear()
        assert len(self.repo.get_all()) == 0
        assert self.repo.get_by_interview_record_id("interview_1") is None
    
    def test_overwrite_existing_record(self):
        """Test overwriting an existing record."""
        self.repo.save(self.evaluation_record)
        
        # Create updated record with same ID
        updated_score = Score(score_label=ScoreLabel.FAIR, numeric_score=70.0)
        updated_record = EvaluationRecord(
            id="eval_1",
            strategy=self.strategy,
            interview_record_id="interview_1",
            super_metrics=[],
            overall_score=updated_score
        )
        
        self.repo.save(updated_record)
        retrieved = self.repo.get_by_id("eval_1")
        assert retrieved is not None
        assert retrieved.overall_score.numeric_score == 70.0
    
    def test_thread_safety(self):
        """Test thread safety with concurrent operations."""
        def save_records(start_id: int):
            for i in range(start_id, start_id + 10):
                record = EvaluationRecord(
                    id=f"eval_{i}",
                    strategy=self.strategy,
                    interview_record_id=f"interview_{i}",
                    super_metrics=[],
                    overall_score=self.score
                )
                self.repo.save(record)
        
        # Create multiple threads
        threads = []
        for i in range(0, 50, 10):
            thread = Thread(target=save_records, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify all records were saved
        all_records = self.repo.get_all()
        assert len(all_records) == 50
        
        # Verify index integrity
        for i in range(50):
            assert self.repo.get_by_interview_record_id(f"interview_{i}") is not None


class TestInMemoryDialogSectionRepo:
    """Test cases for InMemoryDialogSectionRepo."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.repo = InMemoryDialogSectionRepo()
        
        # Create test data
        self.start_time = datetime.now(timezone.utc)
        self.end_time = datetime.now(timezone.utc)
        
        self.message1 = DialogMessage(
            section_id="section_1",
            role=MessageRole.INTERVIEWER,
            content="Hello, can you tell me about yourself?",
            start_time=self.start_time,
            end_time=self.end_time
        )
        
        self.message2 = DialogMessage(
            section_id="section_1",
            role=MessageRole.CANDIDATE,
            content="Sure, I'm a software engineer...",
            start_time=self.start_time,
            end_time=self.end_time
        )
        
        self.dialog_section = DialogSection(
            id="section_1",
            dialog_id="dialog_1",
            messages=[self.message1, self.message2],
            start_time=self.start_time,
            end_time=self.end_time
        )
    
    def test_save_and_get_by_id(self):
        """Test saving and retrieving by section ID."""
        self.repo.save(self.dialog_section)
        
        retrieved = self.repo.get_by_id("section_1")
        assert retrieved is not None
        assert retrieved.id == "section_1"
        assert retrieved.dialog_id == "dialog_1"
        assert len(retrieved.messages) == 2
    
    def test_get_by_dialog_id(self):
        """Test retrieving by dialog ID."""
        self.repo.save(self.dialog_section)
        
        # Create another section for the same dialog
        section2 = DialogSection(
            id="section_2",
            dialog_id="dialog_1",
            messages=[self.message1],
            start_time=self.start_time,
            end_time=self.end_time
        )
        self.repo.save(section2)
        
        sections = self.repo.get_by_dialog_id("dialog_1")
        assert len(sections) == 2
        section_ids = [s.id for s in sections]
        assert "section_1" in section_ids
        assert "section_2" in section_ids
    
    def test_get_nonexistent_section(self):
        """Test retrieving non-existent sections."""
        assert self.repo.get_by_id("nonexistent") is None
        assert self.repo.get_by_dialog_id("nonexistent") == []
    
    def test_get_all(self):
        """Test retrieving all sections."""
        assert self.repo.get_all() == []
        
        self.repo.save(self.dialog_section)
        all_sections = self.repo.get_all()
        assert len(all_sections) == 1
        assert all_sections[0].id == "section_1"
    
    def test_clear(self):
        """Test clearing all sections."""
        self.repo.save(self.dialog_section)
        assert len(self.repo.get_all()) == 1
        
        self.repo.clear()
        assert len(self.repo.get_all()) == 0
        assert self.repo.get_by_dialog_id("dialog_1") == []
    
    def test_dialog_index_integrity(self):
        """Test that dialog index remains consistent."""
        # Create sections for different dialogs
        section1 = DialogSection(
            id="section_1", dialog_id="dialog_1", messages=[], 
            start_time=self.start_time, end_time=self.end_time
        )
        section2 = DialogSection(
            id="section_2", dialog_id="dialog_1", messages=[], 
            start_time=self.start_time, end_time=self.end_time
        )
        section3 = DialogSection(
            id="section_3", dialog_id="dialog_2", messages=[], 
            start_time=self.start_time, end_time=self.end_time
        )
        
        self.repo.save(section1)
        self.repo.save(section2)
        self.repo.save(section3)
        
        # Check dialog_1 sections
        dialog1_sections = self.repo.get_by_dialog_id("dialog_1")
        assert len(dialog1_sections) == 2
        
        # Check dialog_2 sections
        dialog2_sections = self.repo.get_by_dialog_id("dialog_2")
        assert len(dialog2_sections) == 1
        assert dialog2_sections[0].id == "section_3"


class TestInMemoryMetricRepo:
    """Test cases for InMemoryMetricRepo."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.repo = InMemoryMetricRepo()
        
        # Create test data
        self.sub_metrics_dict = {
            "is_core_idea_presented": True,
            "core_idea": "Test core idea",
            "filter_words": ["well", "like"],
            "strong_words": ["excellent", "outstanding"],
            "sentence_count": 2,
            "filter_words_count": 2,
            "strong_words_count": 2,
            "filter_words_frequency": 1.0,
            "strong_words_frequency": 1.0
        }
        
        self.score = Score(score_label=ScoreLabel.GOOD, numeric_score=85.0)
        self.metadata = MetricMetadata(metric_type=MetricType.CONCISENESS)
        
        self.metric = Metric(
            id="metric_1",
            metadata=self.metadata,
            dialog_section_id="section_1",
            dialog_section_index=1,
            sub_metrics=self.sub_metrics_dict,
            score=self.score,
            revision="Great answer!"
        )
    
    def test_save_and_get_by_id(self):
        """Test saving and retrieving by metric ID."""
        self.repo.save(self.metric)
        
        retrieved = self.repo.get_by_id("metric_1")
        assert retrieved is not None
        assert retrieved.id == "metric_1"
        assert retrieved.dialog_section_id == "section_1"
        assert len(retrieved.sub_metrics) == 9  # Updated to match our new sub_metrics_dict
        assert retrieved.score.numeric_score == 85.0
    
    def test_get_by_dialog_section_id(self):
        """Test retrieving by dialog section ID."""
        self.repo.save(self.metric)
        
        # Create another metric for the same section
        metric2 = Metric(
            id="metric_2",
            metadata=MetricMetadata(metric_type=MetricType.LOGICAL_STRUCTURE),
            dialog_section_id="section_1",
            dialog_section_index=1,
            sub_metrics={},
            score=self.score,
            revision=""
        )
        self.repo.save(metric2)
        
        metrics = self.repo.get_by_dialog_section_id("section_1")
        assert len(metrics) == 2
        metric_ids = [m.id for m in metrics]
        assert "metric_1" in metric_ids
        assert "metric_2" in metric_ids
    
    def test_get_nonexistent_metric(self):
        """Test retrieving non-existent metrics."""
        assert self.repo.get_by_id("nonexistent") is None
        assert self.repo.get_by_dialog_section_id("nonexistent") == []
    
    def test_get_all(self):
        """Test retrieving all metrics."""
        assert self.repo.get_all() == []
        
        self.repo.save(self.metric)
        all_metrics = self.repo.get_all()
        assert len(all_metrics) == 1
        assert all_metrics[0].id == "metric_1"
    
    def test_clear(self):
        """Test clearing all metrics."""
        self.repo.save(self.metric)
        assert len(self.repo.get_all()) == 1
        
        self.repo.clear()
        assert len(self.repo.get_all()) == 0
        assert self.repo.get_by_dialog_section_id("section_1") == []
    
    def test_section_index_integrity(self):
        """Test that section index remains consistent."""
        # Create metrics for different sections
        metric1 = Metric(
            id="metric_1", metadata=self.metadata, dialog_section_id="section_1",
            dialog_section_index=1,
            sub_metrics={}, score=self.score, revision=""
        )
        metric2 = Metric(
            id="metric_2", metadata=self.metadata, dialog_section_id="section_2",
            dialog_section_index=2,
            sub_metrics={}, score=self.score, revision=""
        )
        metric3 = Metric(
            id="metric_3", metadata=self.metadata, dialog_section_id="section_1",
            dialog_section_index=1,
            sub_metrics={}, score=self.score, revision=""
        )
        
        self.repo.save(metric1)
        self.repo.save(metric2)
        self.repo.save(metric3)
        
        # Check section_1 metrics
        section1_metrics = self.repo.get_by_dialog_section_id("section_1")
        assert len(section1_metrics) == 2
        
        # Check section_2 metrics
        section2_metrics = self.repo.get_by_dialog_section_id("section_2")
        assert len(section2_metrics) == 1
        assert section2_metrics[0].id == "metric_2"


class TestInMemoryEvaluationStrategyRepo:
    """Test cases for InMemoryEvaluationStrategyRepo."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.repo = InMemoryEvaluationStrategyRepo()
        
        # Create test data
        self.super_metric_metadata = SuperMetricMetadata(
            super_metric_type=SuperMetricType.CLARITY,
            metric_metadata_list=[
                MetricMetadata(metric_type=MetricType.CONCISENESS),
                MetricMetadata(metric_type=MetricType.LOGICAL_STRUCTURE),
            ]
        )
        
        self.strategy = EvaluationStrategy(
            strategy_id="custom_strategy",
            name="Custom Strategy",
            description="A custom evaluation strategy",
            super_metric_metadata_list=[self.super_metric_metadata]
        )
    
    def test_default_strategy_exists(self):
        """Test that default strategy is pre-populated."""
        default_strategy = self.repo.get_by_id("strategy_1")
        assert default_strategy is not None
        assert default_strategy.name == "Default Strategy"
        assert len(default_strategy.super_metric_metadata_list) == 2
    
    def test_save_and_get_by_id(self):
        """Test saving and retrieving by strategy ID."""
        self.repo.save(self.strategy)
        
        retrieved = self.repo.get_by_id("custom_strategy")
        assert retrieved is not None
        assert retrieved.strategy_id == "custom_strategy"
        assert retrieved.name == "Custom Strategy"
        assert len(retrieved.super_metric_metadata_list) == 1
    
    def test_get_nonexistent_strategy(self):
        """Test retrieving non-existent strategy."""
        assert self.repo.get_by_id("nonexistent") is None
    
    def test_get_all(self):
        """Test retrieving all strategies."""
        # Should have default strategy
        all_strategies = self.repo.get_all()
        assert len(all_strategies) == 1
        assert all_strategies[0].strategy_id == "strategy_1"
        
        # Add custom strategy
        self.repo.save(self.strategy)
        all_strategies = self.repo.get_all()
        assert len(all_strategies) == 2
        
        strategy_ids = [s.strategy_id for s in all_strategies]
        assert "strategy_1" in strategy_ids
        assert "custom_strategy" in strategy_ids
    
    def test_clear(self):
        """Test clearing all strategies."""
        # Add custom strategy
        self.repo.save(self.strategy)
        assert len(self.repo.get_all()) == 2  # default + custom
        
        self.repo.clear()
        assert len(self.repo.get_all()) == 0
        assert self.repo.get_by_id("strategy_1") is None
    
    def test_overwrite_strategy(self):
        """Test overwriting an existing strategy."""
        self.repo.save(self.strategy)
        
        # Create updated strategy with same ID
        updated_strategy = EvaluationStrategy(
            strategy_id="custom_strategy",
            name="Updated Custom Strategy",
            description="An updated custom evaluation strategy",
            super_metric_metadata_list=[]
        )
        
        self.repo.save(updated_strategy)
        retrieved = self.repo.get_by_id("custom_strategy")
        assert retrieved is not None
        assert retrieved.name == "Updated Custom Strategy"
        assert len(retrieved.super_metric_metadata_list) == 0
    
    def test_default_strategy_metadata(self):
        """Test default strategy has correct metadata structure."""
        default_strategy = self.repo.get_by_id("strategy_1")
        assert default_strategy is not None
        
        # Should have CLARITY and EVIDENCE super metrics
        super_metric_types = [sm.super_metric_type for sm in default_strategy.super_metric_metadata_list]
        assert SuperMetricType.CLARITY in super_metric_types
        assert SuperMetricType.EVIDENCE in super_metric_types
        
        # CLARITY should have CONCISENESS and LOGICAL_STRUCTURE
        clarity_metadata = next(
            sm for sm in default_strategy.super_metric_metadata_list 
            if sm.super_metric_type == SuperMetricType.CLARITY
        )
        clarity_metric_types = [m.metric_type for m in clarity_metadata.metric_metadata_list]
        assert MetricType.CONCISENESS in clarity_metric_types
        assert MetricType.LOGICAL_STRUCTURE in clarity_metric_types
        
        # EVIDENCE should have RELEVANCE and COMPLETENESS
        evidence_metadata = next(
            sm for sm in default_strategy.super_metric_metadata_list 
            if sm.super_metric_type == SuperMetricType.EVIDENCE
        )
        evidence_metric_types = [m.metric_type for m in evidence_metadata.metric_metadata_list]
        assert MetricType.RELEVANCE in evidence_metric_types
        assert MetricType.COMPLETENESS in evidence_metric_types


class TestRepositoryIntegration:
    """Integration tests for repository interactions."""
    
    def setup_method(self):
        """Set up test fixtures for integration tests."""
        self.eval_repo = InMemoryEvaluationRecordRepo()
        self.section_repo = InMemoryDialogSectionRepo()
        self.metric_repo = InMemoryMetricRepo()
        self.strategy_repo = InMemoryEvaluationStrategyRepo()
    
    def test_full_evaluation_workflow(self):
        """Test a complete evaluation workflow across repositories."""
        # 1. Get evaluation strategy
        strategy = self.strategy_repo.get_by_id("strategy_1")
        assert strategy is not None
        
        # 2. Create and save dialog sections
        start_time = datetime.now(timezone.utc)
        end_time = datetime.now(timezone.utc)
        
        message = DialogMessage(
            section_id="section_1",
            role=MessageRole.CANDIDATE,
            content="I have 5 years of experience in Python development.",
            start_time=start_time,
            end_time=end_time
        )
        
        section = DialogSection(
            id="section_1",
            dialog_id="dialog_1",
            messages=[message],
            start_time=start_time,
            end_time=end_time
        )
        self.section_repo.save(section)
        
        # 3. Create and save metrics
        sub_metrics_dict = {
            "is_core_idea_presented": True,
            "core_idea": "Test integration",
            "filter_words": ["well"],
            "strong_words": ["excellent"],
            "sentence_count": 1,
            "filter_words_count": 1,
            "strong_words_count": 1,
            "filter_words_frequency": 1.0,
            "strong_words_frequency": 1.0
        }
        
        metric = Metric(
            id="metric_1",
            metadata=MetricMetadata(metric_type=MetricType.CONCISENESS),
            dialog_section_id="section_1",
            dialog_section_index=1,
            sub_metrics=sub_metrics_dict,
            score=Score(score_label=ScoreLabel.GOOD, numeric_score=85.0),
            revision="Good conciseness."
        )
        self.metric_repo.save(metric)
        
        # 4. Create and save evaluation record
        evaluation_record = EvaluationRecord(
            id="eval_1",
            strategy=strategy,
            interview_record_id="interview_1",
            super_metrics=[],
            overall_score=Score(score_label=ScoreLabel.GOOD, numeric_score=85.0)
        )
        self.eval_repo.save(evaluation_record)
        
        # 5. Verify all data is correctly stored and retrievable
        retrieved_strategy = self.strategy_repo.get_by_id("strategy_1")
        retrieved_section = self.section_repo.get_by_id("section_1")
        retrieved_metrics = self.metric_repo.get_by_dialog_section_id("section_1")
        retrieved_evaluation = self.eval_repo.get_by_interview_record_id("interview_1")
        
        assert retrieved_strategy is not None
        assert retrieved_strategy.strategy_id == "strategy_1"
        assert retrieved_section is not None
        assert retrieved_section.id == "section_1"
        assert len(retrieved_metrics) == 1
        assert retrieved_metrics[0].id == "metric_1"
        assert retrieved_evaluation is not None
        assert retrieved_evaluation.id == "eval_1"
        assert retrieved_evaluation.interview_record_id == "interview_1"


# Simple test function for manual execution
def test_simple_functionality():
    """Simple test to verify basic functionality without pytest."""
    print("Testing in-memory repositories...")
    
    # Test EvaluationStrategyRepo
    strategy_repo = InMemoryEvaluationStrategyRepo()
    strategy = strategy_repo.get_by_id("strategy_1")
    assert strategy is not None, "Default strategy should exist"
    print(f"✓ Retrieved strategy: {strategy.name}")
    
    # Test DialogSectionRepo
    dialog_repo = InMemoryDialogSectionRepo()
    
    # Create test dialog section
    messages = [
        DialogMessage(
            section_id="section_1",
            role=MessageRole.INTERVIEWER,
            content="What are your strengths?",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc)
        ),
        DialogMessage(
            section_id="section_1", 
            role=MessageRole.CANDIDATE,
            content="My main strength is problem-solving.",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc)
        )
    ]
    
    dialog_section = DialogSection(
        id="section_1",
        dialog_id="dialog_1",
        messages=messages,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc)
    )
    
    dialog_repo.save(dialog_section)
    retrieved_section = dialog_repo.get_by_id("section_1")
    assert retrieved_section is not None, "Dialog section should be saved and retrievable"
    print(f"✓ Saved and retrieved dialog section: {retrieved_section.id}")
    
    # Test MetricRepo
    metric_repo = InMemoryMetricRepo()
    
    # Create test metric
    sub_metrics_dict = {
        "is_core_idea_presented": True,
        "core_idea": "Test final integration",
        "filter_words": ["um", "like"],
        "strong_words": ["confident", "excellent"],
        "sentence_count": 2,
        "filter_words_count": 2,
        "strong_words_count": 2,
        "filter_words_frequency": 1.0,
        "strong_words_frequency": 1.0
    }
    
    score = Score(
        score_label=ScoreLabel.GOOD,
        numeric_score=85.0
    )
    
    metric = Metric(
        id="metric_1",
        metadata=MetricMetadata(metric_type=MetricType.CONCISENESS),
        dialog_section_id="section_1",
        dialog_section_index=1,
        sub_metrics=sub_metrics_dict,
        score=score,
        revision="Consider being more concise."
    )
    
    metric_repo.save(metric)
    retrieved_metric = metric_repo.get_by_id("metric_1")
    assert retrieved_metric is not None, "Metric should be saved and retrievable"
    print(f"✓ Saved and retrieved metric: {retrieved_metric.id}")
    
    # Test EvaluationRecordRepo
    eval_repo = InMemoryEvaluationRecordRepo()
    
    # Create test evaluation record
    super_metrics = [
        SuperMetric(
            metadata=SuperMetricMetadata(
                super_metric_type=SuperMetricType.CLARITY,
                metric_metadata_list=[MetricMetadata(metric_type=MetricType.CONCISENESS)]
            ),
            metric_groups=[
                MetricGroup(
                    metric_type=MetricType.CONCISENESS,
                    metrics=[metric]
                )
            ],
            score=score,
            feedback="Good clarity overall."
        )
    ]
    
    evaluation_record = EvaluationRecord(
        id="eval_1",
        strategy=strategy,
        interview_record_id="interview_123",
        super_metrics=super_metrics,
        overall_score=score
    )
    
    eval_repo.save(evaluation_record)
    retrieved_eval = eval_repo.get_by_interview_record_id("interview_123")
    assert retrieved_eval is not None, "Evaluation record should be saved and retrievable"
    print(f"✓ Saved and retrieved evaluation record: {retrieved_eval.id}")
    
    print("All in-memory repository tests passed! ✓")


if __name__ == "__main__":
    # For pytest execution
    try:
        pytest.main([__file__])
    except ImportError:
        # If pytest is not available, run simple test
        test_simple_functionality()
        print("\n🎉 All repository tests completed successfully!")