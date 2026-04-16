"""
Enums used throughout the evaluation business domain.
"""
from enum import Enum


class MessageRole(Enum):
    """Enum for message roles in dialogue."""
    INTERVIEWER = "INTERVIEWER"
    CANDIDATE = "CANDIDATE"


class ValueType(Enum):
    """Enum for value types in sub-metrics."""
    NUMBER = "NUMBER"
    STRING = "STRING"
    BOOLEAN = "BOOLEAN"


class ScoreLabel(Enum):
    """Enum for score labels."""
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class MetricType(Enum):
    """Enum for metric types."""
    CONCISENESS = "CONCISENESS"
    LOGICAL_STRUCTURE = "LOGICAL_STRUCTURE"
    EVIDENCE = "EVIDENCE"
    QUANTIFIABLE_RESULTS = "QUANTIFIABLE_RESULTS"
    AUDIENCE_APPROPRIATENESS = "AUDIENCE_APPROPRIATENESS"
    ACTIVE_LISTENING = "ACTIVE_LISTENING"
    COMPANY_RESEARCH = "COMPANY_RESEARCH"
    PERSONAL_OWNERSHIP = "PERSONAL_OWNERSHIP"
    GROWTH = "GROWTH"
    PACE = "PACE"
    INTONATION = "INTONATION"
    VOLUME = "VOLUME"
    PRONOUNCIATION = "PRONOUNCIATION"
    PAUSE = "PAUSE"
    EYE_CONTACT = "EYE_CONTACT"
    FACIAL_EXPRESSION = "FACIAL_EXPRESSION"
    POSTURE = "POSTURE"
    PERSONAL_APPEARANCE = "PERSONAL_APPEARANCE"

class SuperMetricType(Enum):
    """Enum for super-metric types."""
    CLARITY = "CLARITY"
    EVIDENCE = "EVIDENCE"
    IMPACT = "IMPACT"
    ENGAGEMENT = "ENGAGEMENT"
    VERBAL_PERFORMANCE = "VERBAL_PERFORMANCE"
    VISUAL_PERFORMANCE = "VISUAL_PERFORMANCE"
    
class StrategyId(Enum):
    """Enum for predefined evaluation strategy IDs."""
    STRATEGY_1 = "strategy_1"
    STRATEGY_BRIEF_LOOKUP = "strategy_brief_lookup"