"""LangChain AI Analysis Service for interview analytics."""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import settings

try:  # pragma: no cover - heavy optional dependency
    from langchain_openai import ChatOpenAI
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
    from langchain_core.output_parsers import JsonOutputParser
    _LANGCHAIN_AVAILABLE = True
    LANGCHAIN_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover
    ChatOpenAI = ChatAnthropic = HumanMessage = SystemMessage = ChatPromptTemplate = PromptTemplate = JsonOutputParser = None  # type: ignore
    _LANGCHAIN_AVAILABLE = False
    LANGCHAIN_IMPORT_ERROR = exc


# ========== Pydantic Models for Structured Output ==========

class DimensionScore(BaseModel):
    """单个维度的评分"""
    score: int = Field(description="该维度的分数，范围0-100")
    performance: str = Field(description="该维度的表现描述")
    issues: str = Field(description="发现的问题")
    suggestions: str = Field(description="改进建议")


class SixDimensionAnalysis(BaseModel):
    """六维面试分析结果"""
    content: DimensionScore = Field(description="内容维度评分")
    expression: DimensionScore = Field(description="表现力维度评分")
    logic: DimensionScore = Field(description="逻辑性维度评分")
    attitude: DimensionScore = Field(description="态度维度评分")
    professionalism: DimensionScore = Field(description="专业性维度评分")
    fluency: DimensionScore = Field(description="流畅度维度评分")
    overall_score: int = Field(description="总体评分，范围0-100")
    overall_feedback: str = Field(description="总体反馈")
    key_strengths: List[str] = Field(description="主要优势列表")
    areas_for_improvement: List[str] = Field(description="待改进领域列表")


class TranscriptAnalysis(BaseModel):
    """转录文本的基础分析"""
    word_count: int = Field(description="总字数")
    filler_words_count: int = Field(description="填充词数量（えー、あのー等）")
    average_sentence_length: float = Field(description="平均句子长度")
    complexity_score: int = Field(description="复杂度评分，0-100")
    clarity_score: int = Field(description="清晰度评分，0-100")


# ========== LangChain Service ==========

class LangChainAnalysisService:
    """LangChain AI分析服务"""
    
    def __init__(self):
        if not _LANGCHAIN_AVAILABLE or ChatOpenAI is None or JsonOutputParser is None:
            raise RuntimeError(
                "LangChain dependencies are not installed or failed to load. "
                "Install langchain-openai, langchain-core, langsmith, etc."
            ) from LANGCHAIN_IMPORT_ERROR

        # 初始化模型
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
        
        # 默认使用的模型
        self.default_model = self.openai_model
        
        # 输出解析器
        self.json_parser = JsonOutputParser()
    
    async def analyze_interview_six_dimensions(
        self,
        transcript: str,
        question: str,
        audio_features: Optional[Dict[str, Any]] = None,
        use_anthropic: bool = False
    ) -> SixDimensionAnalysis:
        """
        分析面试的六维表现
        
        Args:
            transcript: 面试转录文本（日语）
            question: 面试问题
            audio_features: 音频特征（可选），包括音量、语速等
            use_anthropic: 是否使用Anthropic模型
            
        Returns:
            SixDimensionAnalysis: 六维分析结果
        """
        # 选择模型
        model = self.anthropic_model if use_anthropic and self.anthropic_model else self.default_model
        
        # 构建系统提示
        system_prompt = """あなたは日本語面接の専門評価者です。
応募者の面接回答を以下の6つの次元で評価してください：

1. **内容（Content）**: 回答の充実度、具体性、質問への適切さ
2. **表現力（Expression）**: 声のトーン、抑揚、感情表現の豊かさ
   - ⚠️ **重要**: 以下の音声品質の問題を必ず検出してください：
     - **咳**: 咳き込みや咳の音が含まれている場合
     - **発音不明瞭**: もごもご話している、言葉がはっきり聞き取れない場合
     - **のどを鳴らす**: 頻繁に「えへん」などののどを鳴らす音
     - **吃音・ためらい**: 過度な「えー」「あー」「うーん」などのフィラー、言葉の繰り返し
     - **声の途切れ**: 突然の声の途切れや声がかすれる
     - **音量の不規則**: 突然の音量低下や上昇で明瞭さに影響がある
   - これらの問題が検出された場合、`issues`フィールドに具体的に記載し、`score`を低く評価してください。
3. **論理性（Logic）**: 話の構造、因果関係の明確さ、論理的な展開
4. **態度（Attitude）**: 誠実さ、前向きさ、プロフェッショナルな姿勢
5. **専門性（Professionalism）**: 専門知識の深さ、業界理解
6. **流暢度（Fluency）**: 話すスピード、フィラーの少なさ、スムーズさ

各次元を0-100点で評価し、詳細なフィードバックを提供してください。"""
        
        # 構建用户提示
        user_content = f"""
【面接質問】
{question}

【応募者の回答】
{transcript}
"""
        
        # 添加音频特征信息
        if audio_features:
            user_content += f"\n【音声特徴】\n"
            if 'speaking_rate' in audio_features:
                user_content += f"話す速度: {audio_features['speaking_rate']} 文字/分\n"
            if 'average_volume' in audio_features:
                user_content += f"平均音量: {audio_features['average_volume']}\n"
            if 'pitch_variation' in audio_features:
                user_content += f"音程変化: {audio_features['pitch_variation']}\n"
        
        # 创建提示模板 - 明确要求使用英文字段名
        # 注意：使用双大括号 {{ }} 来转义 JSON 示例，避免被 LangChain 识别为模板变量
        json_format_instruction = """
JSON形式で評価結果を返してください。以下の構造で、**必ず英文字段名を使用**してください：

{{
  "content": {{
    "score": 0-100,
    "performance": "表現の説明",
    "issues": "問題点",
    "suggestions": "改善提案"
  }},
  "expression": {{ ... }},
  "logic": {{ ... }},
  "attitude": {{ ... }},
  "professionalism": {{ ... }},
  "fluency": {{ ... }},
  "overall_score": 0-100,
  "overall_feedback": "総合フィードバック",
  "key_strengths": ["強み1", "強み2"],
  "areas_for_improvement": ["改善点1", "改善点2"]
}}

**重要**: フィールド名は必ず英語（content, expression, logic, attitude, professionalism, fluency）を使用してください。日本語のフィールド名は使用しないでください。
"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", user_content + json_format_instruction)
        ])
        
        # 构建chain
        chain = prompt | model | JsonOutputParser(pydantic_object=SixDimensionAnalysis)
        
        # 执行分析
        try:
            result = await chain.ainvoke({})
            
            # 如果LLM返回了中文键名，尝试映射到英文字段名
            if isinstance(result, dict):
                # 检查是否有中文键名，如果有则映射
                field_mapping = {
                    "内容（Content）": "content",
                    "表現力（Expression）": "expression",
                    "論理性（Logic）": "logic",
                    "態度（Attitude）": "attitude",
                    "専門性（Professionalism）": "professionalism",
                    "流暢度（Fluency）": "fluency",
                    "内容": "content",
                    "表現力": "expression",
                    "論理性": "logic",
                    "態度": "attitude",
                    "専門性": "professionalism",
                    "流暢度": "fluency",
                }
                
                # 检查是否需要映射
                needs_mapping = any(key in field_mapping for key in result.keys())
                if needs_mapping:
                    mapped_result = {}
                    for key, value in result.items():
                        if key in field_mapping:
                            mapped_result[field_mapping[key]] = value
                        else:
                            mapped_result[key] = value
                    result = mapped_result
            
            return SixDimensionAnalysis(**result)
        except Exception as e:
            # 如果解析失败，返回默认值
            print(f"[LangChainService] Analysis error: {type(e).__name__}: {str(e)[:200]}")
            import traceback
            traceback.print_exc()
            return self._get_default_analysis()
    
    async def analyze_transcript_basic(
        self,
        transcript: str
    ) -> TranscriptAnalysis:
        """
        基础转录文本分析
        
        Args:
            transcript: 转录文本（日语）
            
        Returns:
            TranscriptAnalysis: 基础分析结果
        """
        # 简单的文本统计
        word_count = len(transcript)
        
        # 统计填充词
        filler_words = ['えー', 'あのー', 'その', 'まあ', 'なんか']
        filler_count = sum(transcript.count(filler) for filler in filler_words)
        
        # 计算句子数（简单按句号分割）
        sentences = [s.strip() for s in transcript.split('。') if s.strip()]
        avg_sentence_length = word_count / len(sentences) if sentences else 0
        
        # 使用LLM分析复杂度和清晰度
        prompt = f"""
以下の日本語の文章を分析し、以下の2つの指標を0-100点で評価してください：

1. complexity_score: 文章の複雑さ（語彙の難易度、文構造の複雑さ）
2. clarity_score: 文章の明確さ（分かりやすさ、論理的な流れ）

【文章】
{transcript}

JSON形式で返してください: {{"complexity_score": <数値>, "clarity_score": <数値>}}
"""
        
        try:
            response = await self.default_model.ainvoke([HumanMessage(content=prompt)])
            scores = self.json_parser.parse(response.content)
            
            return TranscriptAnalysis(
                word_count=word_count,
                filler_words_count=filler_count,
                average_sentence_length=avg_sentence_length,
                complexity_score=scores.get('complexity_score', 50),
                clarity_score=scores.get('clarity_score', 50)
            )
        except Exception as e:
            print(f"Basic analysis error: {e}")
            return TranscriptAnalysis(
                word_count=word_count,
                filler_words_count=filler_count,
                average_sentence_length=avg_sentence_length,
                complexity_score=50,
                clarity_score=50
            )
    
    async def generate_improvement_plan(
        self,
        analysis: SixDimensionAnalysis,
        user_goal: Optional[str] = None
    ) -> str:
        """
        根据六维分析结果生成个性化改进计划
        
        Args:
            analysis: 六维分析结果
            user_goal: 用户目标（可选）
            
        Returns:
            str: 改进计划文本
        """
        prompt = f"""
面接評価結果に基づいて、具体的な改善計画を作成してください。

【評価結果】
- 内容: {analysis.content.score}点
- 表現力: {analysis.expression.score}点
- 論理性: {analysis.logic.score}点
- 態度: {analysis.attitude.score}点
- 専門性: {analysis.professionalism.score}点
- 流暢度: {analysis.fluency.score}点

【主な弱点】
{', '.join(analysis.areas_for_improvement)}

"""
        if user_goal:
            prompt += f"【ユーザーの目標】\n{user_goal}\n\n"
        
        prompt += """
以下の内容を含む改善計画を作成してください：
1. 優先的に改善すべき次元（上位3つ）
2. 各次元の具体的な練習方法
3. 2週間の実践スケジュール
4. 推奨リソース（書籍、動画など）
"""
        
        try:
            response = await self.default_model.ainvoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            print(f"Improvement plan generation error: {e}")
            return "改善計画の生成に失敗しました。"
    
    async def compare_with_previous(
        self,
        current_analysis: SixDimensionAnalysis,
        previous_analysis: SixDimensionAnalysis
    ) -> Dict[str, Any]:
        """
        与上次面试结果对比
        
        Args:
            current_analysis: 当前分析结果
            previous_analysis: 上次分析结果
            
        Returns:
            dict: 对比结果
        """
        comparison = {
            "improvements": [],
            "regressions": [],
            "stable_areas": [],
            "score_changes": {}
        }
        
        dimensions = ['content', 'expression', 'logic', 'attitude', 'professionalism', 'fluency']
        
        for dim in dimensions:
            current_score = getattr(current_analysis, dim).score
            previous_score = getattr(previous_analysis, dim).score
            change = current_score - previous_score
            
            comparison["score_changes"][dim] = {
                "current": current_score,
                "previous": previous_score,
                "change": change,
                "change_percentage": (change / previous_score * 100) if previous_score > 0 else 0
            }
            
            if change > 5:
                comparison["improvements"].append(dim)
            elif change < -5:
                comparison["regressions"].append(dim)
            else:
                comparison["stable_areas"].append(dim)
        
        return comparison
    
    def _get_default_analysis(self) -> SixDimensionAnalysis:
        """返回默认的分析结果（用于错误处理）"""
        default_dimension = DimensionScore(
            score=50,
            performance="分析中にエラーが発生しました",
            issues="評価できませんでした",
            suggestions="もう一度お試しください"
        )
        
        return SixDimensionAnalysis(
            content=default_dimension,
            expression=default_dimension,
            logic=default_dimension,
            attitude=default_dimension,
            professionalism=default_dimension,
            fluency=default_dimension,
            overall_score=50,
            overall_feedback="分析中にエラーが発生しました。もう一度お試しください。",
            key_strengths=[],
            areas_for_improvement=[]
        )


# 创建单例实例
if _LANGCHAIN_AVAILABLE:
    try:
        langchain_service = LangChainAnalysisService()
    except Exception as exc:  # pragma: no cover - configuration issues
        langchain_service = None
        LANGCHAIN_IMPORT_ERROR = exc
else:  # pragma: no cover
    langchain_service = None

