"""
Default implementation of DialogSectionBuilder.

This module contains the default implementation for building dialog sections
from raw dialog information based on conversation flow patterns.
"""
from typing import List

from ...business.entities import DialogSection
from ...business.value_objects import RawDialogInfo, DialogMessage
from ...business.services import DialogSectionBuilder, IdGenerator, Logger
from ...business.enums import MessageRole


class DefaultDialogSectionBuilder(DialogSectionBuilder):
    """
    Default implementation of DialogSectionBuilder.
    
    This implementation parses messages into sections based on conversation flow:
    - A new section starts when an interviewer message follows a candidate message
    - Multiple consecutive candidate messages within a section are merged into one
    - Sections containing only interviewer messages at the end are discarded
    - Each section represents a complete interaction cycle
    """
    
    def __init__(
        self,
        dialog_section_id_generator: IdGenerator,
        logger: Logger
    ):
        """
        Initialize the default dialog section builder.
        
        Args:
            dialog_section_id_generator: ID generator for dialog sections
            logger: Logger service
        """
        self._dialog_section_id_generator = dialog_section_id_generator
        self._logger = logger
    
    def build_dialog_sections(self, raw_dialog_info: RawDialogInfo) -> List[DialogSection]:
        """
        Parse RawDialogInfo into DialogSections without persisting them.
        
        Args:
            raw_dialog_info: The raw dialog information
            
        Returns:
            List[DialogSection]: The created dialog sections (not yet persisted)
        """
        self._logger.debug(
            "evaluation.DefaultDialogSectionBuilder.build_dialog_sections.start", 
            {"dialog_id": raw_dialog_info.dialog_id}
        )
        
        dialog_sections: List[DialogSection] = []
        current_section_messages: List[DialogMessage] = []
        section_index = 0
        
        for message in raw_dialog_info.messages:
            # Start a new section if we encounter an interviewer message
            # and we already have messages in the current section
            if (message.role == MessageRole.INTERVIEWER and 
                current_section_messages and 
                current_section_messages[-1].role == MessageRole.CANDIDATE):
                
                # Create section from current messages (with merged candidate messages)
                section = self._create_dialog_section(
                    raw_dialog_info.dialog_id,
                    current_section_messages,
                    section_index,
                    raw_dialog_info.language
                )
                dialog_sections.append(section)
                section_index += 1
                
                # Start new section
                current_section_messages = [message]
            else:
                current_section_messages.append(message)
        
        # Create final section if there are remaining messages and it contains candidate messages
        if current_section_messages:
            # Check if the section contains at least one candidate message
            has_candidate_message = any(msg.role == MessageRole.CANDIDATE for msg in current_section_messages)
            if has_candidate_message:
                section = self._create_dialog_section(
                    raw_dialog_info.dialog_id,
                    current_section_messages,
                    section_index,
                    raw_dialog_info.language
                )
                dialog_sections.append(section)
            else:
                self._logger.debug(
                    "evaluation.DefaultDialogSectionBuilder.build_dialog_sections.discard_final_section",
                    {
                        "dialog_id": raw_dialog_info.dialog_id,
                        "reason": "Final section contains only interviewer messages"
                    }
                )
        
        self._logger.debug(
            "evaluation.DefaultDialogSectionBuilder.build_dialog_sections.end",
            {
                "dialog_id": raw_dialog_info.dialog_id,
                "sections_count": len(dialog_sections)
            }
        )
        
        return dialog_sections
    
    def _create_dialog_section(
        self, 
        dialog_id: str, 
        messages: List[DialogMessage],
        section_index: int,
        language: str = "ja"
    ) -> DialogSection:
        """
        Create a DialogSection from a list of messages.
        Merges multiple candidate messages into one within each section.
        
        Args:
            dialog_id: The dialog ID
            messages: The messages in this section
            section_index: The index of the section
            language: Language of the section (ja/en/zh)
            
        Returns:
            DialogSection: The created dialog section
        """
        if not messages:
            raise ValueError("Cannot create dialog section with empty messages")
        
        section_id = self._dialog_section_id_generator.generate()
        
        # Merge consecutive candidate messages
        merged_messages = self._merge_candidate_messages(messages, section_id)
        
        return DialogSection(
            id=section_id,
            dialog_id=dialog_id,
            section_index=section_index,
            messages=merged_messages,
            start_time=messages[0].start_time,
            end_time=messages[-1].end_time,
            language=language
        )
    
    def _merge_candidate_messages(
        self, 
        messages: List[DialogMessage], 
        section_id: str
    ) -> List[DialogMessage]:
        """
        Merge consecutive candidate messages into single messages.
        
        Args:
            messages: The original messages
            section_id: The section ID to assign to messages
            
        Returns:
            List[DialogMessage]: Messages with candidate messages merged
        """
        merged_messages: List[DialogMessage] = []
        current_candidate_group: List[DialogMessage] = []
        
        for message in messages:
            if message.role == MessageRole.CANDIDATE:
                # Collect candidate messages
                current_candidate_group.append(message)
            else:
                # Process any accumulated candidate messages first
                if current_candidate_group:
                    merged_candidate = self._create_merged_candidate_message(
                        current_candidate_group, section_id
                    )
                    merged_messages.append(merged_candidate)
                    current_candidate_group = []
                
                # Add interviewer message
                interviewer_message = DialogMessage(
                    section_id=section_id,
                    role=message.role,
                    content=message.content,
                    start_time=message.start_time,
                    end_time=message.end_time,
                    nonverbal=message.nonverbal,
                    target_dimensions=message.target_dimensions,
                )
                merged_messages.append(interviewer_message)
        
        # Process any remaining candidate messages
        if current_candidate_group:
            merged_candidate = self._create_merged_candidate_message(
                current_candidate_group, section_id
            )
            merged_messages.append(merged_candidate)
        
        return merged_messages
    
    def _create_merged_candidate_message(
        self, 
        candidate_messages: List[DialogMessage], 
        section_id: str
    ) -> DialogMessage:
        """
        Create a single merged candidate message from multiple candidate messages.
        
        Args:
            candidate_messages: List of candidate messages to merge
            section_id: The section ID to assign
            
        Returns:
            DialogMessage: The merged candidate message
        """
        if not candidate_messages:
            raise ValueError("Cannot merge empty candidate messages")
        
        # Merge content with space separation
        merged_content = " ".join(msg.content for msg in candidate_messages)
        
        merged_dimensions: List[str] = []
        for msg in candidate_messages:
            if msg.target_dimensions:
                for dim in msg.target_dimensions:
                    if dim not in merged_dimensions:
                        merged_dimensions.append(dim)

        return DialogMessage(
            section_id=section_id,
            role=MessageRole.CANDIDATE,
            content=merged_content,
            start_time=candidate_messages[0].start_time,
            end_time=candidate_messages[-1].end_time,
            nonverbal=candidate_messages[-1].nonverbal,
            target_dimensions=merged_dimensions or None,
        )