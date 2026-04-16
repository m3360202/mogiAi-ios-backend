"""
In-memory implementation of EvaluationRecordRepo for evaluation feature.
Used for rapid prototyping and testing.
"""
from typing import Dict, Optional, List
from threading import Lock

from ..business import EvaluationRecord, EvaluationRecordRepo


class InMemoryEvaluationRecordRepo(EvaluationRecordRepo):
    """
    In-memory implementation of EvaluationRecordRepo.
    Thread-safe for concurrent access.
    """
    
    def __init__(self) -> None:
        self._records: Dict[str, EvaluationRecord] = {}
        self._interview_index: Dict[str, str] = {}  # interview_record_id -> evaluation_record_id
        self._lock = Lock()
    
    def save(self, evaluation_record: EvaluationRecord) -> None:
        """Save an evaluation record."""
        with self._lock:
            self._records[evaluation_record.id] = evaluation_record
            self._interview_index[evaluation_record.interview_record_id] = evaluation_record.id
    
    def get_by_interview_record_id(self, interview_record_id: str) -> Optional[EvaluationRecord]:
        """Get evaluation record by interview record ID."""
        with self._lock:
            evaluation_record_id = self._interview_index.get(interview_record_id)
            if evaluation_record_id:
                return self._records.get(evaluation_record_id)
            return None
    
    def get_by_id(self, evaluation_record_id: str) -> Optional[EvaluationRecord]:
        """Get evaluation record by ID."""
        with self._lock:
            return self._records.get(evaluation_record_id)
    
    def get_all(self) -> List[EvaluationRecord]:
        """Get all evaluation records."""
        with self._lock:
            return list(self._records.values())
    
    def clear(self) -> None:
        """Clear all records (useful for testing)."""
        with self._lock:
            self._records.clear()
            self._interview_index.clear()