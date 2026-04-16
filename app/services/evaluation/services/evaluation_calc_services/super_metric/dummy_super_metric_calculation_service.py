"""
Dummy Super-Metric Calculation Service.

This service provides a basic implementation of SuperMetricCalculationService for testing
and development purposes. It generates dummy super-metrics with fixed dummy scores and empty feedback.
"""
from typing import List
from app.services.evaluation.business import (
    SuperMetricCalculationService,
    MetricGroup,
    SuperMetricMetadata,
    SuperMetric,
    Score,
    ScoreLabel,
    SuperMetricSectionScore,
    SuperMetricFeedback,
    Logger,
    SuperMetricType,
)


class DummySuperMetricCalculationService(SuperMetricCalculationService):
    """
    Dummy implementation of SuperMetricCalculationService for testing purposes.
    
    This service creates super-metrics with:
    - Fixed dummy overall score (POOR, 0.0)
    - Empty section scores
    - Empty feedback placeholders
    """
    
    def __init__(self, logger: Logger):
        """
        Initialize the dummy super-metric calculation service.
        
        Args:
            logger: Logger service for logging operations
        """
        self.logger = logger
    
    def create_super_metric(
        self, 
        metric_groups: List[MetricGroup], 
        metadata: SuperMetricMetadata
    ) -> SuperMetric:
        """
        Create a dummy SuperMetric entity with fixed values.
        
        Creates a super-metric with:
        - Overall score: POOR with numeric value 0.0
        - Empty section scores list
        - Empty feedback placeholders
        
        Args:
            metric_groups: List of metric groups to analyze (ignored in dummy implementation)
            metadata: The super-metric metadata defining the type and configuration
            
        Returns:
            SuperMetric: Dummy super-metric with fixed values
        """
        try:
            self.logger.info("Creating dummy super-metric", {
                "super_metric_type": metadata.super_metric_type.value,
                "metric_groups_count": len(metric_groups),
                "service": "DummySuperMetricCalculationService"
            })
            
            # Create dummy overall score
            dummy_overall_score = Score(
                score_label=ScoreLabel.FAIR,
                numeric_score=75
            )
            
            # Create empty section scores list
            dummy_section_scores: List[SuperMetricSectionScore] = []
            
            # Create dummy feedback
            dummy_feedback = self._calculate_feedback(metadata)
            
            # Create super-metric with dummy values
            super_metric = SuperMetric(
                metadata=metadata,
                metric_groups=metric_groups,
                score=dummy_overall_score,
                section_scores=dummy_section_scores,
                feedback=dummy_feedback
            )
            
            self.logger.info("Successfully created dummy super-metric", {
                "super_metric_type": metadata.super_metric_type.value,
                "overall_score_label": dummy_overall_score.score_label.value,
                "overall_numeric_score": dummy_overall_score.numeric_score,
                "section_scores_count": len(dummy_section_scores),
                "service": "DummySuperMetricCalculationService"
            })
            
            return super_metric
            
        except Exception as e:
            self.logger.error("Failed to create dummy super-metric", e, {
                "super_metric_type": metadata.super_metric_type.value,
                "metric_groups_count": len(metric_groups),
                "service": "DummySuperMetricCalculationService"
            })
            raise

    
    def _calculate_feedback(self, metadata: SuperMetricMetadata) -> SuperMetricFeedback:
        """
        Generate dummy feedback for the super-metric.
        
        Args:
            metadata: The super-metric metadata defining the type and configuration

        Returns:
            SuperMetricFeedback: Dummy feedback with placeholder text
        """

        if metadata.super_metric_type == SuperMetricType.VERBAL_PERFORMANCE:
            return SuperMetricFeedback(
                brief_feedback="全体的に、あなたの話し方は速く、特に説明が長くなるにつれて不明瞭になる傾向が見られました。",
                revised_response="",
                feedback="これは、聞き手が内容を理解するのを難しくし、あなた自身が自信がない、あるいは緊張しているという印象を与えかねません。例えば、「大新設の方と漢字、そしてある程度の社会選挙事件を設ける新人さんにお分けでやったわけですよ」や「取り的にコが失踪した後に、社内で評価するとコンペを防ぐことを考えています」といった箇所では、言葉が詰まったり、発音が不明瞭で聞き取りにくい部分がありました。話す速度を意識的に落とし、特に重要なポイントでは区切りを入れることで、より明確に、そして自信を持って話すことができるでしょう。",
                section_index=0  # Placeholder index
            )
        elif metadata.super_metric_type == SuperMetricType.VISUAL_PERFORMANCE:
            return SuperMetricFeedback(
                brief_feedback="全体的なプレゼンスを向上させ、より自信を持って見えるようにするための具体的なアドバイスを以下に示します。",
                revised_response="",
                feedback="まず、プレゼンスの基本は、そもそも「その場にいること」です。この動画では、大半の時間フレームから姿を消していました。これは視聴者の注意を著しく削ぎ、対話が中断されているという強い印象を与えます。会話のロールプレイである以上、始めから終わりまでカメラの前にいることが不可欠です。\n\n次に、あなたが画面にいる際の姿勢と向きが重要です。",
                section_index=0  # Placeholder index
            )
        else:
            raise ValueError(f"Unsupported super-metric type for dummy feedback: {metadata.super_metric_type.value}")