"""
Tests for JSON file-backed evaluation strategy repository.
"""
import json
import tempfile
import os

from app.services.evaluation.business import (
    SuperMetricType,
    MetricType,
)
from app.services.evaluation.repositories import JsonFileEvaluationStrategyRepo


def test_json_file_strategy_repo():
    """Test JSON file-backed strategy repository functionality."""
    print("Testing JSON file-backed strategy repository...")
    
    # Create a temporary JSON file for testing
    test_strategies = {
        "strategies": [
            {
                "strategy_id": "test_strategy",
                "name": "Test Strategy",
                "description": "A test evaluation strategy",
                "super_metrics": [
                    {
                        "type": "CLARITY",
                        "metrics": [
                            {"type": "CONCISENESS"},
                            {"type": "LOGICAL_STRUCTURE"}
                        ]
                    }
                ]
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
        json.dump(test_strategies, temp_file, indent=2)
        temp_file_path = temp_file.name
    
    try:
        # Test loading from JSON file
        repo = JsonFileEvaluationStrategyRepo(temp_file_path)
        
        # Verify strategy was loaded
        strategy = repo.get_by_id("test_strategy")
        assert strategy is not None, "Strategy should be loaded from JSON file"
        assert strategy.name == "Test Strategy"
        assert len(strategy.super_metric_metadata_list) == 1
        print(f"✓ Successfully loaded strategy: {strategy.name}")
        
        # Test get_all
        all_strategies = repo.get_all()
        assert len(all_strategies) == 1
        print(f"✓ Retrieved {len(all_strategies)} strategies from JSON file")
        
        # Test super metric metadata
        clarity_super_metric = strategy.super_metric_metadata_list[0]
        assert clarity_super_metric.super_metric_type == SuperMetricType.CLARITY
        assert len(clarity_super_metric.metric_metadata_list) == 2
        
        # Test metric metadata
        metric_types = [m.metric_type for m in clarity_super_metric.metric_metadata_list]
        assert MetricType.CONCISENESS in metric_types
        assert MetricType.LOGICAL_STRUCTURE in metric_types
        print("✓ Strategy metadata correctly parsed from JSON")
        
    finally:
        # Clean up temporary file
        os.unlink(temp_file_path)
    
    print("JSON file-backed strategy repository tests passed! ✓")


def test_real_config_file():
    """Test loading from the actual configuration file."""
    print("\nTesting real configuration file...")
    
    config_path = "/Users/wanghuan/Documents/py_repos/career_face_backend/app/config/evaluation_strategies.json"
    
    if not os.path.exists(config_path):
        print("⚠️  Configuration file not found, skipping real config test")
        return
    
    try:
        # Load from real config file
        repo = JsonFileEvaluationStrategyRepo(config_path)
        
        # Test strategies are loaded
        all_strategies = repo.get_all()
        print(f"✓ Loaded {len(all_strategies)} strategies from config file")
        
        # Check for expected strategies
        strategy_ids = [s.strategy_id for s in all_strategies]
        expected_strategies = ["default_strategy", "technical_strategy", "behavioral_strategy", "leadership_strategy"]
        
        for expected_id in expected_strategies:
            if expected_id in strategy_ids:
                strategy = repo.get_by_id(expected_id)
                if strategy:
                    print(f"✓ Found strategy '{expected_id}': {strategy.name}")
                    print(f"  - Super metrics: {len(strategy.super_metric_metadata_list)}")
                    
                    for super_metric in strategy.super_metric_metadata_list:
                        print(f"    - {super_metric.super_metric_type.value}: {len(super_metric.metric_metadata_list)} metrics")
        
        # Test reload functionality
        repo.reload_from_file()
        reloaded_strategies = repo.get_all()
        assert len(reloaded_strategies) == len(all_strategies)
        print("✓ File reload functionality works correctly")
        
    except Exception as e:
        print(f"❌ Error testing real config file: {e}")
        raise
    
    print("Real configuration file tests passed! ✓")


if __name__ == "__main__":
    test_json_file_strategy_repo()
    test_real_config_file()
    print("\n🎉 All JSON strategy repository tests completed successfully!")