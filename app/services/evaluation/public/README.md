# Evaluation API

The Evaluation API provides a simplified interface for evaluating dialog conversations without needing to understand the internal complexity of the evaluation system.

## Overview

The `EvaluationAPI` encapsulates all the dependencies and setup required for the evaluation use case, providing a clean interface for external modules to evaluate dialogs.

## Quick Start

```python
from app.services.evaluation.public import EvaluationAPI, EvaluationAPIImpl

# Create the API instance - handles all dependency setup automatically
evaluation_api: EvaluationAPI = EvaluationAPIImpl()

# Evaluate a dialog (uses "strategy_1" as default)
evaluation_result = evaluation_api.evaluate(raw_dialog_info)
```

## API Interface

### `EvaluationAPI`

Abstract interface for evaluation operations.

#### Methods

- `evaluate(raw_dialog_info: RawDialogInfo, strategy_id: Optional[str] = None) -> EvaluationRecord`

  - Evaluates a raw dialog and returns the evaluation record
  - If `strategy_id` is not provided, uses "strategy_1" as the default strategy

- `get_available_strategies() -> List[EvaluationStrategy]`

  - Returns list of available evaluation strategies

- `reset_repositories() -> None` (EvaluationAPIImpl only)
  - Resets all in-memory repositories to clean state

## Implementation

### `EvaluationAPIImpl`

Concrete implementation that manages all dependencies internally.

#### Constructor

```python
EvaluationAPIImpl(
    evaluation_strategies_file_path: Optional[str] = None
)
```

**Parameters:**

- `evaluation_strategies_file_path`: Optional path to evaluation strategies JSON file. If not provided, uses default path (`app/config/evaluation_strategies.json`)

**Internal Logger:**

- Uses a built-in `SimpleLogger` that only outputs warnings and errors to console
- No external logger dependency required

#### Managed Dependencies

The implementation automatically creates and manages:

- **Repositories**: Dialog sections, metrics, evaluation records, evaluation strategies
- **ID Generators**: Snowflake-based generators for all entities
- **Services**: Dialog section builders, metric calculators, feedback services
- **Use Case**: Complete evaluation use case with all dependencies

## Usage Examples

### Basic Usage

```python
from app.services.evaluation.public import EvaluationAPIImpl

# Simple usage with default configuration
api = EvaluationAPIImpl()
result = api.evaluate(raw_dialog_info)  # Uses "strategy_1" by default

print(f"Overall Score: {result.overall_score.numeric_score}/100")
```

### With Specific Strategy

```python
# Evaluate with specific strategy
result = api.evaluate(raw_dialog_info, "strategy_1")

# Or get available strategies first
strategies = api.get_available_strategies()
strategy_id = strategies[0].strategy_id
result = api.evaluate(raw_dialog_info, strategy_id)
```

### Custom Strategies File

```python
# Use custom strategies configuration
api = EvaluationAPIImpl(
    evaluation_strategies_file_path="/path/to/custom/strategies.json"
)
```

## Data Structures

### Input: `RawDialogInfo`

Contains the dialog to be evaluated:

```python
raw_dialog_info = RawDialogInfo(
    dialog_id="unique_dialog_id",
    messages=[
        DialogMessage(
            section_id="",  # Will be populated automatically
            role=MessageRole.INTERVIEWER,  # or MessageRole.CANDIDATE
            content="Message content",
            start_time=datetime_object,
            end_time=datetime_object
        ),
        # ... more messages
    ]
)
```

### Output: `EvaluationRecord`

Contains the complete evaluation results:

```python
evaluation_record = EvaluationRecord(
    id="evaluation_record_id",
    strategy=evaluation_strategy,
    interview_record_id="dialog_id",
    super_metrics=[...],  # List of SuperMetric objects
    overall_score=Score(...)  # Overall evaluation score
)
```

## Error Handling

The API raises the following exceptions:

- `ValueError`: When "strategy_1" (default) is not found or specified strategy_id is not found
- `Exception`: For general evaluation failures

**Default Strategy:**

- The API uses "strategy_1" as the default strategy when no strategy_id is provided
- This corresponds to the "sub-metrics-llm-rules-aggregation" strategy in the configuration

## Testing

See `example_usage.py` for a complete working example and `test_api.py` for basic API testing.

## Integration with Existing System

The API is built on top of the existing evaluation system and uses the same patterns as the integration test (`integration_test_full_workflow.py`). It automatically sets up all the required dependencies without exposing the complexity to the caller.

## Architecture

```
EvaluationAPI
├── EvaluationUseCaseImpl
├── Repositories (In-Memory)
│   ├── DialogSectionRepo
│   ├── MetricRepo
│   ├── EvaluationRecordRepo
│   └── EvaluationStrategyRepo (JSON-based)
├── Services
│   ├── DialogSectionBuilder
│   ├── MetricCalcServiceBuilder
│   ├── SuperMetricCalcServiceBuilder
│   ├── EvaluationCalcServiceBuilder
│   └── SuperMetricFeedbackServiceBuilder
└── ID Generators
    ├── DialogSectionIDGenerator
    ├── MetricIDGenerator
    └── EvaluationRecordIDGenerator
```

The API abstracts away this complexity and provides a single entry point for evaluation operations.
