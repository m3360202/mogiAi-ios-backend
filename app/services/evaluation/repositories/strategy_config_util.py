#!/usr/bin/env python3
"""
Utility script for managing evaluation strategy configurations.
Provides validation, inspection, and examples for JSON strategy files.
"""
import json
import sys
import os
from typing import List, Dict, Any

# Add the project root to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from app.services.evaluation.repositories import JsonFileEvaluationStrategyRepo
from app.services.evaluation.business import SuperMetricType, MetricType


def validate_strategy_file(file_path: str) -> bool:
    """Validate a strategy configuration file."""
    try:
        print(f"Validating strategy file: {file_path}")
        
        # Try to load the repository
        repo = JsonFileEvaluationStrategyRepo(file_path)
        strategies = repo.get_all()
        
        print(f"✓ Successfully loaded {len(strategies)} strategies")
        
        # Validate each strategy
        for strategy in strategies:
            print(f"\n📋 Strategy: {strategy.name} (ID: {strategy.strategy_id})")
            print(f"   Description: {strategy.description}")
            print(f"   Super Metrics: {len(strategy.super_metric_metadata_list)}")
            
            for super_metric in strategy.super_metric_metadata_list:
                print(f"     • {super_metric.super_metric_type.value}: {len(super_metric.metric_metadata_list)} metrics")
                for metric in super_metric.metric_metadata_list:
                    print(f"       - {metric.metric_type.value}")
        
        print(f"\n✅ Validation successful! File contains {len(strategies)} valid strategies.")
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False


def show_available_types():
    """Show available super metric and metric types."""
    print("\n📖 Available Types for Configuration:")
    
    print("\n🔹 Super Metric Types:")
    for super_metric_type in SuperMetricType:
        print(f"   • {super_metric_type.value}")
    
    print("\n🔹 Metric Types:")
    for metric_type in MetricType:
        print(f"   • {metric_type.value}")


def generate_example_strategy() -> Dict[str, Any]:
    """Generate an example strategy configuration."""
    return {
        "strategy_id": "custom_example",
        "name": "Custom Example Strategy",
        "description": "An example strategy demonstrating the configuration format",
        "super_metrics": [
            {
                "type": "CLARITY",
                "description": "Evaluates communication clarity",
                "metrics": [
                    {
                        "type": "CONCISENESS",
                        "description": "Measures response conciseness"
                    },
                    {
                        "type": "LOGICAL_STRUCTURE", 
                        "description": "Assesses logical flow"
                    }
                ]
            },
            {
                "type": "EVIDENCE",
                "description": "Evaluates supporting evidence quality",
                "metrics": [
                    {
                        "type": "RELEVANCE",
                        "description": "Measures relevance to question"
                    }
                ]
            }
        ]
    }


def create_example_file(output_path: str):
    """Create an example strategy configuration file."""
    example_config = {
        "strategies": [
            generate_example_strategy()
        ]
    }
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(example_config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Created example configuration file: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to create example file: {e}")
        return False


def main():
    """Main CLI interface."""
    if len(sys.argv) < 2:
        print("🛠️  Evaluation Strategy Configuration Utility")
        print("\nUsage:")
        print("  python strategy_config_util.py validate <file_path>    - Validate a strategy file")
        print("  python strategy_config_util.py example <output_path>   - Create example file")
        print("  python strategy_config_util.py types                   - Show available types")
        print("  python strategy_config_util.py inspect <file_path>     - Inspect a strategy file")
        return
    
    command = sys.argv[1]
    
    if command == "validate" and len(sys.argv) >= 3:
        file_path = sys.argv[2]
        validate_strategy_file(file_path)
    
    elif command == "example" and len(sys.argv) >= 3:
        output_path = sys.argv[2]
        create_example_file(output_path)
    
    elif command == "types":
        show_available_types()
    
    elif command == "inspect" and len(sys.argv) >= 3:
        file_path = sys.argv[2]
        if validate_strategy_file(file_path):
            show_available_types()
    
    else:
        print("❌ Invalid command or missing arguments")
        print("Use 'python strategy_config_util.py' to see usage help")


if __name__ == "__main__":
    main()