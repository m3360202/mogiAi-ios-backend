"""
Tests for the DefaultDialogSectionBuilder.
"""
import pytest
from unittest.mock import Mock
from datetime import datetime

from .default_dialog_section_builder import DefaultDialogSectionBuilder
from ...business.value_objects import RawDialogInfo, DialogMessage
from ...business.enums import MessageRole


class TestDefaultDialogSectionBuilder:
    """Test suite for DefaultDialogSectionBuilder."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock services
        self.dialog_section_id_generator = Mock()
        self.logger = Mock()
        
        # Set up ID generation
        self.dialog_section_id_generator.generate.side_effect = ["ds1", "ds2", "ds3"]
        
        # Create the builder
        self.builder = DefaultDialogSectionBuilder(
            dialog_section_id_generator=self.dialog_section_id_generator,
            logger=self.logger
        )
    
    def test_build_single_section(self) -> None:
        """Test building a single dialog section."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Tell me about yourself",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="I am a software engineer",
                    start_time=datetime(2023, 1, 1, 10, 0, 10),
                    end_time=datetime(2023, 1, 1, 10, 0, 15)
                )
            ]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should create one section with both messages
        assert len(sections) == 1
        section = sections[0]
        
        assert section.id == "ds1"
        assert section.dialog_id == "test_dialog"
        assert len(section.messages) == 2
        
        # Check messages have correct section_id
        assert section.messages[0].section_id == "ds1"
        assert section.messages[1].section_id == "ds1"
        
        # Check message roles and content
        assert section.messages[0].role == MessageRole.INTERVIEWER
        assert section.messages[0].content == "Tell me about yourself"
        assert section.messages[1].role == MessageRole.CANDIDATE
        assert section.messages[1].content == "I am a software engineer"
    
    def test_build_multiple_sections(self) -> None:
        """Test building multiple dialog sections."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Question 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Answer 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 10),
                    end_time=datetime(2023, 1, 1, 10, 0, 15)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Question 2",
                    start_time=datetime(2023, 1, 1, 10, 0, 20),
                    end_time=datetime(2023, 1, 1, 10, 0, 25)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Answer 2",
                    start_time=datetime(2023, 1, 1, 10, 0, 30),
                    end_time=datetime(2023, 1, 1, 10, 0, 35)
                )
            ]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should create two sections
        assert len(sections) == 2
        
        # Check first section
        section1 = sections[0]
        assert section1.id == "ds1"
        assert len(section1.messages) == 2
        assert section1.messages[0].content == "Question 1"
        assert section1.messages[1].content == "Answer 1"
        
        # Check second section
        section2 = sections[1]
        assert section2.id == "ds2"
        assert len(section2.messages) == 2
        assert section2.messages[0].content == "Question 2"
        assert section2.messages[1].content == "Answer 2"
    
    def test_build_with_consecutive_interviewer_messages(self) -> None:
        """Test handling consecutive interviewer messages."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Welcome",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Tell me about yourself",
                    start_time=datetime(2023, 1, 1, 10, 0, 10),
                    end_time=datetime(2023, 1, 1, 10, 0, 15)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="I am a developer",
                    start_time=datetime(2023, 1, 1, 10, 0, 20),
                    end_time=datetime(2023, 1, 1, 10, 0, 25)
                )
            ]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should create one section with all messages
        assert len(sections) == 1
        section = sections[0]
        
        assert len(section.messages) == 3
        assert section.messages[0].content == "Welcome"
        assert section.messages[1].content == "Tell me about yourself"
        assert section.messages[2].content == "I am a developer"
    
    def test_build_empty_messages(self) -> None:
        """Test handling empty messages list."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should return empty list
        assert len(sections) == 0
    
    def test_merge_multiple_candidate_messages(self) -> None:
        """Test merging multiple consecutive candidate messages into one."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Tell me about your experience",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="I have 5 years of experience.",
                    start_time=datetime(2023, 1, 1, 10, 0, 10),
                    end_time=datetime(2023, 1, 1, 10, 0, 15)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="I worked at several companies.",
                    start_time=datetime(2023, 1, 1, 10, 0, 16),
                    end_time=datetime(2023, 1, 1, 10, 0, 20)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="I specialize in backend development.",
                    start_time=datetime(2023, 1, 1, 10, 0, 21),
                    end_time=datetime(2023, 1, 1, 10, 0, 25)
                )
            ]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should create one section
        assert len(sections) == 1
        section = sections[0]
        
        # Should have 2 messages: interviewer + merged candidate
        assert len(section.messages) == 2
        
        # Check interviewer message
        assert section.messages[0].role == MessageRole.INTERVIEWER
        assert section.messages[0].content == "Tell me about your experience"
        
        # Check merged candidate message
        assert section.messages[1].role == MessageRole.CANDIDATE
        expected_content = "I have 5 years of experience. I worked at several companies. I specialize in backend development."
        assert section.messages[1].content == expected_content
        assert section.messages[1].start_time == datetime(2023, 1, 1, 10, 0, 10)
        assert section.messages[1].end_time == datetime(2023, 1, 1, 10, 0, 25)
    
    def test_discard_interviewer_only_final_section(self) -> None:
        """Test discarding final section that contains only interviewer messages."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Question 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Answer 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 10),
                    end_time=datetime(2023, 1, 1, 10, 0, 15)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Final question",
                    start_time=datetime(2023, 1, 1, 10, 0, 20),
                    end_time=datetime(2023, 1, 1, 10, 0, 25)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Follow up question",
                    start_time=datetime(2023, 1, 1, 10, 0, 30),
                    end_time=datetime(2023, 1, 1, 10, 0, 35)
                )
            ]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should only create the first section (second section discarded)
        assert len(sections) == 1
        
        section = sections[0]
        assert section.messages[0].content == "Question 1"
        assert section.messages[1].content == "Answer 1"
        
        # Verify logging for discarded section
        discard_calls = [call for call in self.logger.debug.call_args_list 
                        if "discard_final_section" in call[0][0]]
        assert len(discard_calls) == 1
        assert discard_calls[0][0][1]["reason"] == "Final section contains only interviewer messages"
    
    def test_mixed_message_patterns(self) -> None:
        """Test complex patterns with multiple merging scenarios."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Intro",
                    start_time=datetime(2023, 1, 1, 10, 0, 0),
                    end_time=datetime(2023, 1, 1, 10, 0, 5)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Question 1",
                    start_time=datetime(2023, 1, 1, 10, 0, 6),
                    end_time=datetime(2023, 1, 1, 10, 0, 10)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Part A",
                    start_time=datetime(2023, 1, 1, 10, 0, 15),
                    end_time=datetime(2023, 1, 1, 10, 0, 20)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Part B",
                    start_time=datetime(2023, 1, 1, 10, 0, 21),
                    end_time=datetime(2023, 1, 1, 10, 0, 25)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Question 2",
                    start_time=datetime(2023, 1, 1, 10, 0, 30),
                    end_time=datetime(2023, 1, 1, 10, 0, 35)
                ),
                DialogMessage(
                    section_id="",
                    role=MessageRole.CANDIDATE,
                    content="Answer 2",
                    start_time=datetime(2023, 1, 1, 10, 0, 40),
                    end_time=datetime(2023, 1, 1, 10, 0, 45)
                )
            ]
        )
        
        sections = self.builder.build_dialog_sections(raw_dialog_info)
        
        # Should create two sections
        assert len(sections) == 2
        
        # First section: Intro + Question 1 + merged candidate responses
        section1 = sections[0]
        assert len(section1.messages) == 3  # 2 interviewer + 1 merged candidate
        assert section1.messages[0].content == "Intro"
        assert section1.messages[1].content == "Question 1"
        assert section1.messages[2].content == "Part A Part B"
        assert section1.messages[2].role == MessageRole.CANDIDATE
        
        # Second section: Question 2 + Answer 2
        section2 = sections[1]
        assert len(section2.messages) == 2
        assert section2.messages[0].content == "Question 2"
        assert section2.messages[1].content == "Answer 2"
    
    def test_logging_calls(self) -> None:
        """Test that proper logging calls are made."""
        raw_dialog_info = RawDialogInfo(
            dialog_id="test_dialog",
            messages=[
                DialogMessage(
                    section_id="",
                    role=MessageRole.INTERVIEWER,
                    content="Test",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
            ]
        )
        
        self.builder.build_dialog_sections(raw_dialog_info)
        
        # Verify logging calls (start, discard, end)
        assert self.logger.debug.call_count == 3
        
        # Check start logging
        start_call = self.logger.debug.call_args_list[0]
        assert "build_dialog_sections.start" in start_call[0][0]
        assert start_call[0][1]["dialog_id"] == "test_dialog"
        
        # Check discard logging
        discard_call = self.logger.debug.call_args_list[1]
        assert "discard_final_section" in discard_call[0][0]
        
        # Check end logging
        end_call = self.logger.debug.call_args_list[2]
        assert "build_dialog_sections.end" in end_call[0][0]
        assert end_call[0][1]["dialog_id"] == "test_dialog"
        assert end_call[0][1]["sections_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__])