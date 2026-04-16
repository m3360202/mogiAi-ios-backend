"""
Example usage of the TwoPhaseEvaluationAPI.

This module demonstrates how to use the public TwoPhaseEvaluationAPI to evaluate dialogs
using a two-phase approach without needing to understand the internal complexity of the evaluation system.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging
import logging.handlers

from app.services.evaluation.business import (
    DialogMessage, RawDialogInfo, MessageRole, Logger, StrategyId
)
from app.services.evaluation.public import TwoPhaseEvaluationAPI, TwoPhaseEvaluationAPIImpl
import logging

def load_dialog_from_json(json_file_path: str) -> RawDialogInfo:
    """Load dialog data from JSON file and convert to RawDialogInfo format."""
    with open(json_file_path, 'r', encoding='utf-8') as f:
        dialog_data = json.load(f)
    
    # Convert messages to DialogMessage format
    messages = []
    for msg in dialog_data["messages"]:
        # Convert role
        if msg["role"] in ["ai", "interviewer"]:
            role = MessageRole.INTERVIEWER
        elif msg["role"] in ["human", "candidate"]:
            role = MessageRole.CANDIDATE
        else:
            continue  # Skip unknown roles
        
        # Convert timestamps to datetime objects
        start_time = datetime.fromtimestamp(msg["start_time"])
        end_time = datetime.fromtimestamp(msg["end_time"])
        
        dialog_message = DialogMessage(
            section_id="",  # Will be populated by dialog section builder
            role=role,
            content=msg["content"],
            start_time=start_time,
            end_time=end_time
        )
        messages.append(dialog_message)
    
    return RawDialogInfo(
        dialog_id=dialog_data["dialog_id"], 
        messages=messages
    )





async def main() -> None:
    """Main function to demonstrate two-phase evaluation API usage."""
    
    overall_start_time = time.time()
    
    # 1. Create the API instance - it handles all dependency setup automatically
    print("� Creating TwoPhaseEvaluationAPI...")
    api_creation_start = time.time()
    evaluation_api: TwoPhaseEvaluationAPI = TwoPhaseEvaluationAPIImpl()
    api_creation_time = time.time() - api_creation_start
    print(f"✅ TwoPhaseEvaluationAPI created successfully! (⏱️  {api_creation_time:.2f}s)")
    print()
    
    # 2. Check available strategies
    print("📋 Available evaluation strategies:")
    strategy_fetch_start = time.time()
    strategies = evaluation_api.get_available_strategies()
    strategy_fetch_time = time.time() - strategy_fetch_start
    for i, strategy in enumerate(strategies, 1):
        print(f"  {i}. {strategy.name} (ID: {strategy.strategy_id})")
        print(f"     Super-metrics: {[sm.super_metric_type.value for sm in strategy.super_metric_metadata_list]}")
    print(f"⏱️  Strategy fetch time: {strategy_fetch_time:.2f}s")
    print()
    
    print("💡 Default strategy: 'strategy_1' will be used if no strategy is specified")
    print()
    
    # 3. Load test dialog
    print("📂 Loading test dialog...")
    dialog_load_start = time.time()
    current_dir = Path(__file__).parent
    # Navigate up to project root, then to test dialogs
    dialog_file_path = current_dir.parent.parent.parent.parent / "test" / "dialogs" / "yPmCeswgdX9F4bW5jYtWeP_raw.json"
    
    if not dialog_file_path.exists():
        print(f"❌ Test dialog file not found: {dialog_file_path}")
        print("Please ensure the test dialog file exists or update the path.")
        return
    
    raw_dialog_info = load_dialog_from_json(str(dialog_file_path))
    dialog_load_time = time.time() - dialog_load_start
    print(f"✅ Loaded dialog: {raw_dialog_info.dialog_id} ({len(raw_dialog_info.messages)} messages) (⏱️  {dialog_load_time:.2f}s)")
    print()
    
    # 4. Evaluate using the two-phase API - step by step!
    print("🔍 Evaluating dialog using two-phase approach...")
    evaluation_start = time.time()
    try:
        # Step 1: Build dialog sections
        dialog_sections = await evaluation_api.build_sections(raw_dialog_info)
        
        # Step 2: Evaluate each section individually (Phase 1)
        section_results = []
        for section in dialog_sections:
            section_result = await evaluation_api.evaluate_section(section)
            section_results.append(section_result)
        
        # Step 3: Generate overall evaluation from section results (Phase 2)
        evaluation_record = await evaluation_api.evaluate_overall(section_results)
        
        evaluation_time = time.time() - evaluation_start
        print(f"✅ Two-phase evaluation completed! (⏱️  {evaluation_time:.2f}s)")
        print()
        
        # 5. Display results
        print("� EVALUATION RESULTS:")
        print(f"  Record ID: {evaluation_record.id}")
        print(f"  Overall Score: {evaluation_record.overall_score.numeric_score:.1f}/100")
        print(f"  Score Label: {evaluation_record.overall_score.score_label.value}")
        print(f"  Strategy Used: {evaluation_record.strategy.name}")
        print(f"  Super-metrics: {len(evaluation_record.super_metrics)}")
        print()
        
        print("🎯 SUPER-METRIC DETAILS:")
        for i, super_metric in enumerate(evaluation_record.super_metrics, 1):
            print(f"  {i}. {super_metric.metadata.super_metric_type.value}")
            print(f"     Score: {super_metric.score.numeric_score:.1f}/100 ({super_metric.score.score_label.value})")
            print(f"     Weight: {super_metric.metadata.weight}")

            # Display brief feedback
            print(f"     Brief Feedback: {super_metric.feedback.brief_feedback}")
            
            # Display feedback preview
            if hasattr(super_metric.feedback, 'feedback'):
                feedback_text = super_metric.feedback.feedback
            else:
                feedback_text = str(super_metric.feedback) if super_metric.feedback else ""
            
            print(f"     Feedback: {feedback_text}")
            print()
        
        # Calculate and display total time
        total_time = time.time() - overall_start_time
        print("⏱️  TIMING SUMMARY:")
        print(f"  API Creation: {api_creation_time:.2f}s")
        print(f"  Strategy Fetch: {strategy_fetch_time:.2f}s")
        print(f"  Dialog Loading: {dialog_load_time:.2f}s")
        print(f"  Two-Phase Evaluation: {evaluation_time:.2f}s")
        print(f"  Total Time: {total_time:.2f}s")
        print()
        
        print("🎉 Two-phase evaluation API example completed successfully!")
        
    except Exception as e:
        evaluation_time = time.time() - evaluation_start
        total_time = time.time() - overall_start_time
        print(f"❌ Two-phase evaluation failed after {evaluation_time:.2f}s (Total: {total_time:.2f}s): {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())