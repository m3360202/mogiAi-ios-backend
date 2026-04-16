"""
Verbal Visual Metric Calculation Service.

This service implements the calculation of verbal and visual performance metrics
by extracting score labels from dialog message nonverbal performance data and 
translating them to numeric scores.
"""
from typing import List, Optional, Dict, Any, Tuple
from app.services.evaluation.business import (
    MetricCalculationService,
    DialogSection, 
    Metric,
    MetricGroup,
    Score, 
    ScoreLabel,
    MetricMetadata,
    MetricType,
    ScoreTransformationService,
    Logger,
    IdGenerator
)
from app.services.evaluation.business.value_objects import VoicePerformance, VisualPerformance


class VerbalVisualMetricCalculationService(MetricCalculationService):
    """
    Verbal and visual metric calculation service implementation.
    
    Extracts scores from dialog message nonverbal performance data for:
    - Verbal metrics: PACE, INTONATION, VOLUME, PRONOUNCIATION, PAUSE
    - Visual metrics: EYE_CONTACT, FACIAL_EXPRESSION, POSTURE, PERSONAL_APPEARANCE
    """
    
    def __init__(self, logger: Logger, id_generator: IdGenerator, score_transformation_service: ScoreTransformationService):
        """
        Initialize the service.
        
        Args:
            logger: Logger instance for logging operations
            id_generator: ID generator for creating unique metric IDs
            score_transformation_service: Service for transforming between score labels and numeric scores
        """
        self.logger = logger
        self.id_generator = id_generator
        self.score_transformation_service = score_transformation_service
        
        # Mapping from metric types to their corresponding score label field names
        self._score_label_field_mapping = {
            # Verbal performance metrics
            MetricType.PACE: "speed_score_label",  # PACE maps to speed in voice performance
            MetricType.INTONATION: "tone_score_label",  # INTONATION maps to tone
            MetricType.VOLUME: "volume_score_label",
            MetricType.PRONOUNCIATION: "pronunciation_score_label",
            MetricType.PAUSE: "pause_score_label",
            
            # Visual performance metrics  
            MetricType.EYE_CONTACT: "eye_contact_score_label",
            MetricType.FACIAL_EXPRESSION: "facial_expression_score_label",
            MetricType.POSTURE: "body_posture_score_label",  # POSTURE maps to body_posture
            MetricType.PERSONAL_APPEARANCE: "appearance_score_label",  # PERSONAL_APPEARANCE maps to appearance
        }
    
    def _translate_score_label_to_score(self, score_label_str: Optional[str]) -> Score:
        """
        Translate string score label to Score object with numeric value.
        
        Args:
            score_label_str: String score label ("Good", "Fair", "Poor", or None)
            
        Returns:
            Score: Score object with appropriate label and numeric value
        """
        if not score_label_str:
            # Default to FAIR if no score label provided
            return self.score_transformation_service.create_score(ScoreLabel.FAIR)
        
        score_label_upper = score_label_str.upper()
        
        if score_label_upper == "GOOD":
            return self.score_transformation_service.create_score(ScoreLabel.GOOD)
        elif score_label_upper == "FAIR":
            return self.score_transformation_service.create_score(ScoreLabel.FAIR)
        elif score_label_upper == "POOR":
            return self.score_transformation_service.create_score(ScoreLabel.POOR)
        elif score_label_upper == "CRITICAL":
            # Special case: Return POOR label but with 0.0 numeric score
            return self.score_transformation_service.create_score(ScoreLabel.POOR, numeric_score=0.0)
        else:
            # Unknown score label, default to FAIR
            self.logger.warning("Unknown score label encountered", None, {
                "score_label": score_label_str,
                "service": "VerbalVisualMetricCalculationService"
            })
            return self.score_transformation_service.create_score(ScoreLabel.FAIR)
    
    def _extract_metric_specific_voice_data(self, voice_performance: VoicePerformance, metric_type: MetricType) -> Dict[str, Any]:
        """
        Extract only the voice performance data relevant to the specific metric type.
        
        Args:
            voice_performance: VoicePerformance object
            metric_type: The specific metric type being processed
            
        Returns:
            Dict containing only the relevant performance data for this metric
        """
        if metric_type == MetricType.PACE:
            return {
                "speed": voice_performance.speed,
                "speed_score_label": voice_performance.speed_score_label,
            }
        elif metric_type == MetricType.INTONATION:
            return {
                "tone": voice_performance.tone,
                "tone_score_label": voice_performance.tone_score_label,
            }
        elif metric_type == MetricType.VOLUME:
            return {
                "volume": voice_performance.volume,
                "volume_score_label": voice_performance.volume_score_label,
            }
        elif metric_type == MetricType.PRONOUNCIATION:
            return {
                "pronunciation": voice_performance.pronunciation,
                "pronunciation_score_label": voice_performance.pronunciation_score_label,
            }
        elif metric_type == MetricType.PAUSE:
            return {
                "pause": voice_performance.pause,
                "pause_score_label": voice_performance.pause_score_label,
            }
        else:
            # Fallback: return empty dict for unsupported verbal metrics
            return {}
    
    def _extract_metric_specific_visual_data(self, visual_performance: VisualPerformance, metric_type: MetricType) -> Dict[str, Any]:
        """
        Extract only the visual performance data relevant to the specific metric type.
        
        Args:
            visual_performance: VisualPerformance object
            metric_type: The specific metric type being processed
            
        Returns:
            Dict containing only the relevant performance data for this metric
        """
        if metric_type == MetricType.EYE_CONTACT:
            return {
                "eye_contact": visual_performance.eye_contact,
                "eye_contact_score_label": visual_performance.eye_contact_score_label,
            }
        elif metric_type == MetricType.FACIAL_EXPRESSION:
            return {
                "facial_expression": visual_performance.facial_expression,
                "facial_expression_score_label": visual_performance.facial_expression_score_label,
            }
        elif metric_type == MetricType.POSTURE:
            return {
                "body_posture": visual_performance.body_posture,
                "body_posture_score_label": visual_performance.body_posture_score_label,
            }
        elif metric_type == MetricType.PERSONAL_APPEARANCE:
            return {
                "appearance": visual_performance.appearance,
                "appearance_score_label": visual_performance.appearance_score_label,
            }
        else:
            # Fallback: return empty dict for unsupported visual metrics
            return {}
    
    def _extract_performance_data_from_dialog_section(
        self, 
        dialog_section: DialogSection, 
        metric_type: MetricType
    ) -> Tuple[Score, Dict[str, Any]]:
        """
        Extract both score and performance data for a specific metric type from dialog section messages.
        
        Args:
            dialog_section: The dialog section to extract data from
            metric_type: The metric type to extract data for
            
        Returns:
            tuple[Score, dict]: The extracted score and performance data dict, or defaults if not found
        """
        score_label_field = self._score_label_field_mapping.get(metric_type)
        if not score_label_field:
            self.logger.warning("Unsupported metric type for verbal/visual evaluation", None, {
                "metric_type": metric_type.value,
                "service": "VerbalVisualMetricCalculationService"
            })
            return Score(score_label=ScoreLabel.FAIR, numeric_score=50.0), {}
        
        # Look for candidate messages with nonverbal performance data
        for message in dialog_section.messages:
            if message.role.value == "CANDIDATE" and message.nonverbal:
                nonverbal = message.nonverbal
                
                # Check verbal performance metrics
                if metric_type in [MetricType.PACE, MetricType.INTONATION, MetricType.VOLUME, 
                                 MetricType.PRONOUNCIATION, MetricType.PAUSE]:
                    if nonverbal.voice_performance:
                        voice_performance = nonverbal.voice_performance
                        
                        # Extract score
                        score_label_value = getattr(voice_performance, score_label_field, None)
                        score = self._translate_score_label_to_score(score_label_value) if score_label_value else Score(score_label=ScoreLabel.FAIR, numeric_score=50.0)
                        
                        # Extract performance data for sub_metrics - filter for current metric type
                        performance_data = self._extract_metric_specific_voice_data(voice_performance, metric_type)
                        # Remove None values to keep data clean
                        performance_data = {k: v for k, v in performance_data.items() if v is not None}
                        
                        return score, performance_data
                
                # Check visual performance metrics
                elif metric_type in [MetricType.EYE_CONTACT, MetricType.FACIAL_EXPRESSION, 
                                   MetricType.POSTURE, MetricType.PERSONAL_APPEARANCE]:
                    if nonverbal.visual_performance:
                        visual_performance = nonverbal.visual_performance
                        
                        # Extract score
                        score_label_value = getattr(visual_performance, score_label_field, None)
                        score = self._translate_score_label_to_score(score_label_value) if score_label_value else Score(score_label=ScoreLabel.FAIR, numeric_score=50.0)
                        
                        # Log for debugging Critical scores
                        if score_label_value and score_label_value.upper() == "CRITICAL":
                            self.logger.info("Critical score detected in visual metric", {
                                "metric_type": metric_type.value,
                                "score_label": score_label_value,
                                "numeric_score": score.numeric_score,
                                "service": "VerbalVisualMetricCalculationService"
                            })
                        
                        # Extract performance data for sub_metrics - filter for current metric type
                        performance_data = self._extract_metric_specific_visual_data(visual_performance, metric_type)
                        # Remove None values to keep data clean
                        performance_data = {k: v for k, v in performance_data.items() if v is not None}
                        
                        return score, performance_data
        
        # If no data found, return default FAIR score and empty performance data
        self.logger.info("No performance data found in dialog section, using defaults", {
            "dialog_section_id": dialog_section.id,
            "section_index": dialog_section.section_index,
            "metric_type": metric_type.value,
            "service": "VerbalVisualMetricCalculationService"
        })
        return self.score_transformation_service.create_score(ScoreLabel.FAIR), {}
    
    async def create_metric_group(
        self, 
        dialog_sections: List[DialogSection], 
        metadata: MetricMetadata
    ) -> MetricGroup:
        """
        Create a MetricGroup with verbal/visual metrics extracted from dialog messages.
        
        Args:
            dialog_sections: The dialog sections to analyze
            metadata: The metric metadata 
            
        Returns:
            MetricGroup: Complete metric group with metrics for each section
        """
        try:
            self.logger.info("Creating verbal/visual metric group", {
                "dialog_sections_count": len(dialog_sections),
                "metric_type": metadata.metric_type.value,
                "service": "VerbalVisualMetricCalculationService"
            })
            
            metrics: List[Metric] = []
            
            for dialog_section in dialog_sections:
                # Generate unique metric ID for each section
                metric_id = self.id_generator.generate()
                
                self.logger.info("Processing dialog section for verbal/visual metric", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "metric_type": metadata.metric_type.value,
                    "service": "VerbalVisualMetricCalculationService"
                })
                
                # Extract both score and performance data from dialog section messages
                score, performance_data = self._extract_performance_data_from_dialog_section(dialog_section, metadata.metric_type)
                
                # Create metric entity for this section
                metric = Metric(
                    id=metric_id,
                    metadata=metadata,
                    dialog_section_id=dialog_section.id,
                    dialog_section_index=dialog_section.section_index,
                    sub_metrics=performance_data,  # Include verbal/visual performance data
                    score=score,
                    revision=""  # No revision for verbal/visual metrics
                )
                
                metrics.append(metric)
                
                self.logger.info("Successfully created verbal/visual metric for section", {
                    "dialog_section_id": dialog_section.id,
                    "section_index": dialog_section.section_index,
                    "metric_id": metric_id,
                    "metric_type": metadata.metric_type.value,
                    "score": {
                        "label": score.score_label.value,
                        "numeric": score.numeric_score
                    },
                    "sub_metrics_count": len(performance_data),
                    "service": "VerbalVisualMetricCalculationService"
                })
            
            # Create metric group
            metric_group = MetricGroup(
                metric_type=metadata.metric_type,
                metrics=metrics
            )
            
            self.logger.info("Successfully created verbal/visual metric group", {
                "dialog_sections_count": len(dialog_sections),
                "metrics_count": len(metrics),
                "metric_type": metadata.metric_type.value,
                "service": "VerbalVisualMetricCalculationService"
            })
            
            return metric_group
            
        except Exception as e:
            self.logger.error("Failed to create verbal/visual metric group", e, {
                "dialog_sections_count": len(dialog_sections),
                "metric_type": metadata.metric_type.value if metadata else "unknown",
                "service": "VerbalVisualMetricCalculationService"
            })
            raise