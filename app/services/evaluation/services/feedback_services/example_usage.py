"""
Example usage of VerbalVisualSuperMetricFeedbackAdapterService.

This example demonstrates how to use the adapter service to filter
and process only verbal and visual performance super-metrics.
"""


def example_usage() -> None:
    """
    Example demonstrating how to use the VerbalVisualSuperMetricFeedbackAdapterService.
    """
    # Assume we have these dependencies available
    # logger = ...  # Logger implementation
    # dialog_section_repo = ...  # DialogSectionRepo implementation
    
    # Create the underlying feedback service
    # default_service = DefaultSuperMetricFeedbackService(
    #     logger=logger, 
    #     dialog_section_repo=dialog_section_repo
    # )
    
    # Create the adapter service that only handles verbal/visual metrics
    # adapter_service = VerbalVisualSuperMetricFeedbackAdapterService(default_service)
    
    # Example super-metrics list (would normally come from evaluation process)
    # super_metrics: List[SuperMetric] = [...]  # Contains various super-metric types
    
    # The adapter will:
    # 1. Filter to only VERBAL_PERFORMANCE and VISUAL_PERFORMANCE super-metrics
    # 2. Generate feedback for those using the wrapped service
    # 3. Return all super-metrics with feedback updated for verbal/visual types only
    # updated_super_metrics = adapter_service.generate_and_update_feedback(super_metrics)
    
    print("Example usage documented in comments above")


if __name__ == "__main__":
    example_usage()