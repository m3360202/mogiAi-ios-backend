"""
Integration test for evaluation strategies with model parameters.

This test demonstrates how the evaluation strategies JSON can be used
to create metric calculation services with specific models.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.services.evaluation.business import (
    MetricMetadata,
    MetricType,
    Logger,
    IdGenerator
)
from app.services.evaluation.services.evaluation_calc_services.metric import DefaultMetricCalcServiceBuilder


class MockLogger(Logger):
    """Simple mock logger implementation."""
    
    def debug(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"DEBUG: {message}")
    
    def info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"INFO: {message}")
    
    def warning(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"WARNING: {message}")
    
    def error(self, message: str, error: Optional[Exception] = None, context: Optional[Dict[str, Any]] = None) -> None:
        print(f"ERROR: {message}")


class MockIdGenerator(IdGenerator):
    """Simple test ID generator implementation."""
    
    def __init__(self):
        self.counter = 0
    
    def generate(self) -> str:
        self.counter += 1
        return f"test_id_{self.counter}"


def test_evaluation_strategy_with_models():
    """Test creating services from evaluation strategy configuration."""
    print("=== Testing Evaluation Strategy with Model Parameters ===")
    
    # Load evaluation strategies
    strategies_path = Path("app/config/evaluation_strategies.json")
    with open(strategies_path, 'r') as f:
        strategies_data = json.load(f)
    
    logger = MockLogger()
    id_generator = MockIdGenerator()
    builder = DefaultMetricCalcServiceBuilder(logger, id_generator)
    
    # Get the first strategy
    strategy = strategies_data["strategies"][0]
    print(f"Testing strategy: {strategy['name']}")
    
    created_services = []
    
    # Process each super-metric and its metrics
    for super_metric in strategy["super_metrics"]:
        print(f"\nProcessing super-metric: {super_metric['type']}")
        
        for metric_config in super_metric["metrics"]:
            metric_type_str = metric_config["type"]
            model = metric_config["model"]
            
            print(f"  Creating service for metric: {metric_type_str} with model: {model}")
            
            try:
                # Convert string to enum
                metric_type = MetricType[metric_type_str]
                
                # Create metadata with model
                metadata = MetricMetadata(metric_type=metric_type, model=model)
                
                # Only create service for implemented metrics
                if metric_type == MetricType.CONCISENESS:
                    service = builder.build(metadata)
                    created_services.append({
                        "metric_type": metric_type_str,
                        "model": model,
                        "service": service
                    })
                    print(f"    ✅ Created {type(service).__name__} with model {service.model}")
                else:
                    print(f"    ⚠️  Metric type {metric_type_str} not yet implemented")
                    
            except KeyError:
                print(f"    ❌ Unknown metric type: {metric_type_str}")
            except Exception as e:
                print(f"    ❌ Failed to create service: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Successfully created {len(created_services)} services:")
    for service_info in created_services:
        print(f"  - {service_info['metric_type']} using {service_info['model']}")
    
    return created_services


if __name__ == "__main__":
    test_evaluation_strategy_with_models()