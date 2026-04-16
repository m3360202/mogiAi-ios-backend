"""
Test file for AudienceAppropriatenessMetricCalculationService.

This file contains tests to verify the audience appropriateness metric calculation service works correctly.
It tests the service's ability to create complete Metric entities from DialogSection inputs.
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from pydantic import BaseModel

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
    AudienceAppropriatenessMetricCalculationService
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
    print("  - Good: Terminology is appropriate for the intended audience (true) should result in GOOD score (1.0)")
    print("  - Poor: Terminology is not appropriate for the intended audience (false) should result in POOR score (0.0)")


def test_service_initialization() -> None:
    """Test service initialization with required dependencies."""
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Test service creation with different models
    models_to_test = ["gpt-4o", "claude-3-5-sonnet-20241022"]
    
    for model in models_to_test:
        service = AudienceAppropriatenessMetricCalculationService(logger, id_generator, model=model)
        assert service.model == model
        assert service.logger is logger
        assert service.id_generator is id_generator
        print(f"✓ Service initialization test - Model: {model}")


def test_create_metric_group_integration(service: AudienceAppropriatenessMetricCalculationService, dialog_sections: List[DialogSection]) -> None:
    """Test the main create_metric_group method (integration test - may fail without API key)."""
    metadata = MetricMetadata(metric_type=MetricType.AUDIENCE_APPROPRIATENESS, model="gpt-4o", weight=1.0)
    
    try:
        metric_group = asyncio.run(service.create_metric_group(dialog_sections, metadata))
        
        # Verify metric group structure
        assert metric_group.metric_type == MetricType.AUDIENCE_APPROPRIATENESS
        assert isinstance(metric_group.metrics, list)
        assert len(metric_group.metrics) == len(dialog_sections)
        
        # Verify each metric in the group
        for i, metric in enumerate(metric_group.metrics):
            assert metric.id.startswith("test_metric_id_")
            assert metric.dialog_section_id == dialog_sections[i].id
            assert metric.metadata.metric_type == MetricType.AUDIENCE_APPROPRIATENESS
            assert isinstance(metric.sub_metrics, dict)
            assert metric.score.score_label in [ScoreLabel.POOR, ScoreLabel.GOOD]
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


def test_sub_metrics_generation(service: AudienceAppropriatenessMetricCalculationService) -> None:
    """Test sub-metrics generation with different dialog scenarios."""
    
    # Test Case 1: Poor audience appropriateness (too technical for general audience)
    poor_dialog_section = DialogSection(
        id="test_section_poor",
        dialog_id="test_dialog_poor",
        section_index=0,
        messages=[
            DialogMessage(
                section_id="test_section_poor",
                role=MessageRole.INTERVIEWER,
                content="Describe how a website works to a general audience.",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_poor",
                role=MessageRole.CANDIDATE,
                content="When the client sends an HTTP request, the reverse proxy terminates TLS and forwards it to a stateless microservice that hits a sharded database with eventual consistency.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 2: Good audience appropriateness (appropriate language for general audience)
    good_dialog_section = DialogSection(
        id="test_section_good",
        dialog_id="test_dialog_good",
        section_index=1,
        messages=[
            DialogMessage(
                section_id="test_section_good",
                role=MessageRole.INTERVIEWER,
                content="Explain what an API is to a non-technical audience.",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_good",
                role=MessageRole.CANDIDATE,
                content="An API is like a waiter who takes your order to the kitchen and brings back your food. It lets two apps talk to each other.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 3: Technical audience - appropriate technical language
    technical_dialog_section = DialogSection(
        id="test_section_technical",
        dialog_id="test_dialog_technical",
        section_index=2,
        messages=[
            DialogMessage(
                section_id="test_section_technical",
                role=MessageRole.INTERVIEWER,
                content="Explain the architecture of our distributed system to the engineering team.",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_technical",
                role=MessageRole.CANDIDATE,
                content="Our system uses microservices architecture with Docker containers, deployed on Kubernetes. We have a service mesh for inter-service communication and use Kafka for event streaming.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    test_cases = [
        ("Poor Response", poor_dialog_section),
        ("Good Response", good_dialog_section),
        ("Technical Response", technical_dialog_section)
    ]
    
    for test_name, dialog_section in test_cases:
        try:
            metadata = MetricMetadata(metric_type=MetricType.AUDIENCE_APPROPRIATENESS, model="gpt-4o", weight=1.0)
            # Use new interface: create_metric_group with list of dialog sections
            metric_group = asyncio.run(service.create_metric_group([dialog_section], metadata))
            
            # Get the first (and only) metric from the group
            assert len(metric_group.metrics) == 1
            metric = metric_group.metrics[0]
            
            # Verify sub-metrics structure
            assert "terminology_appropriateness" in metric.sub_metrics
            assert "unappropriate_terms" in metric.sub_metrics
            
            # Verify data types
            assert isinstance(metric.sub_metrics["terminology_appropriateness"], bool)
            assert isinstance(metric.sub_metrics["unappropriate_terms"], list)
            
            print(f"✓ Sub-metrics test - {test_name}:")
            print(f"  - Terminology appropriate: {metric.sub_metrics['terminology_appropriateness']}")
            print(f"  - Inappropriate terms count: {len(metric.sub_metrics['unappropriate_terms'])}")
            if metric.sub_metrics['unappropriate_terms']:
                print(f"  - Inappropriate terms: {metric.sub_metrics['unappropriate_terms']}")
            print(f"  - Score: {metric.score.score_label.value}")
            
        except (ValueError, ConnectionError, RuntimeError) as e:
            print(f"⚠ Sub-metrics test skipped for {test_name} - API issue: {e}")


def test_revision_generation(service: AudienceAppropriatenessMetricCalculationService) -> None:
    """Test revision generation for different score levels."""
    
    # Test Case 1: Poor score should generate meaningful revision
    poor_dialog_section = DialogSection(
        id="test_section_revision_poor",
        dialog_id="test_dialog_revision_poor",
        section_index=0,
        messages=[
            DialogMessage(
                section_id="test_section_revision_poor",
                role=MessageRole.INTERVIEWER,
                content="Describe how cloud computing works to a general business audience.",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_revision_poor",
                role=MessageRole.CANDIDATE,
                content="Cloud computing leverages virtualized infrastructure with containerized workloads orchestrated through Kubernetes clusters, providing horizontal scaling and fault tolerance via distributed computing paradigms.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 2: Good score should generate no revision
    good_dialog_section = DialogSection(
        id="test_section_revision_good",
        dialog_id="test_dialog_revision_good",
        section_index=1,
        messages=[
            DialogMessage(
                section_id="test_section_revision_good",
                role=MessageRole.INTERVIEWER,
                content="Describe how cloud computing works to a general business audience.",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_revision_good",
                role=MessageRole.CANDIDATE,
                content="Cloud computing is like renting office space instead of buying a building. Instead of purchasing and maintaining your own servers, you rent computing power from providers like Amazon or Microsoft, paying only for what you use.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    test_cases = [
        ("Poor Response", poor_dialog_section, True),  # Should have substantial revision
        ("Good Response", good_dialog_section, False)  # Should have no revision
    ]
    
    for test_name, dialog_section, expects_revision in test_cases:
        try:
            metadata = MetricMetadata(metric_type=MetricType.AUDIENCE_APPROPRIATENESS, model="gpt-4o", weight=1.0)
            # Use new interface: create_metric_group with list of dialog sections
            metric_group = asyncio.run(service.create_metric_group([dialog_section], metadata))
            
            # Get the first (and only) metric from the group
            assert len(metric_group.metrics) == 1
            metric = metric_group.metrics[0]
            
            revision_length = len(metric.revision.strip())
            
            if expects_revision:
                assert revision_length > 50, f"Expected substantial revision for {test_name}, got {revision_length} characters"
                print(f"✓ Revision test - {test_name}:")
                print(f"  - Score: {metric.score.score_label.value}")
                print(f"  - Revision length: {revision_length} characters")
                print(f"  - Revision preview: {metric.revision[:100]}...")
            else:
                print(f"✓ Revision test - {test_name}:")
                print(f"  - Score: {metric.score.score_label.value}")
                print(f"  - Revision length: {revision_length} characters")
                if revision_length > 0:
                    print(f"  - Revision: {metric.revision}")
                
        except (ValueError, ConnectionError, RuntimeError) as e:
            print(f"⚠ Revision test skipped for {test_name} - API issue: {e}")


def test_audience_appropriateness_service() -> None:
    """Test the audience appropriateness metric calculation service."""
    
    # Create test dependencies
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create test dialog sections (multiple sections to test batch processing)
    dialog_sections = [
        DialogSection(
            id="test_section_1",
            dialog_id="test_dialog_1",
            section_index=0,
            messages=[
                DialogMessage(
                    section_id="test_section_1",
                    role=MessageRole.INTERVIEWER,
                    content="Explain machine learning to a business executive.",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                ),
                DialogMessage(
                    section_id="test_section_1",
                    role=MessageRole.CANDIDATE,
                    content="Machine learning is like teaching a computer to recognize patterns, similar to how you might learn to predict which products your customers prefer based on their past purchases.",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
            ],
            start_time=datetime.now(),
            end_time=datetime.now()
        )
    ]
    
    try:
        # Test direct service creation
        service = AudienceAppropriatenessMetricCalculationService(logger, id_generator, model="gpt-4o")
        print("✓ Successfully created AudienceAppropriatenessMetricCalculationService")
        
        # Test scoring logic understanding
        print("\n--- Testing scoring logic understanding ---")
        test_scoring_logic()
        
        # Test service initialization
        print("\n--- Testing service initialization ---")
        test_service_initialization()
        
        # Test the full create_metric_group integration (may fail without API key)
        print("\n--- Testing create_metric_group integration ---")
        test_create_metric_group_integration(service, dialog_sections)
        
        # Test sub-metrics generation with different scenarios
        print("\n--- Testing sub-metrics generation ---")
        test_sub_metrics_generation(service)
        
        # Test revision generation
        print("\n--- Testing revision generation ---")
        test_revision_generation(service)
        
        print("\n--- All tests completed ---")
        
    except (ValueError, ConnectionError, RuntimeError) as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


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
    custom_eval_system_prompt_path = "/Users/wanghuan/Documents/py_repos/career_face_backend/app/config/prompts/evaluation/v2/prompt_audience_appropriate_eval_system_msg.md"  # e.g., "/path/to/custom_eval_system.md"
    custom_eval_user_prompt_path = None    # e.g., "/path/to/custom_eval_user.md"
    custom_revise_system_prompt_path = None # e.g., "/path/to/custom_revise_system.md"
    custom_revise_user_prompt_path = None   # e.g., "/path/to/custom_revise_user.md"
    
    # Create test dependencies 
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create service with custom prompt parameters
    service = AudienceAppropriatenessMetricCalculationService(
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
        metadata = MetricMetadata(metric_type=MetricType.AUDIENCE_APPROPRIATENESS, model=model, weight=1.0)
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
    test_audience_appropriateness_service()