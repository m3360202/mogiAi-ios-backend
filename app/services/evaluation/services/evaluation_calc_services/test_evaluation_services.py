"""
Test for evaluation calculation services.
"""
from unittest import TestCase
from unittest.mock import Mock

from app.services.evaluation.business import (
    EvaluationStrategy, SuperMetric, SuperMetricMetadata, SuperMetricType, Score, ScoreLabel,
    Logger
)
from app.services.evaluation.services.evaluation_calc_services import (
    GenericEvaluationCalculationService, DefaultEvaluationCalcServiceBuilder
)


class TestEvaluationCalculationServices(TestCase):
    """Test cases for evaluation calculation services."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = Mock(spec=Logger)
        self.evaluation_service = GenericEvaluationCalculationService(self.mock_logger)
        self.builder = DefaultEvaluationCalcServiceBuilder(self.mock_logger)
    
    def test_calculate_score_with_super_metrics(self):
        """Test calculation of evaluation score with super-metrics."""
        # Create mock super-metrics
        super_metrics = [
            self._create_mock_super_metric(SuperMetricType.CLARITY, 80.0, 0.3),
            self._create_mock_super_metric(SuperMetricType.EVIDENCE, 90.0, 0.4),
            self._create_mock_super_metric(SuperMetricType.IMPACT, 70.0, 0.3),
        ]
        
        # Calculate score
        result = self.evaluation_service.calculate_score(super_metrics)
        
        # Verify result
        # Expected: (80*0.3 + 90*0.4 + 70*0.3) / (0.3+0.4+0.3) = (24+36+21)/1.0 = 81.0
        self.assertEqual(result.score_label, ScoreLabel.GOOD)
        self.assertEqual(result.numeric_score, 81.0)
    
    def test_calculate_score_empty_list(self):
        """Test calculation with empty super-metrics list."""
        result = self.evaluation_service.calculate_score([])
        
        self.assertEqual(result.score_label, ScoreLabel.POOR)
        self.assertEqual(result.numeric_score, 0.0)
    
    def test_calculate_score_fair_range(self):
        """Test calculation resulting in FAIR score."""
        super_metrics = [
            self._create_mock_super_metric(SuperMetricType.CLARITY, 65.0, 1.0),
        ]
        
        result = self.evaluation_service.calculate_score(super_metrics)
        
        self.assertEqual(result.score_label, ScoreLabel.FAIR)
        self.assertEqual(result.numeric_score, 65.0)
    
    def test_calculate_score_poor_range(self):
        """Test calculation resulting in POOR score."""
        super_metrics = [
            self._create_mock_super_metric(SuperMetricType.CLARITY, 45.0, 1.0),
        ]
        
        result = self.evaluation_service.calculate_score(super_metrics)
        
        self.assertEqual(result.score_label, ScoreLabel.POOR)
        self.assertEqual(result.numeric_score, 45.0)
    
    def test_builder_creates_service(self):
        """Test that builder creates evaluation calculation service."""
        # Create mock strategy
        strategy = self._create_mock_strategy()
        
        # Build service
        service = self.builder.build(strategy)
        
        # Verify service type
        self.assertIsInstance(service, GenericEvaluationCalculationService)
    
    def _create_mock_super_metric(self, super_metric_type: SuperMetricType, score: float, weight: float) -> SuperMetric:
        """Create a mock SuperMetric for testing."""
        metadata = SuperMetricMetadata(
            super_metric_type=super_metric_type,
            metric_metadata_list=[],  # Empty for test
            weight=weight
        )
        
        mock_super_metric = Mock(spec=SuperMetric)
        mock_super_metric.metadata = metadata
        mock_super_metric.score = Score(
            score_label=ScoreLabel.GOOD if score >= 80 else ScoreLabel.FAIR if score >= 60 else ScoreLabel.POOR,
            numeric_score=score
        )
        
        return mock_super_metric
    
    def _create_mock_strategy(self) -> EvaluationStrategy:
        """Create a mock EvaluationStrategy for testing."""
        return EvaluationStrategy(
            strategy_id="test_strategy",
            name="Test Strategy",
            description="A test evaluation strategy",
            super_metric_metadata_list=[]
        )


if __name__ == "__main__":
    import unittest
    unittest.main()