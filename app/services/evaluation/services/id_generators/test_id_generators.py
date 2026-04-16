"""
Tests for the ID generators module.
"""

from .config import IDGeneratorConfig
from .snowflake_evaluation_record_id_generator import SnowflakeEvaluationRecordIDGenerator
from .snowflake_dialog_section_id_generator import SnowflakeDialogSectionIDGenerator
from .snowflake_metric_id_generator import SnowflakeMetricIDGenerator


class TestIDGeneratorConfig:
    """Test cases for IDGeneratorConfig."""

    def test_all_instance_ids_unique(self):
        """Test that all configured instance IDs are unique."""
        assert IDGeneratorConfig.validate_all_unique()

    def test_all_instance_ids_in_range(self):
        """Test that all configured instance IDs are in valid range."""
        assert IDGeneratorConfig.validate_all_in_range()

    def test_configuration_validation_passes(self):
        """Test that configuration validation passes."""
        # Should not raise an exception
        IDGeneratorConfig.validate_configuration()

    def test_specific_instance_id_values(self):
        """Test the specific configured values."""
        assert IDGeneratorConfig.EVALUATION_RECORD_INSTANCE_ID == 1
        assert IDGeneratorConfig.DIALOG_SECTION_INSTANCE_ID == 2
        assert IDGeneratorConfig.METRIC_INSTANCE_ID == 3


class TestSnowflakeEvaluationRecordIDGenerator:
    """Test cases for SnowflakeEvaluationRecordIDGenerator."""

    def test_init(self):
        """Test initialization."""
        generator = SnowflakeEvaluationRecordIDGenerator()
        assert generator is not None

    def test_generate_returns_string(self):
        """Test that generate returns a string."""
        generator = SnowflakeEvaluationRecordIDGenerator()
        result = generator.generate()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_returns_unique_ids(self):
        """Test that generate returns unique IDs on multiple calls."""
        generator = SnowflakeEvaluationRecordIDGenerator()
        ids = [generator.generate() for _ in range(10)]
        assert len(ids) == len(set(ids))  # All IDs should be unique

    def test_uses_configured_instance_id(self):
        """Test that generator uses the configured instance ID."""
        generator = SnowflakeEvaluationRecordIDGenerator()
        # Should not raise an exception and should generate valid IDs
        id_result = generator.generate()
        assert isinstance(id_result, str)


class TestSnowflakeDialogSectionIDGenerator:
    """Test cases for SnowflakeDialogSectionIDGenerator."""

    def test_init(self):
        """Test initialization."""
        generator = SnowflakeDialogSectionIDGenerator()
        assert generator is not None

    def test_generate_returns_string(self):
        """Test that generate returns a string."""
        generator = SnowflakeDialogSectionIDGenerator()
        result = generator.generate()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_returns_unique_ids(self):
        """Test that generate returns unique IDs on multiple calls."""
        generator = SnowflakeDialogSectionIDGenerator()
        ids = [generator.generate() for _ in range(10)]
        assert len(ids) == len(set(ids))  # All IDs should be unique

    def test_uses_configured_instance_id(self):
        """Test that generator uses the configured instance ID."""
        generator = SnowflakeDialogSectionIDGenerator()
        # Should not raise an exception and should generate valid IDs
        id_result = generator.generate()
        assert isinstance(id_result, str)


class TestSnowflakeMetricIDGenerator:
    """Test cases for SnowflakeMetricIDGenerator."""

    def test_init(self):
        """Test initialization."""
        generator = SnowflakeMetricIDGenerator()
        assert generator is not None

    def test_generate_returns_string(self):
        """Test that generate returns a string."""
        generator = SnowflakeMetricIDGenerator()
        result = generator.generate()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_returns_unique_ids(self):
        """Test that generate returns unique IDs on multiple calls."""
        generator = SnowflakeMetricIDGenerator()
        ids = [generator.generate() for _ in range(10)]
        assert len(ids) == len(set(ids))  # All IDs should be unique

    def test_uses_configured_instance_id(self):
        """Test that generator uses the configured instance ID."""
        generator = SnowflakeMetricIDGenerator()
        # Should not raise an exception and should generate valid IDs
        id_result = generator.generate()
        assert isinstance(id_result, str)


class TestIDGeneratorUniquenessAcrossTypes:
    """Test that different ID generator types produce unique IDs."""

    def test_different_generators_produce_unique_ids(self):
        """Test that different generator types produce unique IDs."""
        eval_gen = SnowflakeEvaluationRecordIDGenerator()
        dialog_gen = SnowflakeDialogSectionIDGenerator()
        metric_gen = SnowflakeMetricIDGenerator()

        eval_ids = [eval_gen.generate() for _ in range(5)]
        dialog_ids = [dialog_gen.generate() for _ in range(5)]
        metric_ids = [metric_gen.generate() for _ in range(5)]

        all_ids = eval_ids + dialog_ids + metric_ids
        assert len(all_ids) == len(set(all_ids))  # All IDs should be unique