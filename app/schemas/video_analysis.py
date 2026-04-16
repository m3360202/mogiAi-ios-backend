"""
视频分析相关的Pydantic schemas
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ========== 非语言特征 ==========

class VoiceFeatures(BaseModel):
    """音频特征"""
    volume_db_norm: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="音量（归一化0-1）/ 音量（正規化0-1）"
    )
    prosody_var: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="抑扬变化度（0-1）/ 抑揚変化度（0-1）"
    )
    speech_rate_norm: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="语速归一化（0.5为最佳）/ 話速正規化（0.5が最適）"
    )


class VisualFeatures(BaseModel):
    """视觉特征"""
    smile_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="微笑占比（0-1）/ 微笑比率（0-1）"
    )
    eye_contact_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="目光接触占比（0-1）/ 視線接触比率（0-1）"
    )
    posture_stability: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="姿态稳定度（0-1）/ 姿勢安定度（0-1）"
    )


class NonverbalFeatures(BaseModel):
    """非语言特征（音频+视觉）"""
    voice: Optional[VoiceFeatures] = Field(
        default=None,
        description="音频特征 / 音声特徴"
    )
    visual: Optional[VisualFeatures] = Field(
        default=None,
        description="视觉特征 / 視覚特徴"
    )


# ========== 分析请求 ==========

class VideoAnalysisRequest(BaseModel):
    """视频分析请求"""
    transcript: str = Field(
        ...,
        min_length=1,
        description="视频转录文本（用户发言）/ 動画の文字起こし（ユーザー発言）"
    )
    question: Optional[str] = Field(
        default=None,
        description="面试问题或对话主题 / 面接質問または会話テーマ"
    )
    nonverbal: Optional[NonverbalFeatures] = Field(
        default=None,
        description="非语言特征 / 非言語特徴"
    )
    scenario: Optional[str] = Field(
        default=None,
        description="场景类型（self_intro/sales/general等）/ シナリオタイプ"
    )
    language: str = Field(
        default="ja",
        pattern="^(ja|zh)$",
        description="语言（ja或zh）/ 言語（jaまたはzh）"
    )
    use_llm: bool = Field(
        default=True,
        description="是否使用LLM增强评估 / LLM強化評価を使用するか"
    )
    use_anthropic: bool = Field(
        default=False,
        description="是否使用Anthropic模型 / Anthropicモデルを使用するか"
    )
    llm_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="LLM权重（0-1） / LLM重み（0-1）"
    )
    compare_with_previous: bool = Field(
        default=False,
        description="是否与历史结果对比 / 過去の結果と比較するか"
    )
    previous_result_id: Optional[str] = Field(
        default=None,
        description="历史结果ID（用于对比）/ 過去の結果ID（比較用）"
    )


# ========== 维度详情 ==========

class DimensionDetail(BaseModel):
    """单个维度的详细信息"""
    reason: str = Field(description="评分理由 / 評価理由")
    advice: str = Field(description="改进建议 / 改善提案")
    snippet: str = Field(description="代表句片段 / 代表文の断片")
    target: str = Field(description="目标句位置 / 対象文の位置")
    target_text: str = Field(description="目标句文本 / 対象文のテキスト")
    sample_fix: str = Field(description="改进示例 / 改善例")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="额外详情（如非语言子指标）/ 追加詳細"
    )
    blend_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="融合信息（LLM+规则）/ ブレンド情報"
    )


class DimensionRow(BaseModel):
    """维度表格行"""
    key: str = Field(description="维度键名 / 次元キー")
    label: str = Field(description="维度标签 / 次元ラベル")
    score: str = Field(description="得分（如'4/5'）/ スコア（例：'4/5'）")
    target: str = Field(description="目标句位置 / 対象文の位置")
    target_text: str = Field(description="目标句文本 / 対象文のテキスト")
    snippet: str = Field(description="代表句片段 / 代表文の断片")
    reason: str = Field(description="评分理由 / 評価理由")
    advice: str = Field(description="改进建议 / 改善提案")
    sample_fix: str = Field(description="改进示例 / 改善例")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="额外详情 / 追加詳細"
    )


# ========== 对比结果 ==========

class DimensionChange(BaseModel):
    """维度变化"""
    current: int = Field(description="当前分数 / 現在のスコア")
    previous: int = Field(description="历史分数 / 過去のスコア")
    change: int = Field(description="变化量 / 変化量")
    change_pct: float = Field(description="变化百分比 / 変化率")


class ComparisonResult(BaseModel):
    """对比结果"""
    improvements: List[Dict[str, Any]] = Field(
        default=[],
        description="进步的维度 / 向上した次元"
    )
    regressions: List[Dict[str, Any]] = Field(
        default=[],
        description="退步的维度 / 向下した次元"
    )
    stable: List[str] = Field(
        default=[],
        description="稳定的维度 / 安定した次元"
    )
    changes: Dict[str, DimensionChange] = Field(
        default={},
        description="各维度的变化详情 / 各次元の変化詳細"
    )
    summary: str = Field(description="对比摘要 / 比較サマリー")


# ========== 分析响应 ==========

class VideoAnalysisResponse(BaseModel):
    """视频分析响应"""
    labels: Dict[str, str] = Field(
        description="维度标签映射 / 次元ラベルマップ"
    )
    scores: Dict[str, Optional[int]] = Field(
        description="各维度得分（1-5或None）/ 各次元のスコア（1-5またはNone）"
    )
    details: Dict[str, DimensionDetail] = Field(
        description="各维度详细信息 / 各次元の詳細情報"
    )
    table_rows: List[DimensionRow] = Field(
        description="表格数据 / テーブルデータ"
    )
    improved_text: str = Field(
        description="改进后的文本示例 / 改善されたテキスト例"
    )
    summary: str = Field(
        description="总结 / サマリー"
    )
    llm_overall_feedback: Optional[str] = Field(
        default=None,
        description="LLM总体反馈 / LLM総合フィードバック"
    )
    comparison: Optional[ComparisonResult] = Field(
        default=None,
        description="与历史结果的对比 / 過去結果との比較"
    )
    meta: Dict[str, Any] = Field(
        alias="__meta",
        description="元信息 / メタ情報"
    )
    
    class Config:
        populate_by_name = True


# ========== 改进路线图请求 ==========

class ImprovementRoadmapRequest(BaseModel):
    """改进路线图请求"""
    analysis_result: VideoAnalysisResponse = Field(
        ...,
        description="分析结果 / 分析結果"
    )
    user_goal: Optional[str] = Field(
        default=None,
        description="用户目标 / ユーザーの目標"
    )
    language: str = Field(
        default="ja",
        pattern="^(ja|zh)$",
        description="语言 / 言語"
    )


class ImprovementRoadmapResponse(BaseModel):
    """改进路线图响应"""
    roadmap: str = Field(
        description="改进路线图文本 / 改善ロードマップテキスト"
    )
    weak_dimensions: List[Dict[str, Any]] = Field(
        default=[],
        description="需要改进的维度列表 / 改善が必要な次元リスト"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="生成时间 / 生成時刻"
    )


# ========== 批量分析 ==========

class BatchAnalysisRequest(BaseModel):
    """批量视频分析请求"""
    transcripts: List[str] = Field(
        ...,
        min_length=1,
        description="多个转录文本 / 複数の文字起こし"
    )
    common_settings: Optional[VideoAnalysisRequest] = Field(
        default=None,
        description="通用设置（应用于所有转录）/ 共通設定"
    )


class BatchAnalysisResponse(BaseModel):
    """批量分析响应"""
    results: List[VideoAnalysisResponse] = Field(
        description="分析结果列表 / 分析結果リスト"
    )
    average_scores: Dict[str, float] = Field(
        description="平均得分 / 平均スコア"
    )
    total_count: int = Field(
        description="总数量 / 総数"
    )
    processed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="处理时间 / 処理時刻"
    )

