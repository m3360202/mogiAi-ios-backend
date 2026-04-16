"""
In-memory implementation of DialogSectionRepo for evaluation feature.
Used for rapid prototyping and testing.
"""
from typing import Dict, Optional, List
from threading import Lock

from ..business import DialogSection, DialogSectionRepo


class InMemoryDialogSectionRepo(DialogSectionRepo):
    """
    In-memory implementation of DialogSectionRepo.
    Thread-safe for concurrent access.
    """
    
    def __init__(self) -> None:
        self._sections: Dict[str, DialogSection] = {}
        self._dialog_index: Dict[str, List[str]] = {}  # dialog_id -> list of section_ids
        self._lock = Lock()
    
    def save(self, dialog_section: DialogSection) -> None:
        """Save a dialog section."""
        with self._lock:
            self._sections[dialog_section.id] = dialog_section
            
            # Update dialog index
            if dialog_section.dialog_id not in self._dialog_index:
                self._dialog_index[dialog_section.dialog_id] = []
            if dialog_section.id not in self._dialog_index[dialog_section.dialog_id]:
                self._dialog_index[dialog_section.dialog_id].append(dialog_section.id)
    
    def get_by_id(self, section_id: str) -> Optional[DialogSection]:
        """Get dialog section by ID."""
        with self._lock:
            return self._sections.get(section_id)
    
    def get_by_dialog_id(self, dialog_id: str) -> List[DialogSection]:
        """Get all dialog sections for a dialog."""
        with self._lock:
            section_ids = self._dialog_index.get(dialog_id, [])
            return [self._sections[section_id] for section_id in section_ids if section_id in self._sections]
    
    def get_all(self) -> List[DialogSection]:
        """Get all dialog sections."""
        with self._lock:
            return list(self._sections.values())
    
    def clear(self) -> None:
        """Clear all sections (useful for testing)."""
        with self._lock:
            self._sections.clear()
            self._dialog_index.clear()