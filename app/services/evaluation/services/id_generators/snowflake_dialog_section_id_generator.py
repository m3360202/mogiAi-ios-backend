"""Snowflake-based ID generator for DialogSection entities."""

from .snowflake_base import SnowflakeGenerator

from ...business.services import IdGenerator
from .config import IDGeneratorConfig


class SnowflakeDialogSectionIDGenerator(IdGenerator):
    """
    ID generator for DialogSection business entity using Snowflake algorithm.
    
    This implementation uses the snowflake-id library to generate unique, 
    time-ordered identifiers for DialogSection entities.
    Uses a predefined instance ID from IDGeneratorConfig.
    """

    def __init__(self):
        """
        Initialize the Snowflake generator for DialogSection IDs.
        
        Uses the predefined instance ID from IDGeneratorConfig to ensure
        no conflicts with other entity ID generators.
        """
        self._generator = SnowflakeGenerator(
            IDGeneratorConfig.DIALOG_SECTION_INSTANCE_ID
        )

    def generate(self) -> str:
        """
        Generate a unique identifier for DialogSection entity.
        
        Returns:
            A unique string identifier based on Snowflake algorithm.
        """
        return str(next(self._generator))