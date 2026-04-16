"""
Configuration for ID generators.

This module defines all instance IDs used by Snowflake ID generators
to ensure uniqueness across different entity types and prevent collisions.
"""


class IDGeneratorConfig:
    """
    Centralized configuration for all ID generator instance IDs.
    
    Instance IDs must be unique across all generators to ensure
    generated IDs never collide. Valid range is 1-1023 per
    Snowflake algorithm specification.
    """
    
    # Entity-specific instance IDs
    EVALUATION_RECORD_INSTANCE_ID = 1
    DIALOG_SECTION_INSTANCE_ID = 2
    METRIC_INSTANCE_ID = 3
    
    # Reserved ranges for future entity types
    # 4-10: Reserved for additional evaluation entities
    # 11-20: Reserved for interview entities
    # 21-30: Reserved for user/session entities
    # 31-50: Reserved for system entities
    
    @classmethod
    def validate_all_unique(cls) -> bool:
        """
        Validate that all configured instance IDs are unique.
        
        Returns:
            True if all IDs are unique, False otherwise.
        """
        instance_ids = [
            cls.EVALUATION_RECORD_INSTANCE_ID,
            cls.DIALOG_SECTION_INSTANCE_ID,
            cls.METRIC_INSTANCE_ID,
        ]
        
        return len(instance_ids) == len(set(instance_ids))
    
    @classmethod
    def validate_all_in_range(cls) -> bool:
        """
        Validate that all configured instance IDs are in valid range (1-1023).
        
        Returns:
            True if all IDs are in valid range, False otherwise.
        """
        instance_ids = [
            cls.EVALUATION_RECORD_INSTANCE_ID,
            cls.DIALOG_SECTION_INSTANCE_ID,
            cls.METRIC_INSTANCE_ID,
        ]
        
        return all(1 <= id_val <= 1023 for id_val in instance_ids)
    
    @classmethod
    def validate_configuration(cls) -> None:
        """
        Validate the entire configuration.
        
        Raises:
            ValueError: If configuration is invalid.
        """
        if not cls.validate_all_unique():
            raise ValueError("Instance IDs must be unique across all generators")
        
        if not cls.validate_all_in_range():
            raise ValueError("All instance IDs must be between 1 and 1023")


# Validate configuration on module import
IDGeneratorConfig.validate_configuration()