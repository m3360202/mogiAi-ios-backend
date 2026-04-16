"""视频内容分析服务 - 集成LangChain和规则评估，提供七维分析。"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.video_evaluator import video_evaluator

try:  # pragma: no cover - optional dependency
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    _LANGCHAIN_AVAILABLE = True
    _LANGCHAIN_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover
    ChatOpenAI = ChatAnthropic = HumanMessage = SystemMessage = ChatPromptTemplate = JsonOutputParser = None  # type: ignore
    _LANGCHAIN_AVAILABLE = False
    _LANGCHAIN_IMPORT_ERROR = exc


# ========== Pydantic Models for LangChain Structured Output ==========

class DimensionAnalysis(BaseModel):
    """单个维度的LLM分析"""
    score: int = Field(description="该维度的分数，范围1-5")
    rationale: str = Field(description="评分理由")
    tips: str = Field(description="改进建议")
    example: Optional[str] = Field(default=None, description="改进示例")


class SevenDimensionLLMAnalysis(BaseModel):
    """七维LLM分析结果"""
    clarity: DimensionAnalysis = Field(description="清晰度/理解しやすさ")
    evidence: DimensionAnalysis = Field(description="证据/根拠・具体性")
    delivery: DimensionAnalysis = Field(description="表达力/表現力・伝達力")
    engagement: DimensionAnalysis = Field(description="互动性/やりとり・双方向性")
    politeness: DimensionAnalysis = Field(description="礼貌/礼儀・態度")
    impact: DimensionAnalysis = Field(description="影响力/印象・影響力")
    overall_feedback: str = Field(description="总体反馈")


# ========== 视频分析服务 ==========

class VideoAnalysisService:
    """视频内容分析服务 - 混合模式（LLM + 规则）"""
    
    def __init__(self):
        if not _LANGCHAIN_AVAILABLE or ChatOpenAI is None or JsonOutputParser is None:
            raise RuntimeError(
                "LangChain dependencies are not installed for video analysis service."
            ) from _LANGCHAIN_IMPORT_ERROR
        # 初始化OpenAI模型
        self.openai_model = ChatOpenAI(
            model=getattr(settings, 'OPENAI_MODEL', 'gpt-4o'),
            temperature=0.3,
            api_key=getattr(settings, 'OPENAI_API_KEY', '')
        )
        
        # 可选的Anthropic模型
        anthropic_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
        if anthropic_key:
            self.anthropic_model = ChatAnthropic(
                model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022'),
                temperature=0.3,
                api_key=anthropic_key
            )
        else:
            self.anthropic_model = None
        
        # 默认模型
        self.default_model = self.openai_model
        
        # 规则评估器
        self.rule_evaluator = video_evaluator
        
        # 输出解析器
        self.json_parser = JsonOutputParser()
    
    async def analyze_video_content(
        self,
        transcript: str,
        question: Optional[str] = None,
        nonverbal: Optional[Dict[str, Any]] = None,
        scenario: Optional[str] = None,
        language: str = "ja",
        use_llm: bool = True,
        use_anthropic: bool = False,
        llm_weight: float = 0.7
    ) -> Dict[str, Any]:
        """
        综合分析视频内容，提供七维评价
        
        Args:
            transcript: 视频转录文本（用户发言）
            question: 面试问题或对话主题（可选）
            nonverbal: 非语言特征字典
                - voice: {"volume_db_norm": 0-1, "prosody_var": 0-1, "speech_rate_norm": 0-1}
                - visual: {"smile_rate": 0-1, "eye_contact_rate": 0-1, "posture_stability": 0-1}
            scenario: 场景类型（self_intro/sales/general等）
            language: 语言（ja/zh）
            use_llm: 是否使用LLM增强评估
            use_anthropic: 是否使用Anthropic模型
            llm_weight: LLM权重（默认0.7，规则权重为1-llm_weight）
            
        Returns:
            综合评估结果字典
        """
        # 1. 执行规则评估（基础评分）
        rule_result = self.rule_evaluator.evaluate(
            human_text=transcript,
            ai_text=question or "",
            nonverbal=nonverbal,
            scenario=scenario,
            language=language
        )
        
        # 2. 如果启用LLM，执行LLM评估并融合
        if use_llm:
            try:
                llm_result = await self._llm_analyze(
                    transcript=transcript,
                    question=question,
                    language=language,
                    use_anthropic=use_anthropic
                )
                
                # 融合LLM和规则评分
                blended_result = self._blend_results(
                    rule_result=rule_result,
                    llm_result=llm_result,
                    llm_weight=llm_weight,
                    language=language
                )
                
                blended_result["__meta"]["llm_used"] = True
                blended_result["__meta"]["blend_ratio"] = {
                    "llm": llm_weight,
                    "rule": 1 - llm_weight
                }
                blended_result["__meta"]["llm_model"] = (
                    self.anthropic_model.model if use_anthropic and self.anthropic_model 
                    else self.openai_model.model
                )
                
                return blended_result
                
            except Exception as e:
                print(f"LLM分析失败，回退到规则评估: {e}")
                rule_result["__meta"]["llm_used"] = False
                rule_result["__meta"]["llm_error"] = str(e)
                return rule_result
        
        else:
            # 仅使用规则评估
            rule_result["__meta"]["llm_used"] = False
            return rule_result
    
    async def _llm_analyze(
        self,
        transcript: str,
        question: Optional[str],
        language: str,
        use_anthropic: bool
    ) -> SevenDimensionLLMAnalysis:
        """
        使用LLM进行语义分析
        
        Args:
            transcript: 转录文本
            question: 问题（可选）
            language: 语言
            use_anthropic: 是否使用Anthropic
            
        Returns:
            LLM分析结果
        """
        # 选择模型
        model = self.anthropic_model if use_anthropic and self.anthropic_model else self.default_model
        
        # 构建系统提示（中日双语）
        if language == "zh":
            system_prompt = """你是一位专业的面试评估专家。
请根据以下6个维度评价应试者的表现（每个维度1-5分）：

1. **清晰度（Clarity）**: 句子长度适中、逻辑结构清晰、避免模糊表达
2. **证据（Evidence）**: 使用数字、具体案例、专有名词支撑观点
3. **表达力（Delivery）**: 语气坚定、减少犹豫词和口头禅
4. **互动性（Engagement）**: 主动提问、确认对方意图、双向交流
5. **礼貌（Politeness）**: 使用得体的问候和敬语
6. **影响力（Impact）**: 突出价值和结果、给人留下深刻印象

对每个维度提供：
- score: 1-5分评分
- rationale: 评分理由
- tips: 改进建议
- example: 改进示例（可选）
"""
        else:
            system_prompt = """あなたは面接評価の専門家です。
応募者の発言を以下の6つの次元で評価してください（各次元1-5点）：

1. **理解のしやすさ（Clarity）**: 文長の適正、論理構造の明確さ、曖昧語の少なさ
2. **根拠・具体性（Evidence）**: 数値、具体例、固有名詞の使用
3. **表現力・伝達力（Delivery）**: 断定的な語気、ためらい語・フィラーの少なさ
4. **やりとり・双方向性（Engagement）**: 質問、相手の意図確認、双方向コミュニケーション
5. **礼儀・態度（Politeness）**: 適切な挨拶と敬語の使用
6. **印象・影響力（Impact）**: 価値と結果の強調、記憶に残る表現

各次元について以下を提供してください：
- score: 1-5点の評価
- rationale: 評価理由
- tips: 改善提案
- example: 改善例（任意）
"""
        
        # 构建用户内容
        if question:
            user_content = f"""【質問/Question】
{question}

【回答/Response】
{transcript}
"""
        else:
            user_content = f"""【発言内容/Content】
{transcript}
"""
        
        # 添加JSON格式要求
        json_instruction = "\n\nJSON形式で評価結果を返してください。" if language == "ja" else "\n\n请以JSON格式返回评估结果。"
        
        # 创建提示
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", user_content + json_instruction)
        ])
        
        # 构建chain
        chain = prompt | model | JsonOutputParser(pydantic_object=SevenDimensionLLMAnalysis)
        
        # 执行分析
        result = await chain.ainvoke({})
        return SevenDimensionLLMAnalysis(**result)
    
    def _blend_results(
        self,
        rule_result: Dict[str, Any],
        llm_result: SevenDimensionLLMAnalysis,
        llm_weight: float,
        language: str
    ) -> Dict[str, Any]:
        """
        融合规则评估和LLM评估结果
        
        Args:
            rule_result: 规则评估结果
            llm_result: LLM评估结果
            llm_weight: LLM权重（0-1）
            language: 语言
            
        Returns:
            融合后的结果
        """
        rule_weight = 1 - llm_weight
        
        # 融合分数（6个语言维度）
        dimensions = ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]
        blended_scores = {}
        
        for dim in dimensions:
            rule_score = rule_result["scores"][dim]
            llm_score = getattr(llm_result, dim).score
            blended_score = int(round(rule_score * rule_weight + llm_score * llm_weight))
            blended_score = max(1, min(5, blended_score))  # 确保在1-5范围内
            blended_scores[dim] = blended_score
        
        # 非语言维度保持规则评分
        blended_scores["nonverbal"] = rule_result["scores"].get("nonverbal")
        
        # 重新计算总分
        total_score = sum(blended_scores[dim] for dim in dimensions)
        blended_scores["total"] = total_score
        blended_scores["max"] = len(dimensions) * 5
        
        # 更新details - 合并LLM的反馈
        blended_details = rule_result["details"].copy()
        
        for dim in dimensions:
            llm_dim_result = getattr(llm_result, dim)
            
            # 如果LLM提供了更详细的反馈，则使用LLM的
            if llm_dim_result.rationale:
                blended_details[dim]["reason"] = (
                    f"【LLM】{llm_dim_result.rationale}\n"
                    f"【規則】{blended_details[dim]['reason']}"
                    if language == "ja" else
                    f"【LLM】{llm_dim_result.rationale}\n"
                    f"【规则】{blended_details[dim]['reason']}"
                )
            
            if llm_dim_result.tips:
                blended_details[dim]["advice"] = llm_dim_result.tips
            
            if llm_dim_result.example:
                blended_details[dim]["sample_fix"] = llm_dim_result.example
            
            # 添加融合信息
            blended_details[dim]["blend_info"] = {
                "rule_score": rule_result["scores"][dim],
                "llm_score": llm_dim_result.score,
                "blended_score": blended_scores[dim],
                "weights": {"rule": rule_weight, "llm": llm_weight}
            }
        
        # 更新table_rows
        blended_table_rows = []
        for row in rule_result["table_rows"]:
            key = row["key"]
            if key in dimensions:
                row["score"] = f"{blended_scores[key]}/5"
                if key in blended_details:
                    row["reason"] = blended_details[key]["reason"]
                    row["advice"] = blended_details[key]["advice"]
                    row["sample_fix"] = blended_details[key]["sample_fix"]
            blended_table_rows.append(row)
        
        # 构建最终结果
        blended_result = {
            "labels": rule_result["labels"],
            "scores": blended_scores,
            "details": blended_details,
            "table_rows": blended_table_rows,
            "improved_text": rule_result["improved_text"],
            "summary": (
                f"総合 {total_score}/{blended_scores['max']}（混合評価：LLM {llm_weight*100:.0f}% + 規則 {rule_weight*100:.0f}%）"
                if language == "ja" else
                f"总分 {total_score}/{blended_scores['max']}（混合评估：LLM {llm_weight*100:.0f}% + 规则 {rule_weight*100:.0f}%）"
            ),
            "llm_overall_feedback": llm_result.overall_feedback,
            "__meta": rule_result["__meta"].copy(),
        }
        
        blended_result["__meta"]["blend_mode"] = "hybrid"
        
        return blended_result
    
    async def analyze_video_with_comparison(
        self,
        current_transcript: str,
        previous_result: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        分析视频并与历史结果对比
        
        Args:
            current_transcript: 当前转录文本
            previous_result: 上次分析结果（可选）
            **kwargs: 传递给analyze_video_content的其他参数
            
        Returns:
            包含对比信息的分析结果
        """
        # 执行当前分析
        current_result = await self.analyze_video_content(
            transcript=current_transcript,
            **kwargs
        )
        
        # 如果有历史结果，添加对比信息
        if previous_result and "scores" in previous_result:
            comparison = self._compare_results(
                current_scores=current_result["scores"],
                previous_scores=previous_result["scores"],
                language=kwargs.get("language", "ja")
            )
            current_result["comparison"] = comparison
        
        return current_result
    
    def _compare_results(
        self,
        current_scores: Dict[str, int],
        previous_scores: Dict[str, int],
        language: str
    ) -> Dict[str, Any]:
        """
        对比当前和历史评分
        
        Args:
            current_scores: 当前评分
            previous_scores: 历史评分
            language: 语言
            
        Returns:
            对比结果
        """
        dimensions = ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]
        
        comparison = {
            "improvements": [],
            "regressions": [],
            "stable": [],
            "changes": {}
        }
        
        for dim in dimensions:
            current = current_scores.get(dim, 0)
            previous = previous_scores.get(dim, 0)
            change = current - previous
            
            comparison["changes"][dim] = {
                "current": current,
                "previous": previous,
                "change": change,
                "change_pct": round((change / previous * 100) if previous > 0 else 0, 1)
            }
            
            if change > 0:
                comparison["improvements"].append({
                    "dimension": dim,
                    "change": change
                })
            elif change < 0:
                comparison["regressions"].append({
                    "dimension": dim,
                    "change": change
                })
            else:
                comparison["stable"].append(dim)
        
        # 生成对比摘要
        if language == "zh":
            summary_parts = []
            if comparison["improvements"]:
                summary_parts.append(f"进步维度：{len(comparison['improvements'])}个")
            if comparison["regressions"]:
                summary_parts.append(f"退步维度：{len(comparison['regressions'])}个")
            if comparison["stable"]:
                summary_parts.append(f"稳定维度：{len(comparison['stable'])}个")
            comparison["summary"] = "、".join(summary_parts) if summary_parts else "无变化"
        else:
            summary_parts = []
            if comparison["improvements"]:
                summary_parts.append(f"向上: {len(comparison['improvements'])}次元")
            if comparison["regressions"]:
                summary_parts.append(f"向下: {len(comparison['regressions'])}次元")
            if comparison["stable"]:
                summary_parts.append(f"安定: {len(comparison['stable'])}次元")
            comparison["summary"] = "、".join(summary_parts) if summary_parts else "変化なし"
        
        return comparison
    
    async def generate_improvement_roadmap(
        self,
        analysis_result: Dict[str, Any],
        user_goal: Optional[str] = None,
        language: str = "ja"
    ) -> str:
        """
        基于分析结果生成个性化改进路线图
        
        Args:
            analysis_result: 分析结果
            user_goal: 用户目标（可选）
            language: 语言
            
        Returns:
            改进路线图文本
        """
        scores = analysis_result["scores"]
        
        # 找出最需要改进的3个维度
        dimensions = ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]
        dim_scores = [(dim, scores[dim]) for dim in dimensions if dim in scores]
        dim_scores.sort(key=lambda x: x[1])  # 按分数升序
        
        weak_dimensions = dim_scores[:3]
        
        # 构建提示
        if language == "zh":
            prompt = f"""
基于以下面试评估结果，制定一个2周的改进计划：

【当前评分】
"""
            for dim, score in dim_scores:
                label = analysis_result["labels"].get(dim, dim)
                prompt += f"- {label}: {score}/5\n"
            
            prompt += f"\n【最需改进的维度】\n"
            for dim, score in weak_dimensions:
                label = analysis_result["labels"].get(dim, dim)
                advice = analysis_result["details"][dim].get("advice", "")
                prompt += f"- {label} ({score}/5): {advice}\n"
            
            if user_goal:
                prompt += f"\n【用户目标】\n{user_goal}\n"
            
            prompt += """
请提供：
1. 优先改进的3个维度及原因
2. 每个维度的具体练习方法（包括日常练习和模拟场景）
3. 2周实践计划（每天30分钟）
4. 推荐的学习资源
5. 效果检验方法
"""
        else:
            prompt = f"""
以下の面接評価結果に基づき、2週間の改善計画を作成してください：

【現在のスコア】
"""
            for dim, score in dim_scores:
                label = analysis_result["labels"].get(dim, dim)
                prompt += f"- {label}: {score}/5\n"
            
            prompt += f"\n【最も改善が必要な次元】\n"
            for dim, score in weak_dimensions:
                label = analysis_result["labels"].get(dim, dim)
                advice = analysis_result["details"][dim].get("advice", "")
                prompt += f"- {label} ({score}/5): {advice}\n"
            
            if user_goal:
                prompt += f"\n【ユーザーの目標】\n{user_goal}\n"
            
            prompt += """
以下を提供してください：
1. 優先的に改善すべき3次元とその理由
2. 各次元の具体的な練習方法（日常練習とシミュレーション）
3. 2週間の実践計画（毎日30分）
4. 推奨学習リソース
5. 効果検証方法
"""
        
        try:
            response = await self.default_model.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            print(f"改进路线图生成失败: {e}")
            return "改善計画の生成に失敗しました。" if language == "ja" else "改进计划生成失败。"


# 创建单例实例
if _LANGCHAIN_AVAILABLE:
    try:
        video_analysis_service = VideoAnalysisService()
    except Exception as exc:  # pragma: no cover
        video_analysis_service = None
        _LANGCHAIN_IMPORT_ERROR = exc
else:  # pragma: no cover
    video_analysis_service = None

