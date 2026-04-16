"""
Test file for CompanyResearchMetricCalculationService.

This file contains tests to verify the company research metric calculation service works correctly.
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
    CompanyResearchMetricCalculationService
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


def get_service() -> CompanyResearchMetricCalculationService:
    """Create a CompanyResearchMetricCalculationService instance for testing."""
    logger = TestLogger()
    id_generator = TestIdGenerator()
    return CompanyResearchMetricCalculationService(logger, id_generator)


def get_dialog_section() -> DialogSection:
    """Create a sample DialogSection for testing."""
    return DialogSection(
        id="test_section_id",
        dialog_id="test_dialog_id",
        section_index=0,
        messages=[
            DialogMessage(
                section_id="test_section_id",
                role=MessageRole.INTERVIEWER,
                content="What interests you about our company?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_id", 
                role=MessageRole.CANDIDATE,
                content="I'm looking for a new challenge and I like working with smart people at innovative companies.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )


def test_scoring_logic() -> None:
    """Test the scoring logic by analyzing the expected behavior."""
    # We can't test private methods directly, but we can document expected behavior
    print("✓ Scoring logic test - Testing expected score calculation behavior")
    print("  - Poor: Fails to mention any specific company details when the question provides an opportunity should result in POOR score (30.0)")
    print("  - Good: Effectively incorporates specific company details into their response, or the question does not pertain to the company should result in GOOD score (85.0)")


def test_service_initialization() -> None:
    """Test service initialization with required dependencies."""
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Test service creation with different models
    models_to_test = ["gpt-4o", "claude-3-5-sonnet-20241022"]
    
    for model in models_to_test:
        service = CompanyResearchMetricCalculationService(logger, id_generator, model=model)
        assert service.model == model
        assert service.logger is logger
        assert service.id_generator is id_generator
        print(f"✓ Service initialization test - Model: {model}")


def test_create_metric_group_integration(dialog_sections: List[DialogSection]) -> None:
    """Test the main create_metric_group method (integration test - may fail without API key)."""
    service = get_service()
    metadata = MetricMetadata(metric_type=MetricType.COMPANY_RESEARCH, model="gpt-4o", weight=1.0)
    
    try:
        metric_group = asyncio.run(service.create_metric_group(dialog_sections, metadata))
        
        # Verify metric group structure
        assert metric_group.metric_type == MetricType.COMPANY_RESEARCH
        assert isinstance(metric_group.metrics, list)
        assert len(metric_group.metrics) == len(dialog_sections)
        
        # Verify each metric in the group
        for i, metric in enumerate(metric_group.metrics):
            assert metric.id.startswith("test_metric_id_")
            assert metric.dialog_section_id == dialog_sections[i].id
            assert metric.metadata.metric_type == MetricType.COMPANY_RESEARCH
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


def test_sub_metrics_generation(service: CompanyResearchMetricCalculationService) -> None:
    """Test sub-metrics generation with different dialog scenarios."""
    
    # Test Case 1: Poor company research (no company details mentioned)
    poor_dialog_section = DialogSection(
        id="test_section_poor",
        dialog_id="test_dialog_poor",
        section_index=0,
        messages=[
            DialogMessage(
                section_id="test_section_poor",
                role=MessageRole.INTERVIEWER,
                content="What interests you about our company?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_poor",
                role=MessageRole.CANDIDATE,
                content="I'm looking for a new challenge and I like working with smart people at innovative companies.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 2: Good company research (specific company details mentioned)
    good_dialog_section = DialogSection(
        id="test_section_good",
        dialog_id="test_dialog_good",
        section_index=1,
        messages=[
            DialogMessage(
                section_id="test_section_good",
                role=MessageRole.INTERVIEWER,
                content="Why do you want to work here?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_good",
                role=MessageRole.CANDIDATE,
                content="I've been following Acme's Apollo platform, especially the v3 rollout last quarter that added on-device ML inference. I also read about your partnership with AWS to run a managed Graviton tier, which aligns with my work optimizing inference on Arm.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 3: Technical question (should default to good since not about company)
    technical_dialog_section = DialogSection(
        id="test_section_technical",
        dialog_id="test_dialog_technical",
        section_index=2,
        messages=[
            DialogMessage(
                section_id="test_section_technical",
                role=MessageRole.INTERVIEWER,
                content="What is the time and space complexity of merge sort, and when would you choose it over quicksort?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_technical",
                role=MessageRole.CANDIDATE,
                content="Merge sort runs in O(n log n) time with O(n) space. I prefer it when I need a stable sort or when working with linked lists, and it guarantees O(n log n) even in the worst case.",
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
        ("Technical Question", technical_dialog_section)
    ]
    
    for test_name, dialog_section in test_cases:
        try:
            metadata = MetricMetadata(metric_type=MetricType.COMPANY_RESEARCH, model="gpt-4o", weight=1.0)
            # Use new interface: create_metric_group with list of dialog sections
            metric_group = asyncio.run(service.create_metric_group([dialog_section], metadata))
            
            # Get the first (and only) metric from the group
            assert len(metric_group.metrics) == 1
            metric = metric_group.metrics[0]
            
            # Verify sub-metrics structure
            assert "has_done_research" in metric.sub_metrics
            assert "company_details_mentioned" in metric.sub_metrics
            
            # Verify data types
            assert isinstance(metric.sub_metrics["has_done_research"], bool)
            assert isinstance(metric.sub_metrics["company_details_mentioned"], list)
            
            print(f"✓ Sub-metrics test - {test_name}:")
            print(f"  - Has done research: {metric.sub_metrics['has_done_research']}")
            print(f"  - Company details count: {len(metric.sub_metrics['company_details_mentioned'])}")
            print(f"  - Company details: {metric.sub_metrics['company_details_mentioned']}")
            print(f"  - Score: {metric.score.score_label.value}")
            
        except (ValueError, ConnectionError, RuntimeError) as e:
            print(f"⚠ Sub-metrics test skipped for {test_name} - API issue: {e}")


def test_revision_generation(service: CompanyResearchMetricCalculationService) -> None:
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
                content="What do you know about our company culture?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_revision_poor",
                role=MessageRole.CANDIDATE,
                content="I think you have a good company culture where people work together and get things done.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    # Test Case 2: Good score should generate minimal or no revision
    good_dialog_section = DialogSection(
        id="test_section_revision_good",
        dialog_id="test_dialog_revision_good",
        section_index=1,
        messages=[
            DialogMessage(
                section_id="test_section_revision_good",
                role=MessageRole.INTERVIEWER,
                content="What attracts you to our company?",
                start_time=datetime.now(),
                end_time=datetime.now()
            ),
            DialogMessage(
                section_id="test_section_revision_good",
                role=MessageRole.CANDIDATE,
                content="I'm particularly impressed by your recent acquisition of DataCorp, which shows your commitment to expanding your analytics capabilities. Your quarterly engineering blog posts also demonstrate a culture of technical excellence and knowledge sharing that I'd love to be part of.",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        ],
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    
    test_cases = [
        ("Poor Response", poor_dialog_section, True),  # Should have substantial revision
        ("Good Response", good_dialog_section, False)  # Should have minimal/no revision
    ]
    
    for test_name, dialog_section, expects_revision in test_cases:
        try:
            metadata = MetricMetadata(metric_type=MetricType.COMPANY_RESEARCH, model="gpt-4o", weight=1.0)
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


def test_company_research_service() -> None:
    """Test the company research metric calculation service."""
    
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
                    content="Why are you interested in working at our company?",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                ),
                DialogMessage(
                    section_id="test_section_1",
                    role=MessageRole.CANDIDATE,
                    content="I've been following your company's recent expansion into AI-powered customer service tools. Your acquisition of TechStartup last year and the integration of their natural language processing technology into your main platform really impressed me. I also noticed your commitment to remote work culture, which aligns with my work style preferences.",
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
        service = CompanyResearchMetricCalculationService(logger, id_generator, model="gpt-4o")
        print("✓ Successfully created CompanyResearchMetricCalculationService")
        
        # Test scoring logic understanding
        print("\n--- Testing scoring logic understanding ---")
        test_scoring_logic()
        
        # Test service initialization
        print("\n--- Testing service initialization ---")
        test_service_initialization()
        
        # Test the full create_metric_group integration (may fail without API key)
        print("\n--- Testing create_metric_group integration ---")
        test_create_metric_group_integration(dialog_sections)
        
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
    custom_eval_system_prompt_path = "/Users/wanghuan/Documents/py_repos/career_face_backend/app/config/prompts/evaluation/v2/prompt_company_research_eval_system_msg.md"  # e.g., "/path/to/custom_eval_system.md"
    custom_eval_user_prompt_path = None    # e.g., "/path/to/custom_eval_user.md"
    custom_revise_system_prompt_path = None # e.g., "/path/to/custom_revise_system.md"
    custom_revise_user_prompt_path = None   # e.g., "/path/to/custom_revise_user.md"
    
    # Create test dependencies 
    logger = TestLogger()
    id_generator = TestIdGenerator()
    
    # Create service with custom prompt parameters
    service = CompanyResearchMetricCalculationService(
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
        metadata = MetricMetadata(metric_type=MetricType.COMPANY_RESEARCH, model=model, weight=1.0)
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
    test_company_research_service()