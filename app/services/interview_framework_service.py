import json
import random
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

class InterviewFrameworkService:
    def __init__(self):
        self._frameworks_data = None
        self._load_frameworks()

    def _load_frameworks(self):
        try:
            # 使用相对路径：从 backend/app/services/interview_framework_service.py
            # 到 backend/app/config/prompts/evaluation/v3/frameworks/all.json
            # 向上两级到 backend/app，然后进入 config
            current_file = Path(__file__).resolve()
            # current_file = backend/app/services/interview_framework_service.py
            # parent.parent = backend/app
            app_dir = current_file.parent.parent
            json_path = app_dir / "config" / "prompts" / "evaluation" / "v3" / "frameworks" / "all.json"
            
            print(f"[InterviewFrameworkService] Loading frameworks from: {json_path}")
            print(f"[InterviewFrameworkService] File exists: {json_path.exists()}")
            
            if not json_path.exists():
                print(f"[InterviewFrameworkService] ❌ Framework file not found at: {json_path}")
                self._frameworks_data = {"interviewFrameworks": []}
                return
            
            with open(json_path, "r", encoding="utf-8") as f:
                self._frameworks_data = json.load(f)
            
            categories_count = len(self._frameworks_data.get("interviewFrameworks", []))
            print(f"[InterviewFrameworkService] ✅ Loaded {categories_count} framework categories")
            
            if categories_count == 0:
                print(f"[InterviewFrameworkService] ⚠️ Warning: No framework categories found in file")
        except Exception as e:
            print(f"[InterviewFrameworkService] ❌ Error loading frameworks: {e}")
            import traceback
            traceback.print_exc()
            self._frameworks_data = {"interviewFrameworks": []}

    def get_random_framework(self) -> Optional[Dict[str, Any]]:
        """
        Randomly select a framework from all available frameworks.
        Returns a dict with category and method details.
        """
        if not self._frameworks_data:
            print(f"[InterviewFrameworkService] ⚠️ No framework data loaded")
            return None
            
        categories = self._frameworks_data.get("interviewFrameworks", [])
        if not categories:
            print(f"[InterviewFrameworkService] ⚠️ No framework categories available")
            return None

        # Pick a random category
        category = random.choice(categories)
        methods = category.get("methods", [])
        if not methods:
            print(f"[InterviewFrameworkService] ⚠️ Category '{category.get('category')}' has no methods")
            return None

        # Pick a random method
        method = random.choice(methods)
        
        result = {
            "category": category.get("category"),
            "methodName": method.get("methodName"),
            "description": method.get("description"),
            "bestFor": method.get("bestFor")
        }
        print(f"[InterviewFrameworkService] ✅ Selected framework: {result['methodName']} ({result['category']})")
        return result

    def get_framework_by_name(self, method_name: str) -> Optional[Dict[str, Any]]:
        """Find a framework by its method name."""
        if not self._frameworks_data:
            return None
            
        for category in self._frameworks_data.get("interviewFrameworks", []):
            for method in category.get("methods", []):
                if method.get("methodName") == method_name:
                    return {
                        "category": category.get("category"),
                        "methodName": method.get("methodName"),
                        "description": method.get("description"),
                        "bestFor": method.get("bestFor")
                    }
        return None
    
    def get_all_frameworks_summary(self) -> str:
        """
        Get a formatted summary of all available frameworks for LLM selection.
        Returns a string that can be included in the prompt.
        """
        if not self._frameworks_data or not self._frameworks_data.get("interviewFrameworks"):
            return ""
        
        summary_parts = []
        for category in self._frameworks_data.get("interviewFrameworks", []):
            category_name = category.get("category", "")
            methods = category.get("methods", [])
            if not methods:
                continue
            
            category_summary = f"\n【{category_name}】\n"
            for method in methods:
                method_name = method.get("methodName", "")
                description = method.get("description", "")
                best_for = method.get("bestFor", "")
                category_summary += f"- {method_name}: {description} (适用于: {best_for})\n"
            
            summary_parts.append(category_summary)
        
        return "\n".join(summary_parts)

# Singleton instance
interview_framework_service = InterviewFrameworkService()

