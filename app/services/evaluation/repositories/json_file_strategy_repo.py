"""
JSON file-backed implementation of EvaluationStrategyRepo for evaluation feature.
Allows configuration of strategies through JSON files.
"""
import json
import os
from typing import Dict, Optional, List
from threading import Lock
from pydantic import BaseModel, Field

from ..business import (
    EvaluationStrategy, 
    EvaluationStrategyRepo,
    SuperMetricMetadata,
    MetricMetadata,
    SuperMetricType,
    MetricType,
)


class MetricConfigModel(BaseModel):
    """Pydantic model for metric configuration in JSON."""
    type: str = Field(..., description="Metric type as string")
    description: Optional[str] = Field(None, description="Optional metric description")
    model: str = Field(default="gpt-4o", description="Model for LLM-based evaluation")
    weight: float = Field(default=1.0, description="Weight of this metric in the overall evaluation")
    eval_system_prompt_path: Optional[str] = Field(None, description="Path to evaluation system prompt file")


class SuperMetricConfigModel(BaseModel):
    """Pydantic model for super-metric configuration in JSON."""
    type: str = Field(..., description="Super-metric type as string")
    description: Optional[str] = Field(None, description="Optional super-metric description")
    metrics: List[MetricConfigModel] = Field(..., description="List of metrics in this super-metric")
    weight: float = Field(default=1.0, description="Weight of this super-metric in the overall evaluation")


class StrategyConfigModel(BaseModel):
    """Pydantic model for strategy configuration in JSON."""
    strategy_id: str = Field(..., description="Unique strategy identifier")
    name: str = Field(..., description="Strategy name")
    description: str = Field(default="", description="Strategy description")
    super_metrics: List[SuperMetricConfigModel] = Field(..., description="List of super-metrics")


class StrategiesFileModel(BaseModel):
    """Pydantic model for the entire strategies JSON file."""
    strategies: List[StrategyConfigModel] = Field(..., description="List of evaluation strategies")


class JsonFileEvaluationStrategyRepo(EvaluationStrategyRepo):
    """
    JSON file-backed implementation of EvaluationStrategyRepo.
    Thread-safe for concurrent access.
    Loads strategies from a JSON configuration file.
    """
    
    def __init__(self, json_file_path: str) -> None:
        self._strategies: Dict[str, EvaluationStrategy] = {}
        self._lock = Lock()
        self._json_file_path = json_file_path
        self._load_strategies_from_file()
    
    def save(self, strategy: EvaluationStrategy) -> None:
        """Save an evaluation strategy (in-memory only, doesn't update JSON file)."""
        with self._lock:
            self._strategies[strategy.strategy_id] = strategy
    
    def get_by_id(self, strategy_id: str) -> Optional[EvaluationStrategy]:
        """Get evaluation strategy by ID."""
        with self._lock:
            return self._strategies.get(strategy_id)
    
    def get_all(self) -> List[EvaluationStrategy]:
        """Get all evaluation strategies."""
        with self._lock:
            return list(self._strategies.values())
    
    def clear(self) -> None:
        """Clear all strategies (useful for testing)."""
        with self._lock:
            self._strategies.clear()
    
    def reload_from_file(self) -> None:
        """Reload strategies from the JSON file."""
        with self._lock:
            self._strategies.clear()
            self._load_strategies_from_file()
    
    def _load_strategies_from_file(self) -> None:
        """Load evaluation strategies from JSON file using Pydantic validation."""
        if not os.path.exists(self._json_file_path):
            raise FileNotFoundError(f"Strategy configuration file not found: {self._json_file_path}")
        
        try:
            with open(self._json_file_path, 'r', encoding='utf-8') as file:
                raw_data = json.load(file)
            
            # Parse and validate the JSON using Pydantic
            strategies_file = StrategiesFileModel.model_validate(raw_data)
            
            # Convert Pydantic models to business domain objects
            for strategy_config in strategies_file.strategies:
                strategy = self._convert_config_to_strategy(strategy_config)
                self._strategies[strategy.strategy_id] = strategy
                
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Error parsing strategy configuration file: {e}")
    
    def _convert_config_to_strategy(self, strategy_config: StrategyConfigModel) -> EvaluationStrategy:
        """Convert Pydantic strategy config model to business domain EvaluationStrategy."""
        super_metric_metadata_list: List[SuperMetricMetadata] = []
        
        for super_metric_config in strategy_config.super_metrics:
            super_metric_metadata = self._convert_super_metric_config(super_metric_config)
            super_metric_metadata_list.append(super_metric_metadata)
        
        return EvaluationStrategy(
            strategy_id=strategy_config.strategy_id,
            name=strategy_config.name,
            description=strategy_config.description,
            super_metric_metadata_list=super_metric_metadata_list
        )
    
    def _convert_super_metric_config(self, super_metric_config: SuperMetricConfigModel) -> SuperMetricMetadata:
        """Convert Pydantic super-metric config model to business domain SuperMetricMetadata."""
        try:
            super_metric_type = SuperMetricType(super_metric_config.type)
        except ValueError as exc:
            raise ValueError(f"Invalid super metric type: {super_metric_config.type}") from exc
        
        metric_metadata_list: List[MetricMetadata] = []
        
        for metric_config in super_metric_config.metrics:
            try:
                metric_type = MetricType(metric_config.type)
            except ValueError as exc:
                raise ValueError(f"Invalid metric type: {metric_config.type}") from exc
            
            metric_metadata = MetricMetadata(
                metric_type=metric_type, 
                model=metric_config.model,
                weight=metric_config.weight,
                eval_system_prompt_path=metric_config.eval_system_prompt_path
            )
            metric_metadata_list.append(metric_metadata)
        
        return SuperMetricMetadata(
            super_metric_type=super_metric_type,
            metric_metadata_list=metric_metadata_list,
            weight=super_metric_config.weight
        )