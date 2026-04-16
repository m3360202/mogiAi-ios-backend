"""
面试参数配置加载服务
从 interview-params.json 加载练习模式的详细参数配置
"""
import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

class InterviewParamsService:
    """面试参数配置服务"""
    
    def __init__(self):
        self._params: Optional[Dict] = None
        self._load_params()
    
    def _load_params(self):
        """加载配置文件"""
        config_path = Path(__file__).parent.parent / "config" / "interview-params.json"
        
        if not config_path.exists():
            print(f"[WARNING] interview-params.json not found at {config_path}")
            self._params = self._get_default_params()
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._params = json.load(f)
            print(f"[InterviewParams] Loaded config from {config_path}")
        except Exception as e:
            print(f"[ERROR] Failed to load interview-params.json: {e}")
            self._params = self._get_default_params()
    
    def _get_default_params(self) -> Dict:
        """获取默认参数（fallback）"""
        return {
            "practice": {
                "basic": {
                    "rounds": 10,
                    "dimensions": [
                        {"key": "content", "name": "内容"},
                        {"key": "expression", "name": "表现力"},
                        {"key": "logic", "name": "伦理性"},
                        {"key": "attitude", "name": "态度"},
                        {"key": "professionalism", "name": "专业性"},
                        {"key": "fluency", "name": "流暢度"}
                    ]
                }
            }
        }
    
    def get_practice_mode_config(self, mode: str) -> Dict[str, Any]:
        """
        获取练习模式配置
        
        Args:
            mode: 'basic' 或 'advanced'
            
        Returns:
            模式配置字典
        """
        if not self._params:
            self._load_params()
        
        return self._params.get("practice", {}).get(mode, {})
    
    def get_basic_dimensions(self) -> List[Dict[str, Any]]:
        """获取基础篇的所有维度配置"""
        config = self.get_practice_mode_config("basic")
        return config.get("dimensions", [])
    
    def get_basic_rounds(self) -> int:
        """获取基础篇的轮次数"""
        config = self.get_practice_mode_config("basic")
        return config.get("rounds", 10)
    
    def get_dimension_by_key(self, dimension_key: str) -> Optional[Dict[str, Any]]:
        """
        根据维度key获取维度配置
        
        Args:
            dimension_key: 维度key，如 'content', 'expression'
            
        Returns:
            维度配置字典，如果未找到返回None
        """
        dimensions = self.get_basic_dimensions()
        for dim in dimensions:
            if dim.get("key") == dimension_key:
                return dim
        return None
    
    def get_advanced_scenarios(self) -> List[Dict[str, Any]]:
        """获取应用篇的所有场景配置"""
        config = self.get_practice_mode_config("advanced")
        return config.get("scenarios", [])
    
    def get_advanced_rounds(self) -> Dict[str, int]:
        """获取应用篇的轮次配置"""
        config = self.get_practice_mode_config("advanced")
        rounds = config.get("rounds", {})
        if isinstance(rounds, dict):
            return rounds
        return {"min": 15, "max": 20, "default": 18}
    
    def get_scenario_by_key(self, scenario_key: str) -> Optional[Dict[str, Any]]:
        """
        根据场景key获取场景配置
        
        Args:
            scenario_key: 场景key，如 'team_difficulty'
            
        Returns:
            场景配置字典，如果未找到返回None
        """
        scenarios = self.get_advanced_scenarios()
        for scenario in scenarios:
            if scenario.get("key") == scenario_key:
                return scenario
        return None
    
    def build_dimension_prompt(self, dimension_key: str, user_answer: str) -> str:
        """
        根据维度配置构建智能提示词
        
        Args:
            dimension_key: 维度key
            user_answer: 用户回答
            
        Returns:
            生成的提示词
        """
        dimension = self.get_dimension_by_key(dimension_key)
        if not dimension:
            return f"{dimension_key}に関する質問: {user_answer}"
        
        name = dimension.get("name", dimension_key)
        focus = dimension.get("focus", "")
        prompt_focus = dimension.get("prompt_focus", [])
        
        # 构建详细的提示词
        prompt = f"""あなたは日本語の面接官です。以下の評価軸に基づいて質問してください：

【評価軸】: {name}
【重点】: {focus}

【評価基準】:
"""
        for i, focus_item in enumerate(prompt_focus[:4], 1):  # 只使用前4个要点
            prompt += f"{i}. {focus_item}\n"
        
        prompt += f"""
【応募者の回答】:
{user_answer}

上記の評価基準に基づき、応募者の回答に対して1つの具体的な質問をしてください。
質問は簡潔で明確にし、評価やコメントは含めないでください。"""
        
        return prompt
    
    def build_scenario_prompt(self, scenario_key: str, user_answer: str) -> str:
        """
        根据场景配置构建智能提示词
        
        Args:
            scenario_key: 场景key
            user_answer: 用户回答
            
        Returns:
            生成的提示词
        """
        scenario = self.get_scenario_by_key(scenario_key)
        if not scenario:
            return f"{scenario_key}に関する質問: {user_answer}"
        
        name = scenario.get("name", scenario_key)
        description = scenario.get("description", "")
        prompt_focus = scenario.get("prompt_focus", [])
        
        # 构建详细的提示词
        prompt = f"""あなたは日本語の面接官です。以下のシナリオに基づいて質問してください：

【シナリオ】: {name}
【説明】: {description}

【評価ポイント】:
"""
        for i, focus_item in enumerate(prompt_focus[:4], 1):  # 只使用前4个要点
            prompt += f"{i}. {focus_item}\n"
        
        prompt += f"""
【応募者の回答】:
{user_answer}

上記の評価ポイントに基づき、応募者の回答に対して1つの具体的な質問をしてください。
質問は簡潔で明確にし、評価やコメントは含めないでください。"""
        
        return prompt
    
    def get_dimension_evaluation_criteria(self, dimension_key: str) -> List[str]:
        """获取维度的评估标准"""
        dimension = self.get_dimension_by_key(dimension_key)
        if dimension:
            return dimension.get("evaluation_criteria", [])
        return []
    
    def get_dimension_weight(self, dimension_key: str) -> float:
        """获取维度的权重"""
        dimension = self.get_dimension_by_key(dimension_key)
        if dimension:
            return dimension.get("weight", 0.0)
        return 0.0
    
    def get_framework_use_probability(self) -> float:
        """
        获取框架使用概率
        
        Returns:
            框架使用概率 (0.0 到 1.0)，默认 0.9 (90%)
        """
        return 0.9  # 90% 概率使用框架


# 创建单例实例
interview_params_service = InterviewParamsService()

