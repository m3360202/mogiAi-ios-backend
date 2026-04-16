"""
Test file for GrowthMetricCalculationService.

This file contains tests to verify the growth metric calculation service works correctly.
It tests the service's ability to create complete MetricGroup entities from DialogSection inputs.
"""
import asyncio
import json
import time
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, Optional, List

from app.services.evaluation.business import (
    DialogSection, 
    DialogMessage,
    MessageRole, 
    MetricMetadata,
    MetricType,
    MetricGroup,
    Logger,
    IdGenerator,
    ScoreLabel
)
from app.services.evaluation.services.evaluation_calc_services.metric import (
    GrowthMetricCalculationService
)


class TestLogger(Logger):
    """Simple test logger implementation."""
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"DEBUG: {message} - Context: {context}")
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"INFO: {message} - Context: {context}")
    
    def warning(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"WARNING: {message} - Error: {error} - Context: {context}")
    
    def error(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"ERROR: {message} - Error: {error} - Context: {context}")


class TestIdGenerator(IdGenerator):
    """Simple test ID generator implementation."""
    
    def __init__(self):
        self.counter = 0
    
    def generate(self) -> str:
        self.counter += 1
        return f"test_metric_id_{self.counter}"


def test_growth_metric_calculation_service():
    """Test the GrowthMetricCalculationService with sample dialog."""
    
    # Create test dependencies
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create test dialog sections with learning and growth content
    messages = [
        DialogMessage(
            section_id="test_dialog_section_1",
            role=MessageRole.INTERVIEWER,
            content="Can you share a challenging situation you faced and what you learned from it?",
            start_time=datetime.now(),
            end_time=datetime.now()
        ),
        DialogMessage(
            section_id="test_dialog_section_1",
            role=MessageRole.CANDIDATE,
            content="I struggled with time management during a big project, which caused delays. I learned to prioritize tasks better and plan ahead. In the future, I will use a project management tool to track deadlines and allocate time more effectively.",
            start_time=datetime.now(),
            end_time=datetime.now()
        )
    ]
    
    dialog_sections = [DialogSection(
        id="test_dialog_section_1",
        dialog_id="test_dialog_1",
        section_index=0,
        messages=messages,
        start_time=datetime.now(),
        end_time=datetime.now()
    )]
    
    # Create test metadata
    metadata = MetricMetadata(
        metric_type=MetricType.GROWTH,
        model="gpt-4o"
    )
    
    # Initialize service
    service = GrowthMetricCalculationService(logger, id_generator, "gpt-4o")
    
    # Test metric group creation
    try:
        metric_group = asyncio.run(service.create_metric_group(dialog_sections, metadata))
        
        # Verify metric group was created
        print(f"Metric Type: {metric_group.metric_type.value}")
        print(f"Number of Metrics: {len(metric_group.metrics)}")
        
        # Verify first metric
        metric = metric_group.metrics[0]
        print(f"Metric ID: {metric.id}")
        print(f"Dialog Section ID: {metric.dialog_section_id}")
        print(f"Score Label: {metric.score.score_label.value}")
        print(f"Numeric Score: {metric.score.numeric_score}")
        print(f"Sub-metrics: {metric.sub_metrics}")
        print(f"Revision: {metric.revision}")
        
        # Verify sub-metrics structure
        assert "are_lessons_learned" in metric.sub_metrics
        assert "key_takeaways" in metric.sub_metrics
        assert "will_change_approach" in metric.sub_metrics
        assert "approach_changes" in metric.sub_metrics
        
        print("✅ Growth metric calculation service test passed!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        raise


def test_growth_metric_poor_case():
    """Test the GrowthMetricCalculationService with poor growth content."""
    
    # Create test dependencies
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create test dialog sections with no learning or growth
    messages = [
        DialogMessage(
            section_id="test_dialog_section_2",
            role=MessageRole.INTERVIEWER,
            content="Can you describe a time when you had to adapt to a new situation?",
            start_time=datetime.now(),
            end_time=datetime.now()
        ),
        DialogMessage(
            section_id="test_dialog_section_2",
            role=MessageRole.CANDIDATE,
            content="I had to work with a new team, but I just followed their lead and completed my tasks as assigned.",
            start_time=datetime.now(),
            end_time=datetime.now()
        )
    ]
    
    dialog_sections = [DialogSection(
        id="test_dialog_section_2",
        dialog_id="test_dialog_1",
        section_index=0,
        messages=messages,
        start_time=datetime.now(),
        end_time=datetime.now()
    )]
    
    # Create test metadata
    metadata = MetricMetadata(
        metric_type=MetricType.GROWTH,
        model="gpt-4o"
    )
    
    # Initialize service
    service = GrowthMetricCalculationService(logger, id_generator, "gpt-4o")
    
    # Test metric group creation
    try:
        metric_group = asyncio.run(service.create_metric_group(dialog_sections, metadata))
        
        # Verify first metric (poor score)
        metric = metric_group.metrics[0]
        print(f"Score Label: {metric.score.score_label.value}")
        print(f"Numeric Score: {metric.score.numeric_score}")
        print(f"Sub-metrics: {metric.sub_metrics}")
        print(f"Revision: {metric.revision}")
        
        # Should have revision for poor/fair scores
        assert len(metric.revision) > 0, "Poor scores should have revision text"
        
        print("✅ Growth metric poor case test passed!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        raise




def load_dialog_sections_from_json(json_file_path: str, section_index: Optional[int] = None) -> List[DialogSection]:
    """
    Load dialog sections from a JSON file like CV7qpRZ6yaYTvaNsK4e2X3.json.
    
    Args:
        json_file_path: Path to the JSON file containing dialog data
        section_index: Optional specific section index to load (loads all if None)
        
    Returns:
        List[DialogSection]: Parsed dialog sections
    """
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    dialog_sections: List[DialogSection] = []
    
    sections_to_process = (
        [data["sections"][section_index]] if section_index is not None 
        else data.get("sections", [])
    )
    
    for section_data in sections_to_process:
        # Convert section data to DialogSection using model_validate
        section = DialogSection.model_validate(section_data)
        dialog_sections.append(section)
    
    return dialog_sections


def test_experimental_prompts() -> None:
    """
    Experimental test method to try different prompts and see output JSON with timing.
    All configuration is done in the "given" section below.
    """
    
    # GIVEN - Test Configuration
    json_file_path = "/Users/wanghuan/Documents/py_repos/career_face_backend/test/dialogs/CV7qpRZ6yaYTvaNsK4e2X3.json"
    section_index = None  # Set to specific index (0, 1, etc.) to test only one section, or None for all
    model = "gpt-4o-mini"  # Can change to "claude-3-5-sonnet-20241022" etc.
    enable_revision = False
    
    # Custom prompt paths (set to None to use defaults)
    custom_eval_system_prompt_path = "/Users/wanghuan/Documents/py_repos/career_face_backend/app/config/prompts/evaluation/v2/prompt_growth_eval_system_msg.md"  # e.g., "/path/to/custom_eval_system.md"
    custom_eval_user_prompt_path = None    # e.g., "/path/to/custom_eval_user.md"
    custom_revise_system_prompt_path = None # e.g., "/path/to/custom_revise_system.md"
    custom_revise_user_prompt_path = None   # e.g., "/path/to/custom_revise_user.md"
    
    # Create test dependencies 
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create service with custom prompt parameters
    service = GrowthMetricCalculationService(
        logger=logger, 
        id_generator=id_generator,
        model=model,
        enable_revision=enable_revision,
        eval_system_prompt_path=custom_eval_system_prompt_path,
        eval_user_prompt_path=custom_eval_user_prompt_path,
        revise_system_prompt_path=custom_revise_system_prompt_path,
        revise_user_prompt_path=custom_revise_user_prompt_path
    )
    
    try:
        print("🧪 EXPERIMENTAL PROMPT TEST")
        print("=" * 50)
        print(f"JSON File: {json_file_path}")
        print(f"Model: {model}")
        print(f"Enable Revision: {enable_revision}")
        if custom_eval_system_prompt_path:
            print(f"Custom Eval System Prompt: {custom_eval_system_prompt_path}")
        if custom_revise_system_prompt_path:
            print(f"Custom Revise System Prompt: {custom_revise_system_prompt_path}")
        print("-" * 50)
        
        # Load dialog sections from JSON file
        dialog_sections = load_dialog_sections_from_json(json_file_path, section_index)
        print(f"Sections to test: {len(dialog_sections)}")
        
        # Track overall timing and cost
        start_time = time.time()
        
        # Test the metric calculation with timing
        metadata = MetricMetadata(metric_type=MetricType.GROWTH, model=model, weight=1.0)
        metric_group = asyncio.run(service.create_metric_group(dialog_sections, metadata))
        
        end_time = time.time()
        total_elapsed = end_time - start_time
        
        # Display results for each section
        print("\n📊 RESULTS:")
        print(f"Total Processing Time: {total_elapsed:.3f} seconds")
        print(f"{metric_group.model_dump_json(indent=2)}")
        
        print("\n" + "=" * 50)
        print("✅ Experimental test completed successfully!")
        
    except Exception as e:
        print(f"❌ Experimental test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Testing GrowthMetricCalculationService...")
    print("\n--- Test 1: Good Growth Case ---")
    test_growth_metric_calculation_service()
    print("\n--- Test 2: Poor Growth Case ---")
    test_growth_metric_poor_case()
    print("\n🎉 All tests completed!")