"""
Fast Interview Evaluator - 快速面试评估服务
一次LLM调用获取所有维度的评分和评语
使用 v3/content 预设规则
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel


class DimensionScore(BaseModel):
    """单个维度的评分"""
    score: int  # 0-100分（与v3体系对齐）
    brief_feedback: str  # 简要评语 (20-30字)
    detailed_feedback: str  # 详细反馈（包含详细评价和改进建议）


class FastEvaluationResult(BaseModel):
    """快速评估结果"""
    overall_score: float  # 总分 0-100（平均分）
    overall_brief: str  # 整体简评 (30-50字)
    dimensions: Dict[str, DimensionScore]  # 各维度评分
    # 4个维度（v3/content体系）: clarity(明确性), evidence(根据), impact(影响力), engagement(参与度)


class FastInterviewEvaluator:
    """快速面试评估器 - 一次LLM调用搞定所有评估，使用v3/content规则"""
    
    def __init__(self):
        """初始化评估器"""
        from app.core.llm_factory import llm_factory
        self.client, self.model = llm_factory.get_non_visual_client()
        
        # v3/content 的4个评估维度
        self.dimensions = {
            "clarity": "明确性",
            "evidence": "根据",
            "impact": "影响力",
            "engagement": "参与度"
        }
        
        # 加载v3/content规则
        self.v3_rules = self._load_v3_content_rules()
    
    def _load_v3_content_rules(self) -> Dict[str, Dict[str, str]]:
        """加载v3/content下的预设规则"""
        rules = {}
        base_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content"
        
        for dim_key, dim_name in self.dimensions.items():
            dim_path = base_path / dim_key / "system_msg_zh.md"
            if dim_path.exists():
                try:
                    content = dim_path.read_text(encoding='utf-8')
                    # 提取关键信息：维度定义、词汇集
                    definition_match = re.search(r'\*\*{dimension_name}.*?\*\*:\s*(.+?)(?:\n|$)', content, re.MULTILINE)
                    vocab_match = re.search(r'优先词汇[：:]\s*(.+?)(?:\n|$)', content, re.MULTILINE)
                    avoid_match = re.search(r'避免词汇[：:]\s*(.+?)(?:\n|$)', content, re.MULTILINE)
                    
                    rules[dim_key] = {
                        "definition": definition_match.group(1).strip() if definition_match else f"{dim_name}的评估标准",
                        "priority_vocab": vocab_match.group(1).strip() if vocab_match else "",
                        "avoid_vocab": avoid_match.group(1).strip() if avoid_match else "",
                        "full_prompt": content  # 保留完整prompt用于参考
                    }
                except Exception as e:
                    print(f"[FastEvaluator] ⚠️ Failed to load rule for {dim_key}: {e}")
                    # Fallback
                    rules[dim_key] = {
                        "definition": f"{dim_name}的评估标准",
                        "priority_vocab": "",
                        "avoid_vocab": "",
                        "full_prompt": ""
        }
            else:
                # Fallback
                rules[dim_key] = {
                    "definition": f"{dim_name}的评估标准",
                    "priority_vocab": "",
                    "avoid_vocab": "",
                    "full_prompt": ""
                }
        
        return rules
    
    async def evaluate(
        self,
        interview_data: List[Dict[str, Any]],
        position: str = "候选人",
        language: str = "zh"
    ) -> FastEvaluationResult:
        """
        快速评估面试表现（使用v3/content规则）
        
        Args:
            interview_data: 面试对话数据 [{"role": "system/user", "content": "...", "timestamp": ...}]
            position: 应聘职位
            language: 语言代码 (zh/ja/en)
            
        Returns:
            FastEvaluationResult: 评估结果
        """
        print(f"[FastEvaluator] 🚀 Starting fast evaluation (v3/content rules) for {len(interview_data)} messages...")
        
        # 构建简洁的对话历史
        conversation = []
        for item in interview_data:
            role = "面试官" if item.get("role") in ("system", "agent") else "候选人"
            content = item.get("content", "")
            conversation.append(f"{role}: {content}")
        
        conversation_text = "\n\n".join(conversation)
        
        # 构建prompt（使用v3规则）
        system_prompt = self._build_system_prompt_v3(position, language)
        user_prompt = self._build_user_prompt_v3(conversation_text, language)
        
        try:
            # 调用LLM
            print(f"[FastEvaluator] 📡 Calling {self.model}...")
            start_time = __import__('time').time()
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=3000,  # 增加token以支持详细反馈
            )
            
            elapsed = __import__('time').time() - start_time
            print(f"[FastEvaluator] ✅ LLM responded in {elapsed:.2f}s")
            
            # 解析结果
            result_text = response.choices[0].message.content
            result_json = json.loads(result_text)
            
            print(f"[FastEvaluator] 📊 Parsing evaluation result...")
            
            # 转换为FastEvaluationResult（v3格式）
            dimensions = {}
            total_score = 0.0
            valid_dims = 0
            
            for dim_key, dim_name in self.dimensions.items():
                dim_data = result_json.get("dimensions", {}).get(dim_key, {})
                score = dim_data.get("score", 50)
                if isinstance(score, (int, float)) and 0 <= score <= 100:
                    total_score += score
                    valid_dims += 1
                
                dimensions[dim_key] = DimensionScore(
                    score=score if isinstance(score, (int, float)) else 50,
                    brief_feedback=dim_data.get("brief_feedback", "评估中"),
                    detailed_feedback=dim_data.get("detailed_feedback", "详细评估正在生成中")
                )
            
            overall_score = total_score / valid_dims if valid_dims > 0 else 50.0
            
            evaluation = FastEvaluationResult(
                overall_score=round(overall_score, 1),
                overall_brief=result_json.get("overall_brief", "整体表现良好"),
                dimensions=dimensions
            )
            
            print(f"[FastEvaluator] ✅ Evaluation completed! Overall: {evaluation.overall_score}/100")
            return evaluation
            
        except Exception as e:
            print(f"[FastEvaluator] ❌ Evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _build_system_prompt_v3(self, position: str, language: str = "zh") -> str:
        """构建系统提示（使用v3/content规则）"""
        # 构建维度说明（从v3规则中提取）
        dimension_descriptions = []
        for dim_key, dim_name in self.dimensions.items():
            rule = self.v3_rules.get(dim_key, {})
            definition = rule.get("definition", f"{dim_name}的评估标准")
            priority_vocab = rule.get("priority_vocab", "")
            avoid_vocab = rule.get("avoid_vocab", "")
            
            desc = f"**{dim_name} ({dim_key})**：{definition}"
            if priority_vocab:
                desc += f"\n  - 优先词汇：{priority_vocab}"
            if avoid_vocab:
                desc += f"\n  - 避免词汇：{avoid_vocab}"
            dimension_descriptions.append(desc)
        
        dimensions_text = "\n".join([f"{i+1}. {desc}" for i, desc in enumerate(dimension_descriptions)])
        
        return f"""你是一名资深的面试评估专家，擅长快速准确地评估候选人的面试表现。

**评估维度说明**（基于v3/content评估体系）：
{dimensions_text}

**评分标准**（0-100分）：
- 90-100分：优秀，表现突出
- 75-89分：良好，符合期望
- 60-74分：一般，基本达标
- 40-59分：欠佳，需要改进
- 0-39分：较差，明显不足

**反馈生成规则**：

### 一句话点评（brief_feedback）
1. **控制在20-30字以内**
2. **使用第二人称语气（对候选人直接说"你/您"）**
3. **当候选人发言长度尚可时（≥40个汉字或≥2句完整表达），必须引用并评价其具体表述**
   - 在brief_feedback中至少引用1处候选人原话（用引号""或『』），并紧贴引用点指出问题/亮点
4. **禁止使用抽象词汇**
5. **根据得分调整语气**：
   - 如果得分 > 75分：使用褒义语气，重点指出优秀之处

### 详细反馈（detailed_feedback）
必须严格按照以下结构：
```
🔸 详细评价：
（基于评估维度详细分析现状和问题）

💡 改进建议：
（提供具体的改进方法和行动建议）
```

**重要规则**：
- 使用第二人称语气（你/您）
- 当候选人发言长度尚可时，详细评价必须包含引用与逐点点评
- 至少引用1-2处候选人原话，并对每个引用点分别给出"为什么这样说不够好/哪里做得好 + 如何改写/如何补充"的建议

**你的任务**：
快速分析面试对话，为每个维度给出评分（0-100分）、一句话点评（20-30字）和详细反馈。
评语要**具体、简洁、有建设性**，避免空话套话。

**职位**：{position}"""
    
    def _build_user_prompt_v3(self, conversation: str, language: str = "zh") -> str:
        """构建用户提示（v3格式）"""
        return f"""请评估以下面试对话中候选人的表现：

{conversation}

---

请以JSON格式返回评估结果（严格遵循以下结构）：

{{
  "overall_brief": "候选人表现良好，回答较为完整，但逻辑条理可以更清晰。",
  "dimensions": {{
    "clarity": {{
      "score": 75,
      "brief_feedback": "你的回答逻辑清晰，但结论可以更明确。",
      "detailed_feedback": "🔸 详细评价：\n你的回答在逻辑结构上基本清晰，能够按照一定的顺序组织内容。然而，在结论部分，你提到"我觉得还可以"，这样的表述不够明确，面试官可能无法准确理解你的最终观点。\n\n💡 改进建议：\n建议在回答结尾时，用一句话明确总结你的核心观点，例如"综上所述，我认为..."或"我的结论是..."，这样可以让面试官更清楚地理解你的立场。"
    }},
    "evidence": {{
      "score": 80,
      "brief_feedback": "你提供了具体案例，如"在XX项目中负责XX功能"，增强了说服力。",
      "detailed_feedback": "🔸 详细评价：\n你在回答中提到了具体的项目经历，例如"在XX项目中负责XX功能"，这为你的回答提供了有力的支撑。这些具体案例能够帮助面试官更好地理解你的能力和经验。\n\n💡 改进建议：\n可以进一步补充这些案例的结果和影响，例如"通过这个功能，我们提升了XX%的用户满意度"，这样可以让你的回答更有说服力。"
    }},
    "impact": {{
      "score": 70,
      "brief_feedback": "你的回答内容较为完整，但可以更突出专业性和影响力。",
      "detailed_feedback": "🔸 详细评价：\n你的回答涵盖了主要要点，但在展现专业性和影响力方面还有提升空间。面试官可能希望看到你如何通过具体行动产生实际影响。\n\n💡 改进建议：\n建议在回答中突出你的专业判断和决策带来的实际效果，例如"基于我的分析，我们采用了XX方案，最终实现了XX目标"，这样可以更好地展现你的专业能力和影响力。"
    }},
    "engagement": {{
      "score": 65,
      "brief_feedback": "你能够回应面试官的问题，但可以更主动地引导对话。",
      "detailed_feedback": "🔸 详细评价：\n你能够及时回应面试官的问题，展现出基本的沟通意愿。然而，你的回答主要是单向陈述，缺乏主动引导对话的尝试。\n\n💡 改进建议：\n可以在回答中适当加入反问或延伸话题，例如"关于这个问题，我还想了解贵公司在这方面的具体做法"，这样可以让对话更加互动，展现出你的主动性和思考深度。"
    }}
  }}
}}

**重要提示**：
1. 所有brief_feedback控制在20-30字
2. detailed_feedback必须包含"🔸 详细评价："和"💡 改进建议："两部分
3. 当候选人发言长度≥40个汉字时，brief_feedback和detailed_feedback中必须引用候选人原话
4. 评语要具体、有针对性，避免"表现良好"之类的空话
5. 必须严格遵循JSON格式，不要添加其他内容
6. 所有分数使用0-100分制"""


# 创建全局单例
_fast_evaluator: Optional[FastInterviewEvaluator] = None


def get_fast_evaluator() -> FastInterviewEvaluator:
    """获取快速评估器单例"""
    global _fast_evaluator
    if _fast_evaluator is None:
        _fast_evaluator = FastInterviewEvaluator()
    return _fast_evaluator

