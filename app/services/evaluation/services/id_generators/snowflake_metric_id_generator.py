"""Snowflake-based ID generator for Metric entities."""

from .snowflake_base import SnowflakeGenerator

from ...business.services import IdGenerator
from .config import IDGeneratorConfig


class SnowflakeMetricIDGenerator(IdGenerator):
    """
    ID generator for Metric business entity using Snowflake algorithm.
    
    This implementation uses the snowflake-id library to generate unique, 
    time-ordered identifiers for Metric entities.
    Uses a predefined instance ID from IDGeneratorConfig.
    """

    def __init__(self):
        """
        Initialize the Snowflake generator for Metric IDs.
        
        Uses the predefined instance ID from IDGeneratorConfig to ensure
        no conflicts with other entity ID generators.
        """
        self._generator = SnowflakeGenerator(
            IDGeneratorConfig.METRIC_INSTANCE_ID
        )

    def generate(self) -> str:
        """
        Generate a unique identifier for Metric entity.
        
        Returns:
            A unique string identifier based on Snowflake algorithm.
        """
        return str(next(self._generator))