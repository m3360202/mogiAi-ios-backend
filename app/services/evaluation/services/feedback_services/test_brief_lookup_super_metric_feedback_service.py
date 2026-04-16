"""
Tests for BriefLookupSuperMetricFeedbackService.
"""
import json
import pytest
from unittest.mock import Mock, mock_open, patch
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from app.services.evaluation.business import (
    SuperMetric,
    SuperMetricMetadata,
    SuperMetricType,
    SuperMetricSectionScore,
    SuperMetricFeedback,
    SuperMetricFeedbackContributorSectionGroup,
    MetricGroup,
    MetricType,
    MetricMetadata,
    Score,
    ScoreLabel,
    Logger,
    DialogSectionRepo,
)
from app.services.evaluation.business.entities import Metric
from app.services.evaluation.services.feedback_services import BriefLookupSuperMetricFeedbackService


class TestBriefLookupSuperMetricFeedbackService:
    """Test suite for BriefLookupSuperMetricFeedbackService."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock services
        self.mock_logger = Mock(spec=Logger)
        self.mock_dialog_section_repo = Mock(spec=DialogSectionRepo)
        
        # Sample JSON data for testing
        self.sample_json_data: Dict[str, Any] = {
            "brief_lookup": [
                {
                    "super_metric_type": "CLARITY",
                    "metric_type_order": ["CONCISENESS", "LOGICAL_STRUCTURE", "AUDIENCE_APPROPRIATENESS"],
                    "brief_feedbacks": {
                        "GOOD-GOOD-GOOD": ["Excellent clarity!", "Very clear communication"],
                        "GOOD-FAIR-POOR": ["Good start, needs improvement", "Work on appropriateness"],
                        "POOR-POOR-POOR": ["Needs significant improvement", "Focus on clarity"]
                    }
                },
                {
                    "super_metric_type": "EVIDENCE",
                    "metric_type_order": ["EVIDENCE"],
                    "brief_feedbacks": {
                        "GOOD": ["Strong evidence provided", "Well-supported claims"],
                        "FAIR": ["Some evidence present", "Could use more examples"],
                        "POOR": ["Lacking evidence", "Need concrete examples"]
                    }
                }
            ]
        }
    
    def _create_service_with_json_data(self, json_data: Optional[Dict[str, Any]] = None) -> BriefLookupSuperMetricFeedbackService:
        """Create service instance with mocked JSON data."""
        if json_data is None:
            json_data = self.sample_json_data
        
        with patch("builtins.open", mock_open(read_data=json.dumps(json_data))):
            with patch("json.load", return_value=json_data):
                service = BriefLookupSuperMetricFeedbackService(
                    logger=self.mock_logger,
                    dialog_section_repo=self.mock_dialog_section_repo
                )
        return service
    
    def _create_mock_super_metric(
        self,
        super_metric_type: SuperMetricType,
        overall_score: float,
        overall_score_label: ScoreLabel,
        weight: float = 1.0,
        metric_scores: Optional[Dict[MetricType, Dict[str, Any]]] = None
    ) -> SuperMetric:
        """Create a mock SuperMetric for testing."""
        if metric_scores is None:
            metric_scores = {}
        
        # Create metadata
        metric_metadata_list = []
        metric_groups = []
        
        if super_metric_type == SuperMetricType.CLARITY:
            metric_types = [MetricType.CONCISENESS, MetricType.LOGICAL_STRUCTURE, MetricType.AUDIENCE_APPROPRIATENESS]
        elif super_metric_type == SuperMetricType.EVIDENCE:
            metric_types = [MetricType.EVIDENCE]
        else:
            metric_types = []
        
        for metric_type in metric_types:
            # Create metric metadata
            metadata = MetricMetadata(metric_type=metric_type, weight=0.33)
            metric_metadata_list.append(metadata)
            
            # Get score for this metric type
            score_info = metric_scores.get(metric_type, {"score": overall_score, "label": overall_score_label})
            
            # Create mock metric
            mock_metric = Mock(spec=Metric)
            mock_metric.metadata = metadata
            mock_metric.score = Score(
                score_label=score_info["label"],
                numeric_score=score_info["score"]
            )
            mock_metric.sub_metrics = {}
            
            # Create metric group
            metric_group = MetricGroup(
                metric_type=metric_type,
                metrics=[mock_metric]
            )
            metric_groups.append(metric_group)
        
        # Create super metric metadata
        super_metadata = SuperMetricMetadata(
            super_metric_type=super_metric_type,
            metric_metadata_list=metric_metadata_list,
            weight=weight
        )
        
        # Create section scores
        section_scores = [
            SuperMetricSectionScore(
                section_id="section_1",
                section_index=0,
                score=Score(score_label=ScoreLabel.GOOD, numeric_score=85.0)
            ),
            SuperMetricSectionScore(
                section_id="section_2",
                section_index=1,
                score=Score(score_label=ScoreLabel.FAIR, numeric_score=65.0)
            ),
            SuperMetricSectionScore(
                section_id="section_3",
                section_index=2,
                score=Score(score_label=ScoreLabel.POOR, numeric_score=45.0)
            )
        ]
        
        # Create empty feedback initially
        empty_feedback = SuperMetricFeedback(
            brief_feedback="",
            revised_response="",
            feedback="",
            section_index=0
        )
        
        return SuperMetric(
            metadata=super_metadata,
            metric_groups=metric_groups,
            score=Score(score_label=overall_score_label, numeric_score=overall_score),
            section_scores=section_scores,
            feedback=empty_feedback
        )
    
    def test_initialization_success(self) -> None:
        """Test successful initialization with valid JSON data."""
        service = self._create_service_with_json_data()
        
        # Verify JSON data was loaded
        assert service.brief_feedback_data == self.sample_json_data
        
        # Verify logging
        self.mock_logger.debug.assert_called_once()
        debug_call = self.mock_logger.debug.call_args
        assert "Successfully loaded brief feedback lookup data" in debug_call[0][0]
        assert debug_call[0][1]["lookup_entries"] == 2
    
    def test_initialization_file_not_found(self) -> None:
        """Test initialization when JSON file is not found."""
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            service = BriefLookupSuperMetricFeedbackService(
                logger=self.mock_logger,
                dialog_section_repo=self.mock_dialog_section_repo
            )
        
        # Should fall back to empty data
        assert service.brief_feedback_data == {"brief_lookup": []}
        
        # Verify error logging
        self.mock_logger.error.assert_called_once()
        error_call = self.mock_logger.error.call_args
        assert "Failed to load brief feedback lookup data" in error_call[0][0]
        assert isinstance(error_call[0][1], FileNotFoundError)
    
    def test_initialization_invalid_json(self) -> None:
        """Test initialization with invalid JSON data."""
        with patch("builtins.open", mock_open(read_data="invalid json")):
            with patch("json.load", side_effect=json.JSONDecodeError("Invalid JSON", "", 0)):
                service = BriefLookupSuperMetricFeedbackService(
                    logger=self.mock_logger,
                    dialog_section_repo=self.mock_dialog_section_repo
                )
        
        # Should fall back to empty data
        assert service.brief_feedback_data == {"brief_lookup": []}
        
        # Verify error logging
        self.mock_logger.error.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_and_update_feedback_success(self) -> None:
        """Test successful feedback generation and update."""
        service = self._create_service_with_json_data()
        
        # Create test super metrics
        super_metrics = [
            self._create_mock_super_metric(
                SuperMetricType.CLARITY,
                overall_score=80.0,
                overall_score_label=ScoreLabel.GOOD,
                weight=0.6,
                metric_scores={
                    MetricType.CONCISENESS: {"score": 85.0, "label": ScoreLabel.GOOD},
                    MetricType.LOGICAL_STRUCTURE: {"score": 75.0, "label": ScoreLabel.GOOD},
                    MetricType.AUDIENCE_APPROPRIATENESS: {"score": 80.0, "label": ScoreLabel.GOOD}
                }
            ),
            self._create_mock_super_metric(
                SuperMetricType.EVIDENCE,
                overall_score=70.0,
                overall_score_label=ScoreLabel.FAIR,
                weight=0.4
            )
        ]
        
        # Call the method
        result = await service.generate_and_update_feedback(super_metrics)
        
        # Verify results
        assert len(result) == 2
        
        # Check CLARITY feedback
        clarity_result = next(sm for sm in result if sm.metadata.super_metric_type == SuperMetricType.CLARITY)
        assert clarity_result.feedback.brief_feedback in ["Excellent clarity!", "Very clear communication"]
        assert clarity_result.feedback.revised_response == ""
        assert clarity_result.feedback.feedback == ""
        assert clarity_result.feedback.section_index in [0, 1, 2]  # One of the section indices
        
        # Check EVIDENCE feedback
        evidence_result = next(sm for sm in result if sm.metadata.super_metric_type == SuperMetricType.EVIDENCE)
        assert evidence_result.feedback.brief_feedback in ["Some evidence present", "Could use more examples"]
        assert evidence_result.feedback.revised_response == ""
        assert evidence_result.feedback.feedback == ""
    
    @pytest.mark.asyncio
    async def test_generate_and_update_feedback_error_handling(self) -> None:
        """Test error handling during feedback generation."""
        service = self._create_service_with_json_data()
        
        # Create super metrics that will cause errors
        super_metrics = [Mock()]  # Invalid super metric
        
        with pytest.raises(Exception):
            await service.generate_and_update_feedback(super_metrics)
        
        # Verify error logging
        self.mock_logger.error.assert_called()
        error_call = self.mock_logger.error.call_args
        assert "Failed to generate and update feedback" in error_call[0][0]
    
    def test_pick_contributing_sections(self) -> None:
        """Test the contributing sections picking logic."""
        service = self._create_service_with_json_data()
        
        # Create test super metrics with different weights
        super_metrics = [
            self._create_mock_super_metric(SuperMetricType.CLARITY, 80.0, ScoreLabel.GOOD, weight=0.6),
            self._create_mock_super_metric(SuperMetricType.EVIDENCE, 70.0, ScoreLabel.FAIR, weight=0.4)
        ]
        
        # Call the method
        contributing_groups = service._pick_contributing_sections(super_metrics)
        
        # Should have picked sections for both super metrics
        assert len(contributing_groups) <= 2  # At most 2, could be less if sections overlap
        
        # Verify no duplicate sections
        section_ids = [cg.section_id for cg in contributing_groups]
        assert len(section_ids) == len(set(section_ids))  # No duplicates
        
        # Verify structure
        for group in contributing_groups:
            assert isinstance(group.super_metric_type, SuperMetricType)
            assert isinstance(group.section_id, str)
            assert isinstance(group.section_index, int)
            assert isinstance(group.is_positive, bool)
    
    def test_lookup_brief_feedback_clarity_success(self) -> None:
        """Test successful brief feedback lookup for CLARITY super metric."""
        service = self._create_service_with_json_data()
        
        # Create a CLARITY super metric with specific scores
        super_metric = self._create_mock_super_metric(
            SuperMetricType.CLARITY,
            overall_score=80.0,
            overall_score_label=ScoreLabel.GOOD,
            metric_scores={
                MetricType.CONCISENESS: {"score": 85.0, "label": ScoreLabel.GOOD},
                MetricType.LOGICAL_STRUCTURE: {"score": 75.0, "label": ScoreLabel.GOOD},
                MetricType.AUDIENCE_APPROPRIATENESS: {"score": 80.0, "label": ScoreLabel.GOOD}
            }
        )
        
        # Call the method
        result = service._lookup_brief_feedback(super_metric)
        
        # Should get feedback from GOOD-GOOD-GOOD key
        assert result in ["Excellent clarity!", "Very clear communication"]
    
    def test_lookup_brief_feedback_evidence_success(self) -> None:
        """Test successful brief feedback lookup for EVIDENCE super metric."""
        service = self._create_service_with_json_data()
        
        # Create an EVIDENCE super metric
        super_metric = self._create_mock_super_metric(
            SuperMetricType.EVIDENCE,
            overall_score=70.0,
            overall_score_label=ScoreLabel.FAIR
        )
        
        # Call the method
        result = service._lookup_brief_feedback(super_metric)
        
        # Should get feedback from FAIR key
        assert result in ["Some evidence present", "Could use more examples"]
    
    def test_lookup_brief_feedback_no_entry_found(self) -> None:
        """Test feedback lookup when no entry is found for super metric type."""
        service = self._create_service_with_json_data()
        
        # Create a super metric type not in JSON data
        super_metric = self._create_mock_super_metric(
            SuperMetricType.IMPACT,  # Not in sample data
            overall_score=80.0,
            overall_score_label=ScoreLabel.GOOD
        )
        
        # Call the method
        result = service._lookup_brief_feedback(super_metric)
        
        # Should return empty string
        assert result == ""
        
        # Verify warning logging
        warning_calls = [call for call in self.mock_logger.warning.call_args_list 
                        if "No lookup entry found" in call[0][0]]
        assert len(warning_calls) >= 1
    
    def test_lookup_brief_feedback_no_key_found(self) -> None:
        """Test feedback lookup when lookup key is not found."""
        service = self._create_service_with_json_data()
        
        # Create a CLARITY super metric with scores that don't match any key
        super_metric = self._create_mock_super_metric(
            SuperMetricType.CLARITY,
            overall_score=80.0,
            overall_score_label=ScoreLabel.GOOD,
            metric_scores={
                MetricType.CONCISENESS: {"score": 85.0, "label": ScoreLabel.GOOD},
                MetricType.LOGICAL_STRUCTURE: {"score": 65.0, "label": ScoreLabel.FAIR},
                MetricType.AUDIENCE_APPROPRIATENESS: {"score": 55.0, "label": ScoreLabel.FAIR}
            }
        )
        
        # This should create key "GOOD-FAIR-FAIR" which doesn't exist in sample data
        result = service._lookup_brief_feedback(super_metric)
        
        # Should return empty string
        assert result == ""
        
        # Verify warning logging
        warning_calls = [call for call in self.mock_logger.warning.call_args_list 
                        if "No brief feedback found for lookup key" in call[0][0]]
        assert len(warning_calls) >= 1
    
    def test_build_lookup_key_with_metric_order(self) -> None:
        """Test lookup key building with metric type order."""
        service = self._create_service_with_json_data()
        
        # Create super metric with specific scores
        super_metric = self._create_mock_super_metric(
            SuperMetricType.CLARITY,
            overall_score=80.0,
            overall_score_label=ScoreLabel.GOOD,
            metric_scores={
                MetricType.CONCISENESS: {"score": 85.0, "label": ScoreLabel.GOOD},
                MetricType.LOGICAL_STRUCTURE: {"score": 65.0, "label": ScoreLabel.FAIR},
                MetricType.AUDIENCE_APPROPRIATENESS: {"score": 45.0, "label": ScoreLabel.POOR}
            }
        )
        
        # Get lookup entry for CLARITY
        lookup_entry = self.sample_json_data["brief_lookup"][0]
        
        # Call the method
        result = service._build_lookup_key(super_metric, lookup_entry)
        
        # Should build key in order: CONCISENESS-LOGICAL_STRUCTURE-AUDIENCE_APPROPRIATENESS
        assert result == "GOOD-FAIR-POOR"
    
    def test_build_lookup_key_no_metric_order(self) -> None:
        """Test lookup key building without metric type order."""
        service = self._create_service_with_json_data()
        
        # Create super metric
        super_metric = self._create_mock_super_metric(
            SuperMetricType.EVIDENCE,
            overall_score=70.0,
            overall_score_label=ScoreLabel.FAIR
        )
        
        # Create lookup entry without metric_type_order
        lookup_entry = {"super_metric_type": "EVIDENCE"}
        
        # Call the method
        result = service._build_lookup_key(super_metric, lookup_entry)
        
        # Should use overall score
        assert result == "FAIR"
    
    def test_build_lookup_key_missing_metric(self) -> None:
        """Test lookup key building when a metric is missing."""
        service = self._create_service_with_json_data()
        
        # Create super metric missing one of the expected metrics
        super_metric = self._create_mock_super_metric(
            SuperMetricType.CLARITY,
            overall_score=80.0,
            overall_score_label=ScoreLabel.GOOD,
            metric_scores={
                MetricType.CONCISENESS: {"score": 85.0, "label": ScoreLabel.GOOD},
                # Missing LOGICAL_STRUCTURE and AUDIENCE_APPROPRIATENESS
            }
        )
        
        # Get lookup entry for CLARITY
        lookup_entry = self.sample_json_data["brief_lookup"][0]
        
        # Call the method
        result = service._build_lookup_key(super_metric, lookup_entry)
        
        # Should use overall score for missing metrics
        assert result == "GOOD-GOOD-GOOD"  # CONCISENESS=GOOD, others fallback to overall=GOOD
    
    def test_create_empty_feedback(self) -> None:
        """Test creation of empty feedback."""
        service = self._create_service_with_json_data()
        
        # Call the method
        result = service._create_empty_feedback()
        
        # Verify structure
        assert isinstance(result, SuperMetricFeedback)
        assert result.brief_feedback == ""
        assert result.revised_response == ""
        assert result.feedback == ""
        assert result.section_index == 0
    
    def test_update_super_metrics(self) -> None:
        """Test updating super metrics with feedback."""
        service = self._create_service_with_json_data()
        
        # Create test super metrics
        super_metrics = [
            self._create_mock_super_metric(SuperMetricType.CLARITY, 80.0, ScoreLabel.GOOD),
            self._create_mock_super_metric(SuperMetricType.EVIDENCE, 70.0, ScoreLabel.FAIR)
        ]
        
        # Create feedback map
        feedback_map = {
            SuperMetricType.CLARITY: SuperMetricFeedback(
                brief_feedback="Test clarity feedback",
                revised_response="",
                feedback="",
                section_index=1
            ),
            SuperMetricType.EVIDENCE: SuperMetricFeedback(
                brief_feedback="Test evidence feedback",
                revised_response="",
                feedback="",
                section_index=2
            )
        }
        
        # Call the method
        result = service._update_super_metrics(super_metrics, feedback_map)
        
        # Verify results
        assert len(result) == 2
        
        # Check CLARITY feedback
        clarity_result = next(sm for sm in result if sm.metadata.super_metric_type == SuperMetricType.CLARITY)
        assert clarity_result.feedback.brief_feedback == "Test clarity feedback"
        assert clarity_result.feedback.section_index == 1
        
        # Check EVIDENCE feedback
        evidence_result = next(sm for sm in result if sm.metadata.super_metric_type == SuperMetricType.EVIDENCE)
        assert evidence_result.feedback.brief_feedback == "Test evidence feedback"
        assert evidence_result.feedback.section_index == 2
        
        # Verify original super metrics are unchanged (frozen objects)
        assert super_metrics[0].feedback.brief_feedback == ""
        assert super_metrics[1].feedback.brief_feedback == ""
    
    def test_update_super_metrics_missing_feedback(self) -> None:
        """Test updating super metrics when feedback is missing."""
        service = self._create_service_with_json_data()
        
        # Create test super metric
        super_metrics = [
            self._create_mock_super_metric(SuperMetricType.CLARITY, 80.0, ScoreLabel.GOOD)
        ]
        
        # Empty feedback map
        feedback_map = {}
        
        # Call the method
        result = service._update_super_metrics(super_metrics, feedback_map)
        
        # Verify result has empty feedback
        assert len(result) == 1
        assert result[0].feedback.brief_feedback == ""
        assert result[0].feedback.revised_response == ""
        assert result[0].feedback.feedback == ""


if __name__ == "__main__":
    pytest.main([__file__])