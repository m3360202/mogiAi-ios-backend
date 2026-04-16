"""
Rule-based fallback feedback generation for super-metrics.

When LLM-based feedback generation fails, we synthesise actionable guidance
based on the super-metric score label and dialog context so that users still
receive meaningful coaching tips instead of generic placeholders.
"""
from __future__ import annotations

from typing import Dict, Tuple

from app.services.evaluation.business.entities import DialogSection
from app.services.evaluation.business.enums import ScoreLabel, SuperMetricType
from app.services.evaluation.business.value_objects import (
    SuperMetric,
    SuperMetricFeedback,
)


def _extract_candidate_answer(section: DialogSection) -> str:
    """Collect the candidate's utterances within a section."""
    fragments = [
        message.content.strip()
        for message in section.messages
        if message.role.value == "CANDIDATE" and message.content.strip()
    ]
    return " ".join(fragments)


def _score_tone(score_label: ScoreLabel) -> Tuple[str, str]:
    """Return tone descriptors for brief feedback and coaching focus (Yoodli-style warm, friendly tone)."""
    if score_label == ScoreLabel.GOOD:
        return "その調子です！", "あなたの強みを維持しつつ、もう1〜2個の強調点を掘り下げると、より印象に残る回答になりますよ。"
    if score_label == ScoreLabel.FAIR:
        return "さらなる伸びしろがありますね。", "詳細と構成を補うと、より完成度が高く説得力のある回答になりますよ。"
    return "重点的な改善が必要ですが、一つずつ取り組めば大丈夫です。", "要点を整理し直し、具体的な事例を補い、話すリズムを練習してみてくださいね。"


def _metric_specific_guidance(
    metric_type: SuperMetricType,
    score_label: ScoreLabel,
) -> Tuple[str, str, str]:
    """
    Provide (brief, detailed, revised_response) templates for each super-metric.
    """
    # Mapping helper for readability
    brief_tone, focus_hint = _score_tone(score_label)

    def join_lines(*lines: str) -> str:
        return " ".join(line for line in lines if line)

    if metric_type == SuperMetricType.CLARITY:
        detailed = join_lines(
            "「背景-課題-行動-結果（STAR）」の構成でストーリーを整理すると、相手に伝わりやすくなりますよ。",
            "要点を明確に示し、最初の30秒で核心メッセージが伝わるようにすると良いですね。",
            focus_hint,
        )
        revised = (
            "参考フレーム：1) 背景/目標 2) あなたの担当 3) 主要な行動 "
            "4) 定量的な結果/学び。回答は2〜3文に分け、まず結論を示してから詳細を述べましょう。"
        )
        return brief_tone, detailed, revised

    if metric_type == SuperMetricType.EVIDENCE:
        detailed = join_lines(
            "具体的な案件、時期、技術スタックを補足すると、より説得力が出ますよ。",
            "データや成果、フィードバックに触れると、面接官の信頼を高めることができます。",
            focus_hint,
        )
        revised = (
            "「状況-課題-行動-結果」モデルを使いましょう。まず背景と課題を述べ、"
            "あなたの具体的行動を説明し、データで結果を示します。"
        )
        return brief_tone, detailed, revised

    if metric_type == SuperMetricType.IMPACT:
        detailed = join_lines(
            "影響を定量化すると、もっと印象に残りますよ（例：コストをどれだけ削減、効率をどれだけ向上）。",
            "個人の貢献とチームの成果を分けて示すと、あなたの影響力がより明確に伝わりますね。",
            focus_hint,
        )
        revised = (
            "成果を述べる際は「数値＋指標＋期間」を入れましょう。例えば：「API応答時間を"
            "800ms から 200ms へ最適化し、苦情率が 40% 低下」。"
        )
        return brief_tone, detailed, revised

    if metric_type == SuperMetricType.ENGAGEMENT:
        detailed = join_lines(
            "面接官の質問に共感を示し、要約や短い応答から入ると、会話がもっと弾みますよ。",
            "会社/ポジションに関する事前調査の印象を補足すると、あなたの関心とコミットメントが伝わりますね。",
            focus_hint,
        )
        revised = (
            "回答の最初の3秒で短く呼応しましょう（例：「良いご質問ですね」）。"
            "自社プロダクトや文化、直近の動向に関する1〜2例を交えて所感を述べましょう。"
        )
        return brief_tone, detailed, revised

    if metric_type == SuperMetricType.VERBAL_PERFORMANCE:
        detailed = join_lines(
            "話す速度とポーズを調整し、キーセンテンスを際立たせると、より魅力的になりますよ。",
            "抑揚とエネルギーを保つと、単調さを避けることができますね。",
            focus_hint,
        )
        revised = (
            "練習では「強調語＋キーフレーズ＋短いポーズ」のリズムを意識しましょう。"
            "例：「最も重要な経験は、XXプロジェクトで…（一拍）私が具体的に行ったのは…」。"
        )
        return brief_tone, detailed, revised

    if metric_type == SuperMetricType.VISUAL_PERFORMANCE:
        detailed = join_lines(
            "視線と表情に注意し、カメラを見ながら自然な微笑みを保つと良いですね。",
            "姿勢を整え、肩の力を抜き、過度な身振りを避けると、よりプロフェッショナルな印象になりますよ。",
            focus_hint,
        )
        revised = (
            "事前に機器の高さを調整し、視線がレンズと水平になるようにしましょう。回答中はオープンな手振りを心がけ、"
            "要所でうなずきや微笑みを入れると自信が伝わります。"
        )
        return brief_tone, detailed, revised

    # Fallback for unforeseen metric types
    detailed = join_lines(
        "重要情報を整理し、実例と結び付けると、より分かりやすくなりますよ。",
        "定量データや具体例を用いると、説得力が高まりますね。",
        focus_hint,
    )
    revised = (
        "「結論→根拠→事例」の順で回答を構成し、まず見解を述べ、その後にデータや経験を補いましょう。"
    )
    return brief_tone, detailed, revised


def build_rule_based_feedback(
    super_metric: SuperMetric,
    section: DialogSection,
) -> SuperMetricFeedback:
    """
    Construct a SuperMetricFeedback instance with meaningful guidance derived from
    the score label and 指標の種類.
    """
    metric_type = super_metric.metadata.super_metric_type
    score_label = super_metric.score.score_label

    brief_core, detailed, revised = _metric_specific_guidance(metric_type, score_label)

    metric_display_names: Dict[SuperMetricType, str] = {
        SuperMetricType.CLARITY: "話の構成",
        SuperMetricType.EVIDENCE: "エビデンス",
        SuperMetricType.IMPACT: "成果のインパクト",
        SuperMetricType.ENGAGEMENT: "エンゲージメント",
        SuperMetricType.VERBAL_PERFORMANCE: "言語表現",
        SuperMetricType.VISUAL_PERFORMANCE: "カメラ映り",
    }
    display_name = metric_display_names.get(metric_type, metric_type.value.title())

    candidate_answer = _extract_candidate_answer(section)
    if candidate_answer:
        detailed = f"{detailed} 現在の回答例：{candidate_answer}"

    # Yoodli-style: Use warm, friendly format without colon separation
    brief_feedback = brief_core  # Direct friendly message, no formal prefix

    return SuperMetricFeedback(
        brief_feedback=brief_feedback,
        revised_response=revised,
        feedback=detailed,
        section_index=section.section_index,
    )


