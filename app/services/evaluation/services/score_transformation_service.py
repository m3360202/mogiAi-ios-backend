"""
Default implementation of ScoreTransformationService.

This service provides the standard transformation logic between score labels 
and numeric scores used throughout the evaluation system.
"""
from typing import Optional
from app.services.evaluation.business import (
    ScoreTransformationService, ScoreLabel, Score, Logger
)


class DefaultScoreTransformationService(ScoreTransformationService):
    """
    Default implementation of ScoreTransformationService.
    
    Implements standard transformation logic:
    - GOOD: 80.0+ numeric score (default: 85.0)
    - FAIR: 65.0-79.9 numeric score (default: 70.0)  
    - POOR: <65.0 numeric score (default: 55.0)
    """
    
    def __init__(self, logger: Logger):
        """
        Initialize the default score transformation service.
        
        Args:
            logger: Logger service for logging operations
        """
        self.logger = logger
        
        # Define standard numeric score mappings
        self._label_to_score_mapping = {
            ScoreLabel.GOOD: 85.0,
            ScoreLabel.FAIR: 70.0,
            ScoreLabel.POOR: 55.0
        }
        
        # Define thresholds for reverse mapping (numeric to label)
        self._good_threshold = 80.0
        self._fair_threshold = 65.0
    
    def label_to_numeric_score(self, score_label: ScoreLabel) -> float:
        """
        Convert a ScoreLabel to its corresponding numeric score.
        
        Args:
            score_label: The score label to convert
            
        Returns:
            float: The standard numeric score for the label
        """
        numeric_score = self._label_to_score_mapping.get(score_label)
        if numeric_score is None:
            self.logger.warning("Unknown score label, defaulting to FAIR", None, {
                "score_label": score_label.value if score_label else "None",
                "service": "DefaultScoreTransformationService"
            })
            return self._label_to_score_mapping[ScoreLabel.FAIR]
        
        self.logger.debug("Converted score label to numeric", {
            "score_label": score_label.value,
            "numeric_score": numeric_score,
            "service": "DefaultScoreTransformationService"
        })
        
        return numeric_score
    
    def numeric_score_to_label(self, numeric_score: float) -> ScoreLabel:
        """
        Convert a numeric score to its corresponding ScoreLabel.
        
        Args:
            numeric_score: The numeric score to convert (0.0-100.0)
            
        Returns:
            ScoreLabel: The label corresponding to the numeric score
        """
        if numeric_score >= self._good_threshold:
            score_label = ScoreLabel.GOOD
        elif numeric_score >= self._fair_threshold:
            score_label = ScoreLabel.FAIR
        else:
            score_label = ScoreLabel.POOR
        
        self.logger.debug("Converted numeric score to label", {
            "numeric_score": numeric_score,
            "score_label": score_label.value,
            "service": "DefaultScoreTransformationService"
        })
        
        return score_label
    
    def create_score(self, score_label: ScoreLabel, numeric_score: Optional[float] = None) -> Score:
        """
        Create a Score object with consistent label and numeric score.
        If numeric_score is not provided, it will be derived from the label.
        
        Args:
            score_label: The score label
            numeric_score: Optional explicit numeric score, otherwise derived from label
            
        Returns:
            Score: A Score object with consistent label and numeric values
        """
        if numeric_score is None:
            numeric_score = self.label_to_numeric_score(score_label)
        else:
            # Validate that explicit numeric_score is consistent with label
            expected_label = self.numeric_score_to_label(numeric_score)
            if expected_label != score_label:
                self.logger.warning("Inconsistent score label and numeric score", None, {
                    "provided_label": score_label.value,
                    "provided_numeric_score": numeric_score,
                    "expected_label_for_score": expected_label.value,
                    "service": "DefaultScoreTransformationService"
                })
        
        score = Score(score_label=score_label, numeric_score=numeric_score)
        
        self.logger.debug("Created score object", {
            "score_label": score_label.value,
            "numeric_score": numeric_score,
            "service": "DefaultScoreTransformationService"
        })
        
        return score