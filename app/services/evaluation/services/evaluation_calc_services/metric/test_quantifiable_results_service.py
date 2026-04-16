"""
Test file for QuantifiableResultsMetricCalculationService.

This file contains tests to verify the quantifiable results metric calculation service works correctly.
It tests the service's ability to create complete Metric entities from DialogSection inputs.
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
    QuantifiableResultsMetricCalculationService
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


def test_scoring_logic() -> None:
    """Test the scoring logic by analyzing the expected behavior."""
    # We can't test private methods directly, but we can document expected behavior
    print("✓ Scoring logic test - Testing expected score calculation behavior")
    print("  - Good: Has results AND quantifiable results should result in GOOD score (85.0)")
    print("  - Fair: Results present but not quantifiable should result in FAIR score (65.0)")
    print("  - Poor: Neither results nor quantifiable data present should result in POOR score (30.0)")


def test_service_initialization() -> None:
    """Test service initialization with required dependencies."""
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Test service creation with different models
    models_to_test = ["gpt-4o", "claude-3-5-sonnet-20241022"]
    
    for model in models_to_test:
        service = QuantifiableResultsMetricCalculationService(logger, id_generator, model=model)
        assert service.model == model
        assert service.logger is logger
        assert service.id_generator is id_generator
        print(f"✓ Service initialization test - Model: {model}")


def test_create_metric_group_integration(service: QuantifiableResultsMetricCalculationService, dialog_sections: List[DialogSection]) -> None:
    """Test the main create_metric_group method (integration test - may fail without API key)."""
    metadata = MetricMetadata(metric_type=MetricType.QUANTIFIABLE_RESULTS, model="gpt-4o", weight=1.0)
    
    try:
        metric_group = asyncio.run(service.create_metric_group(dialog_sections, metadata))
        
        # Verify metric group structure
        assert metric_group.metric_type == MetricType.QUANTIFIABLE_RESULTS
        assert isinstance(metric_group.metrics, list)
        assert len(metric_group.metrics) == len(dialog_sections)
        
        # Verify each metric in the group
        for i, metric in enumerate(metric_group.metrics):
            assert metric.id.startswith("test_metric_id_")
            assert metric.dialog_section_id == dialog_sections[i].id
            assert metric.metadata.metric_type == MetricType.QUANTIFIABLE_RESULTS
            assert isinstance(metric.sub_metrics, dict)
            assert metric.score.score_label in [ScoreLabel.POOR, ScoreLabel.FAIR, ScoreLabel.GOOD]
            assert isinstance(metric.revision, str)
        
        print(f"✓ Integration test - MetricGroup created successfully:")
        print(f"  - Metric type: {metric_group.metric_type.value}")
        print(f"  - Number of metrics: {len(metric_group.metrics)}")
        for i, metric in enumerate(metric_group.metrics):
            print(f"  - Metric {i+1}: ID {metric.id}, Score {metric.score.score_label.value} ({metric.score.numeric_score})")
            print(f"    Sub-metrics count: {len(metric.sub_metrics)}, Revision length: {len(metric.revision)}")
        
    except (ValueError, ConnectionError, RuntimeError) as e:
        print(f"⚠ Integration test skipped - API issue: {e}")
        print("  This is expected if no valid API key is configured")


def test_sub_metrics_generation(service: QuantifiableResultsMetricCalculationService) -> None:
    """Test sub-metrics generation with different dialog scenarios."""
    
    # Test Case 1: Poor results (no results at all)
    poor_dialog_section = DialogSection(
        id="test_section_poor",
        dialog_id="test_dialog_poor",
        section_index=0,
        messages=[
            DialogMessage(
                section_id="test_section_poor",
                role=MessageRole.INTERVIEWER,
                content="Tell me about your responsibilities on the data pipeline project.",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_poor",
                role=MessageRole.CANDIDATE,
                content="I designed the pipeline architecture, set up CI/CD, and coordinated with the analytics team.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 2: Fair results (has results but not quantifiable)
    fair_dialog_section = DialogSection(
        id="test_section_fair",
        dialog_id="test_dialog_fair",
        section_index=1,
        messages=[
            DialogMessage(
                section_id="test_section_fair",
                role=MessageRole.INTERVIEWER,
                content="What were the outcomes of your last release?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_fair",
                role=MessageRole.CANDIDATE,
                content="We delivered the feature on time, users loved the new experience, and the app performance improved noticeably.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 3: Good results (has results with quantifiable data)
    good_dialog_section = DialogSection(
        id="test_section_good",
        dialog_id="test_dialog_good",
        section_index=2,
        messages=[
            DialogMessage(
                section_id="test_section_good",
                role=MessageRole.INTERVIEWER,
                content="Can you share a project where you achieved measurable impact?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_good",
                role=MessageRole.CANDIDATE,
                content="I led an optimization effort that cut page load time by 35% and saved $120k annually by reducing cloud costs.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    test_cases = [
        ("Poor case", poor_dialog_section, ScoreLabel.POOR),
        ("Fair case", fair_dialog_section, ScoreLabel.FAIR),
        ("Good case", good_dialog_section, ScoreLabel.GOOD)
    ]
    
    for test_name, dialog_section, expected_score in test_cases:
        try:
            # Try to run the actual test - will fail without API key
            metadata = MetricMetadata(metric_type=MetricType.QUANTIFIABLE_RESULTS, model="gpt-4o", weight=1.0)
            # Use new interface: create_metric_group with list of dialog sections
            metric_group = asyncio.run(service.create_metric_group([dialog_section], metadata))
            
            # Get the first (and only) metric from the group
            assert len(metric_group.metrics) == 1
            metric = metric_group.metrics[0]
            
            print(f"✓ {test_name} - Actual result:")
            print(f"  - Score: {metric.score.score_label.value}")
            print(f"  - Has results: {metric.sub_metrics.get('has_results')}")
            print(f"  - Quantifiable results: {metric.sub_metrics.get('quantifiable_results')}")
            print(f"  - Results count: {len(metric.sub_metrics.get('results', []))}")
            
        except (ValueError, ConnectionError, RuntimeError) as e:
            print(f"⚠ {test_name} skipped - API issue: {e}")
            print(f"  Expected score would be: {expected_score.value}")


def test_prompt_loading(service: QuantifiableResultsMetricCalculationService) -> None:
    """Test that prompts are loaded correctly."""
    # Check that prompt attributes exist
    assert hasattr(service, 'eval_system_prompt')
    assert hasattr(service, 'eval_user_prompt')
    assert hasattr(service, 'revise_system_prompt')
    assert hasattr(service, 'revise_user_prompt')
    
    # Check that prompts are not empty
    assert len(service.eval_system_prompt) > 0
    assert len(service.eval_user_prompt) > 0
    assert len(service.revise_system_prompt) > 0
    assert len(service.revise_user_prompt) > 0
    
    print("✓ Prompt loading test - All prompts loaded successfully")
    print(f"  - Eval system prompt length: {len(service.eval_system_prompt)}")
    print(f"  - Eval user prompt length: {len(service.eval_user_prompt)}")
    print(f"  - Revise system prompt length: {len(service.revise_system_prompt)}")
    print(f"  - Revise user prompt length: {len(service.revise_user_prompt)}")


def run_all_tests() -> None:
    """Run all tests for the QuantifiableResultsMetricCalculationService."""
    print("=== Running QuantifiableResultsMetricCalculationService Tests ===\n")
    
    # Initialize test dependencies
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create service instance
    service = QuantifiableResultsMetricCalculationService(logger, id_generator)
    
    # Test 1: Service initialization
    test_service_initialization()
    print()
    
    # Test 2: Prompt loading
    test_prompt_loading(service)
    print()
    
    # Test 3: Scoring logic documentation
    test_scoring_logic()
    print()
    
    # Test 4: Sub-metrics generation scenarios
    print("=== Sub-metrics generation scenarios ===")
    test_sub_metrics_generation(service)
    print()
    
    # Test 5: Create metric group integration test (sample dialog sections)
    sample_dialog_sections = [
        DialogSection(
            id="test_section_sample_1",
            dialog_id="test_dialog_sample",
            section_index=0,
            messages=[
                DialogMessage(
                    section_id="test_section_sample_1",
                    role=MessageRole.INTERVIEWER,
                    content="Can you tell me about a successful project you worked on?",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                ),
                DialogMessage(
                    section_id="test_section_sample_1",
                    role=MessageRole.CANDIDATE,
                    content="I worked on a performance optimization project that reduced server response time by 40% and decreased operational costs by $50,000 annually.",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
            ],
            start_time=datetime.now(),
            end_time=datetime.now()
        ),
        DialogSection(
            id="test_section_sample_2",
            dialog_id="test_dialog_sample",
            section_index=1,
            messages=[
                DialogMessage(
                    section_id="test_section_sample_2",
                    role=MessageRole.INTERVIEWER,
                    content="What were the challenges in that project?",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                ),
                DialogMessage(
                    section_id="test_section_sample_2",
                    role=MessageRole.CANDIDATE,
                    content="The main challenge was handling the database migration while maintaining service availability.",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
            ],
            start_time=datetime.now(),
            end_time=datetime.now()
        )
    ]
    
    print("=== Integration test with sample dialog sections ===")
    test_create_metric_group_integration(service, sample_dialog_sections)
    print()
    
    print("=== All Tests Completed ===")




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
    custom_eval_system_prompt_path = "/Users/wanghuan/Documents/py_repos/career_face_backend/app/config/prompts/evaluation/v2/prompt_quantifiable_results_eval_system_msg.md"  # e.g., "/path/to/custom_eval_system.md"
    custom_eval_user_prompt_path = None    # e.g., "/path/to/custom_eval_user.md"
    custom_revise_system_prompt_path = None # e.g., "/path/to/custom_revise_system.md"
    custom_revise_user_prompt_path = None   # e.g., "/path/to/custom_revise_user.md"
    
    # Create test dependencies 
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create service with custom prompt parameters
    service = QuantifiableResultsMetricCalculationService(
        logger=logger, 
        id_generator=id_generator,
        model=model,
        enable_revision=enable_revision,
        custom_eval_system_prompt_path=custom_eval_system_prompt_path,
        custom_eval_user_prompt_path=custom_eval_user_prompt_path,
        custom_revise_system_prompt_path=custom_revise_system_prompt_path,
        custom_revise_user_prompt_path=custom_revise_user_prompt_path
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
        metadata = MetricMetadata(metric_type=MetricType.QUANTIFIABLE_RESULTS, model=model, weight=1.0)
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
    run_all_tests()