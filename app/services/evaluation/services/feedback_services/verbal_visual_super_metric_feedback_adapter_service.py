"""
Verbal and Visual super-metric feedback adapter service implementation.
"""
from typing import List

from app.services.evaluation.business import (
    SuperMetricFeedbackService,
    SimpleSectionFeedbackService,
    SuperMetric,
    SuperMetricType,
    SuperMetricFeedback,
    DialogSection,
)


class VerbalVisualSuperMetricFeedbackAdapterService(SuperMetricFeedbackService, SimpleSectionFeedbackService):
    """
    Adapter implementation of SuperMetricFeedbackService that specifically handles 
    feedback generation for VERBAL_PERFORMANCE and VISUAL_PERFORMANCE super-metrics.
    
    This adapter wraps an existing SuperMetricFeedbackService and filters the input
    to only process verbal and visual performance related super-metrics, delegating
    the actual feedback generation to the wrapped service.
    """
    
    def __init__(self, wrapped_service: SuperMetricFeedbackService):
        """
        Initialize the verbal/visual super-metric feedback adapter service.
        
        Args:
            wrapped_service: The underlying SuperMetricFeedbackService to delegate to
        """
        self.wrapped_service = wrapped_service
    
    async def generate_and_update_feedback(self, super_metrics: List[SuperMetric]) -> List[SuperMetric]:
        """
        Generate and update feedback for verbal and visual performance super-metrics only.
        
        This method filters the input super-metrics to only include VERBAL_PERFORMANCE 
        and VISUAL_PERFORMANCE types, then delegates to the wrapped service for actual
        feedback generation. Other super-metric types are returned unchanged.
        
        Args:
            super_metrics: List of super-metrics to generate feedback for
            
        Returns:
            List[SuperMetric]: Updated super-metrics with generated feedback for 
                             verbal/visual types, others unchanged
        """
        # Define the super-metric types this adapter handles
        unhandled_types = {SuperMetricType.VERBAL_PERFORMANCE, SuperMetricType.VISUAL_PERFORMANCE}
        
        # Split super-metrics into handled and unhandled groups
        handled_super_metrics = [
            sm for sm in super_metrics 
            if sm.metadata.super_metric_type not in unhandled_types
        ]
        unhandled_super_metrics = [
            sm for sm in super_metrics 
            if sm.metadata.super_metric_type in unhandled_types
        ]
        
        # Generate feedback only for handled super-metrics
        updated_handled_super_metrics = []
        if handled_super_metrics:
            updated_handled_super_metrics = await self.wrapped_service.generate_and_update_feedback(
                handled_super_metrics
            )
        
        # Combine updated handled metrics with unchanged unhandled metrics
        # Maintain original order by using the original list as reference
        result: List[SuperMetric] = []
        handled_iter = iter(updated_handled_super_metrics)
        unhandled_iter = iter(unhandled_super_metrics)
        
        for original_super_metric in super_metrics:
            if original_super_metric.metadata.super_metric_type in unhandled_types:
                # Use original version for unhandled types
                result.append(next(unhandled_iter))
            else:
                # Use updated version for handled types
                result.append(next(handled_iter))
        
        return result
    
class VerbalVisualSimpleSectionFeedbackAdapterService(SimpleSectionFeedbackService):

    def __init__(self, wrapped_service: SimpleSectionFeedbackService):
        """
        Initialize the verbal/visual super-metric feedback adapter service.
        
        Args:
            wrapped_service: The underlying SuperMetricFeedbackService to delegate to
        """
        self.wrapped_service = wrapped_service

    async def generate_feedback_for_super_metric(
        self, 
        section: DialogSection, 
        super_metric: SuperMetric
    ) -> SuperMetricFeedback:
        """
        Generate feedback for a specific super-metric using mock data.
        
        This method generates mock feedback based on the super-metric type,
        using the same mock data patterns as DummySuperMetricCalculationService.
        
        Args:
            section: The dialog section (unused in mock implementation)
            super_metric: The super-metric to generate feedback for
            
        Returns:
            SuperMetricFeedback: Mock feedback data based on super-metric type
            
        Raises:
            ValueError: If the super-metric type is not supported
        """
        super_metric_type = super_metric.metadata.super_metric_type
        
        if super_metric_type == SuperMetricType.VERBAL_PERFORMANCE:
            return SuperMetricFeedback(
                brief_feedback="全体的に、あなたの話し方は速く、特に説明が長くなるにつれて不明瞭になる傾向が見られました。",
                revised_response="",
                feedback="これは、聞き手が内容を理解するのを難しくし、あなた自身が自信がない、あるいは緊張しているという印象を与えかねません。例えば、「大新設の方と漢字、そしてある程度の社会選挙事件を設ける新人さんにお分けでやったわけですよ」や「取り的にコが失踪した後に、社内で評価するとコンペを防ぐことを考えています」といった箇所では、言葉が詰まったり、発音が不明瞭で聞き取りにくい部分がありました。話す速度を意識的に落とし、特に重要なポイントでは区切りを入れることで、より明確に、そして自信を持って話すことができるでしょう。",
                section_index=section.section_index
            )
        elif super_metric_type == SuperMetricType.VISUAL_PERFORMANCE:
            return SuperMetricFeedback(
                brief_feedback="全体的なプレゼンスを向上させ、より自信を持って見えるようにするための具体的なアドバイスを以下に示します。",
                revised_response="",
                feedback="まず、プレゼンスの基本は、そもそも「その場にいること」です。この動画では、大半の時間フレームから姿を消していました。これは視聴者の注意を著しく削ぎ、対話が中断されているという強い印象を与えます。会話のロールプレイである以上、始めから終わりまでカメラの前にいることが不可欠です。\n\n次に、あなたが画面にいる際の姿勢と向きが重要です。",
                section_index=section.section_index
            )
        else:
            # forward to the wrapped service for other types
            return await self.wrapped_service.generate_feedback_for_super_metric(
                section, 
                super_metric
            )