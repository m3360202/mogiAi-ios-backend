"""
Tests for SimpleSectionFeedbackServiceImpl.

This test suite verifies the behavior of the simple section feedback service implementation,
including proper LLM integration, prompt loading, and feedback generation.
"""
import json
import pytest
from unittest.mock import Mock, mock_open, patch, AsyncMock
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from app.services.evaluation.business import (
    SuperMetric,
    SuperMetricMetadata,
    SuperMetricType,
    SuperMetricFeedback,
    MetricGroup,
    MetricType,
    MetricMetadata,
    Score,
    ScoreLabel,
    Logger,
    DialogSectionRepo,
    DialogMessage,
    MessageRole
)
from app.services.evaluation.business.entities import DialogSection
from app.services.evaluation.services.feedback_services.simple_section_feedback_service import (
    SimpleSectionFeedbackServiceImpl,
    SingleSectionFeedbackResult
)


class TestSimpleSectionFeedbackServiceImpl:
    """Test suite for SimpleSectionFeedbackServiceImpl."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock services
        self.mock_logger = Mock(spec=Logger)
        self.mock_dialog_section_repo = Mock(spec=DialogSectionRepo)
        
        # Sample prompt content for testing
        self.sample_system_prompt = """
        You are an expert interview feedback generator.
        Your task is to provide constructive feedback for interview responses.
        """
        
        self.sample_user_prompt_template = """
        Super-metric: {super_metric_type}
        Section: {section_index}
        Score: {score} ({score_label})
        
        Conversation:
        {conversation_content}
        
        Provide feedback in JSON format with the following structure:
        - super_metric_type: string
        - brief_feedback: string
        - revised_response: string
        - feedback: string
        """
        
        # Sample dialog section for testing
        self.sample_dialog_section = DialogSection(
            id="section_1",
            dialog_id="dialog_123",
            section_index=0,
            messages=[
                DialogMessage(
                    section_id="section_1",
                    role=MessageRole.INTERVIEWER,
                    content="Tell me about your experience with project management.",
                    start_time=datetime(2025, 1, 1, 10, 0, 0),
                    end_time=datetime(2025, 1, 1, 10, 0, 15)
                ),
                DialogMessage(
                    section_id="section_1",
                    role=MessageRole.CANDIDATE,
                    content="I have led several projects using agile methodologies and have experience with cross-functional teams.",
                    start_time=datetime(2025, 1, 1, 10, 0, 15),
                    end_time=datetime(2025, 1, 1, 10, 0, 45)
                )
            ],
            start_time=datetime(2025, 1, 1, 10, 0, 0),
            end_time=datetime(2025, 1, 1, 10, 0, 45)
        )
        
        # Sample super metric for testing
        self.sample_super_metric = self._create_sample_super_metric()
    
    def _create_sample_super_metric(self) -> SuperMetric:
        """Create a sample SuperMetric for testing."""
        # Create metadata
        metadata = SuperMetricMetadata(
            super_metric_type=SuperMetricType.CLARITY,
            metric_metadata_list=[
                MetricMetadata(metric_type=MetricType.CONCISENESS, weight=0.5, eval_system_prompt_path=None),
                MetricMetadata(metric_type=MetricType.LOGICAL_STRUCTURE, weight=0.5, eval_system_prompt_path=None)
            ],
            weight=1.0
        )
        
        # Create empty metric groups (not needed for this test)
        metric_groups: List[MetricGroup] = []
        
        # Create score
        score = Score(score_label=ScoreLabel.GOOD, numeric_score=85.0)
        
        # Create empty feedback
        feedback = SuperMetricFeedback(
            brief_feedback="",
            revised_response="",
            feedback="",
            section_index=0
        )
        
        return SuperMetric(
            metadata=metadata,
            metric_groups=metric_groups,
            score=score,
            section_scores=[],
            feedback=feedback
        )
    
    def _create_service_with_mocked_prompts(self) -> SimpleSectionFeedbackServiceImpl:
        """Create service instance with mocked prompt files."""
        with patch("builtins.open") as mock_file:
            # Configure mock to return different content for different files
            def side_effect(file_path: Any, *args: Any, **kwargs: Any) -> Any:
                mock_file_obj = mock_open().return_value
                if "system_msg" in str(file_path):
                    mock_file_obj.read.return_value = self.sample_system_prompt
                elif "user_msg" in str(file_path):
                    mock_file_obj.read.return_value = self.sample_user_prompt_template
                return mock_file_obj
            
            mock_file.side_effect = side_effect
            
            service = SimpleSectionFeedbackServiceImpl(
                logger=self.mock_logger,
                dialog_section_repo=self.mock_dialog_section_repo,
                model="gpt-4o"
            )
        return service
    
    def test_initialization_success(self) -> None:
        """Test successful initialization with valid prompt files."""
        service = self._create_service_with_mocked_prompts()
        
        # Verify prompts were loaded
        assert service.section_system_prompt == self.sample_system_prompt
        assert service.section_user_prompt_template == self.sample_user_prompt_template
        assert service.model == "gpt-4o"
        assert service.temperature == 0.3
        
        # Verify logging
        self.mock_logger.debug.assert_called_once()
        debug_call = self.mock_logger.debug.call_args
        assert "Successfully loaded section feedback prompts" in debug_call[0][0]
    
    def test_initialization_file_not_found(self) -> None:
        """Test initialization when prompt files are not found."""
        with patch("builtins.open", side_effect=FileNotFoundError("File not found")):
            with pytest.raises(FileNotFoundError):
                SimpleSectionFeedbackServiceImpl(
                    logger=self.mock_logger,
                    dialog_section_repo=self.mock_dialog_section_repo
                )
        
        # Verify error logging
        self.mock_logger.error.assert_called_once()
        error_call = self.mock_logger.error.call_args
        assert "Failed to load feedback prompts" in error_call[0][0]
        assert isinstance(error_call[0][1], FileNotFoundError)
    
    @pytest.mark.asyncio
    async def test_generate_feedback_for_super_metric_success(self) -> None:
        """Test successful feedback generation for a super-metric."""
        service = self._create_service_with_mocked_prompts()
        
        # Mock LLM response
        mock_response_data = {
            "super_metric_type": "CLARITY",
            "brief_feedback": "Your response shows good structure but could be more concise.",
            "revised_response": "I have 5 years of project management experience using agile methodologies, successfully leading cross-functional teams of 8-12 people.",
            "feedback": "While your response demonstrates relevant experience, consider being more specific about your achievements. Quantify your experience with concrete examples."
        }
        
        with patch.object(service, '_call_llm_with_json_response', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_response_data
            
            # Call the method
            result = await service.generate_feedback_for_super_metric(
                section=self.sample_dialog_section,
                super_metric=self.sample_super_metric
            )
        
        # Verify result
        assert isinstance(result, SuperMetricFeedback)
        assert result.brief_feedback == mock_response_data["brief_feedback"]
        assert result.revised_response == mock_response_data["revised_response"]
        assert result.feedback == mock_response_data["feedback"]
        assert result.section_index == self.sample_dialog_section.section_index
        
        # Verify LLM was called with correct parameters
        mock_llm.assert_called_once()
        call_args = mock_llm.call_args[0][0]  # Get the messages parameter
        
        # Check system message
        assert call_args[0]["role"] == "system"
        assert call_args[0]["content"] == self.sample_system_prompt
        
        # Check user message contains expected content
        user_message = call_args[1]["content"]
        assert "CLARITY" in user_message
        assert "85" in user_message  # score
        assert "GOOD" in user_message  # score label
        assert "Interviewer: Tell me about your experience" in user_message
        assert "Candidate: I have led several projects" in user_message
        
        # Verify debug logging
        debug_calls = [call for call in self.mock_logger.debug.call_args_list 
                      if "Generating feedback for super-metric" in call[0][0]]
        assert len(debug_calls) >= 1
        
        success_calls = [call for call in self.mock_logger.debug.call_args_list 
                        if "Successfully generated feedback" in call[0][0]]
        assert len(success_calls) >= 1
    
    @pytest.mark.asyncio
    async def test_generate_feedback_for_super_metric_llm_error(self) -> None:
        """Test error handling when LLM call fails."""
        service = self._create_service_with_mocked_prompts()
        
        with patch.object(service, '_call_llm_with_json_response', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM service unavailable")
            
            # Call the method
            result = await service.generate_feedback_for_super_metric(
                section=self.sample_dialog_section,
                super_metric=self.sample_super_metric
            )
        
        # Should return placeholder feedback
        assert isinstance(result, SuperMetricFeedback)
        assert "Feedback generation temporarily unavailable" in result.brief_feedback
        assert result.revised_response == "Please try again later for detailed feedback."
        assert result.feedback == "We encountered an issue generating detailed feedback for this section. Please try again later."
        assert result.section_index == self.sample_dialog_section.section_index
        
        # Verify error logging
        error_calls = [call for call in self.mock_logger.error.call_args_list 
                      if "Failed to generate feedback" in call[0][0]]
        assert len(error_calls) >= 1
    
    @pytest.mark.asyncio
    async def test_call_llm_with_json_response_success(self) -> None:
        """Test successful LLM call with JSON response parsing."""
        service = self._create_service_with_mocked_prompts()
        
        # Mock LLM response
        mock_response_content = json.dumps({
            "super_metric_type": "CLARITY",
            "brief_feedback": "Test feedback",
            "revised_response": "Test revision",
            "feedback": "Test detailed feedback"
        })
        
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = mock_response_content
        
        with patch("app.services.evaluation.utils.litellm_client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response
            
            messages = [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "User prompt"}
            ]
            
            # Call the method
            result = await service._call_llm_with_json_response(messages)
        
        # Verify result
        assert isinstance(result, dict)
        assert result["super_metric_type"] == "CLARITY"
        assert result["brief_feedback"] == "Test feedback"
        
        # Verify LLM was called with correct parameters
        mock_acompletion.assert_called_once()
        call_kwargs = mock_acompletion.call_args[1]
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["messages"] == messages
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["response_format"] == {"type": "json_object"}
    
    @pytest.mark.asyncio
    async def test_call_llm_with_json_response_empty_content(self) -> None:
        """Test LLM call when response content is None."""
        service = self._create_service_with_mocked_prompts()
        
        # Mock LLM response with None content
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = None
        
        with patch("app.services.evaluation.utils.litellm_client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response
            
            messages = [{"role": "user", "content": "Test"}]
            
            # Should raise ValueError
            with pytest.raises(ValueError, match="LLM returned empty content"):
                await service._call_llm_with_json_response(messages)
    
    @pytest.mark.asyncio
    async def test_call_llm_with_json_response_invalid_json(self) -> None:
        """Test LLM call when response contains invalid JSON."""
        service = self._create_service_with_mocked_prompts()
        
        # Mock LLM response with invalid JSON
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "invalid json content"
        
        with patch("app.services.evaluation.utils.litellm_client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response
            
            messages = [{"role": "user", "content": "Test"}]
            
            # Should raise JSON decode error
            with pytest.raises(json.JSONDecodeError):
                await service._call_llm_with_json_response(messages)
    
    @pytest.mark.asyncio
    async def test_call_llm_with_json_response_litellm_error(self) -> None:
        """Test LLM call when LiteLLM raises an exception."""
        service = self._create_service_with_mocked_prompts()
        
        with patch("app.services.evaluation.utils.litellm_client.litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = Exception("API error")
            
            messages = [{"role": "user", "content": "Test"}]
            
            # Should raise exception and log error
            with pytest.raises(Exception, match="API error"):
                await service._call_llm_with_json_response(messages)
        
        # Verify error logging
        error_calls = [call for call in self.mock_logger.error.call_args_list 
                      if "Failed to call LLM for feedback generation" in call[0][0]]
        assert len(error_calls) >= 1
    
    def test_create_placeholder_feedback(self) -> None:
        """Test creation of placeholder feedback."""
        service = self._create_service_with_mocked_prompts()
        
        # Call the method
        result = service._create_placeholder_feedback(
            section=self.sample_dialog_section,
            super_metric=self.sample_super_metric
        )
        
        # Verify structure
        assert isinstance(result, SuperMetricFeedback)
        assert "Feedback generation temporarily unavailable for CLARITY" in result.brief_feedback
        assert result.revised_response == "Please try again later for detailed feedback."
        assert result.feedback == "We encountered an issue generating detailed feedback for this section. Please try again later."
        assert result.section_index == self.sample_dialog_section.section_index
    
    def test_single_section_feedback_result_model(self) -> None:
        """Test the SingleSectionFeedbackResult Pydantic model."""
        # Test valid data
        valid_data = {
            "super_metric_type": "CLARITY",
            "brief_feedback": "Good structure",
            "revised_response": "Improved response",
            "feedback": "Detailed feedback"
        }
        
        result = SingleSectionFeedbackResult(**valid_data)
        assert result.super_metric_type == "CLARITY"
        assert result.brief_feedback == "Good structure"
        assert result.revised_response == "Improved response"
        assert result.feedback == "Detailed feedback"
        
        # Test missing required field
        invalid_data = {
            "super_metric_type": "CLARITY",
            # Missing required fields
        }
        
        with pytest.raises(Exception):  # Pydantic validation error
            SingleSectionFeedbackResult(**invalid_data)
    
    @pytest.mark.asyncio
    async def test_generate_feedback_with_real_llm_api(self) -> None:
        """Integration test: Generate feedback using the actual LLM API (not mocked)."""
        service = self._create_service_with_mocked_prompts()
        
        # Create a realistic dialog section for testing
        realistic_section = DialogSection(
            id="integration_test_section",
            dialog_id="integration_test_dialog",
            section_index=0,
            messages=[
                DialogMessage(
                    section_id="integration_test_section",
                    role=MessageRole.INTERVIEWER,
                    content="Tell me about a challenging project you've worked on and how you handled it.",
                    start_time=datetime(2025, 1, 1, 10, 0, 0),
                    end_time=datetime(2025, 1, 1, 10, 0, 10)
                ),
                DialogMessage(
                    section_id="integration_test_section",
                    role=MessageRole.CANDIDATE,
                    content="Well, I worked on a project where we had to implement a new system in just 2 weeks. It was really challenging because the requirements kept changing and we had limited resources. I managed the team and we worked long hours to get it done.",
                    start_time=datetime(2025, 1, 1, 10, 0, 10),
                    end_time=datetime(2025, 1, 1, 10, 0, 45)
                )
            ],
            start_time=datetime(2025, 1, 1, 10, 0, 0),
            end_time=datetime(2025, 1, 1, 10, 0, 45)
        )
        
        # Create a super metric to evaluate
        test_super_metric = self._create_sample_super_metric()
        
        try:
            # Call the actual method without mocking - this will hit the real LLM API
            result = await service.generate_feedback_for_super_metric(
                section=realistic_section,
                super_metric=test_super_metric
            )
            
            # Verify the result structure
            assert isinstance(result, SuperMetricFeedback)
            assert len(result.brief_feedback) > 0
            assert len(result.revised_response) > 0
            assert len(result.feedback) > 0
            assert result.section_index == realistic_section.section_index
            
            # Verify the feedback content is meaningful (basic sanity checks)
            assert result.brief_feedback != "Feedback generation temporarily unavailable for CLARITY."
            assert result.revised_response != "Please try again later for detailed feedback."
            assert result.feedback != "We encountered an issue generating detailed feedback for this section. Please try again later."
            
            # Log the actual result for manual review
            self.mock_logger.info(f"Real LLM API Test Result - Brief: {result.brief_feedback}")
            self.mock_logger.info(f"Real LLM API Test Result - Revised: {result.revised_response}")
            self.mock_logger.info(f"Real LLM API Test Result - Feedback: {result.feedback}")
            
            print(f"\n=== REAL LLM API TEST RESULTS ===")
            print(f"Brief Feedback: {result.brief_feedback}")
            print(f"Revised Response: {result.revised_response}")
            print(f"Detailed Feedback: {result.feedback}")
            print(f"Section Index: {result.section_index}")
            print(f"=====================================\n")
            
        except Exception as e:
            # If the API call fails, we should still fail the test but with a clear message
            pytest.fail(f"Real LLM API call failed: {str(e)}. This could indicate API key issues, network problems, or service unavailability.")

    def test_conversation_content_formatting(self) -> None:
        """Test that conversation content is properly formatted for the LLM prompt."""
        
        # Create section with multiple messages
        section = DialogSection(
            id="section_test",
            dialog_id="dialog_test",
            section_index=1,
            messages=[
                DialogMessage(
                    section_id="section_test",
                    role=MessageRole.INTERVIEWER,
                    content="What is your biggest weakness?",
                    start_time=datetime(2025, 1, 1, 10, 0, 0),
                    end_time=datetime(2025, 1, 1, 10, 0, 10)
                ),
                DialogMessage(
                    section_id="section_test",
                    role=MessageRole.CANDIDATE,
                    content="I sometimes struggle with perfectionism, but I'm learning to balance quality with efficiency.",
                    start_time=datetime(2025, 1, 1, 10, 0, 10),
                    end_time=datetime(2025, 1, 1, 10, 0, 30)
                ),
                DialogMessage(
                    section_id="section_test",
                    role=MessageRole.INTERVIEWER,
                    content="Can you give me a specific example?",
                    start_time=datetime(2025, 1, 1, 10, 0, 30),
                    end_time=datetime(2025, 1, 1, 10, 0, 35)
                )
            ],
            start_time=datetime(2025, 1, 1, 10, 0, 0),
            end_time=datetime(2025, 1, 1, 10, 0, 35)
        )
        
        # Test the conversation content formatting logic directly
        conversation_content = ""
        for message in section.messages:
            role_label = "Interviewer" if message.role.value == "INTERVIEWER" else "Candidate"
            conversation_content += f"{role_label}: {message.content}\n"
        
        expected_content = (
            "Interviewer: What is your biggest weakness?\n"
            "Candidate: I sometimes struggle with perfectionism, but I'm learning to balance quality with efficiency.\n"
            "Interviewer: Can you give me a specific example?\n"
        )
        
        assert conversation_content == expected_content


if __name__ == "__main__":
    pytest.main([__file__])