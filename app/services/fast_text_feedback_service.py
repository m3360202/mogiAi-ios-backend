"""
Fast text-only feedback generator for section evaluation.

Goal: Generate cached feedback for text-based super-metrics quickly (no vision),
so TwoPhaseEvaluation can skip slow per-super-metric feedback LLM calls.

This service returns a dict compatible with TwoPhaseEvaluation cached_feedback:
{
  "clarity": {"brief_feedback": "...", "detailed_feedback": "...", "revised_response": ""},
  "evidence": {...},
  "impact": {...},
  "engagement": {...},
  # optional placeholders:
  "verbal_performance": {...},
  "visual_performance": {...}
}
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from openai import AsyncOpenAI
from app.core.llm_factory import llm_factory


def _norm_lang(language: str) -> str:
    if not isinstance(language, str) or not language:
        return "ja"
    if language.startswith("zh"):
        return "zh"
    if language.startswith("en"):
        return "en"
    return "ja"


def _load_unified_prompt(language: str) -> str:
    """
    Load v3 unified evaluation system prompt for language.
    We will reuse its feedback rules & vocabulary sets for text-only fast evaluation.
    
    Update: Since prompts are now split, we load the clarity dimension prompt as a representative source 
    for general feedback rules, or fallback to a simple prompt construction.
    """
    lang = _norm_lang(language)
    # Use clarity system prompt as it contains the general rules
    prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / "clarity" / f"system_msg_{lang}.md"
    
    if not prompt_path.exists():
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / "clarity" / "system_msg_zh.md"
        
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_feedback_rules(unified_prompt: str, language: str) -> str:
    """
    Extract the feedback-related rules section from the unified system prompt.
    We intentionally avoid the unified output-format part to prevent conflicts.
    """
    if not unified_prompt:
        return ""

    lang = _norm_lang(language)
    if lang == "zh":
        # From '## 【反馈生成规则】' to end
        anchor = "## 【反馈生成规则】"
    elif lang == "en":
        anchor = "## 【Feedback Generation Rules】"
    else:
        anchor = "## 【フィードバック生成ルール】"

    idx = unified_prompt.find(anchor)
    if idx == -1:
        return ""
    return unified_prompt[idx:].strip()


def _text_only_system_prompt(language: str) -> str:
    """
    Build system prompt for fast text-only evaluation using v3 unified prompt rules.
    """
    unified = _load_unified_prompt(language)
    rules = _extract_feedback_rules(unified, language)
    lang = _norm_lang(language)

    base = ""
    if lang == "zh":
        base = (
            "你只评估【4个文本维度】：clarity/evidence/impact/engagement。\n"
            "禁止做视觉/语音分析（不看视频帧，不基于音频做推断），禁止编造非语言内容。\n"
            "分数范围 0-100。\n"
            "只输出 JSON，不要输出任何额外文字。\n"
        )
    elif lang == "en":
        base = (
            "Evaluate ONLY the 4 text dimensions: clarity/evidence/impact/engagement.\n"
            "Do NOT do visual/voice analysis and do NOT invent any nonverbal observations.\n"
            "Score range: 0-100.\n"
            "Return JSON only. No extra text.\n"
        )
    else:
        base = (
            "テキストの【4次元】のみ評価：clarity/evidence/impact/engagement。\n"
            "視覚/音声の分析は禁止（動画フレームは見ない、音声も推測しない）。非言語情報を捏造しない。\n"
            "スコア範囲 0-100。\n"
            "JSONのみ出力（余計な文章禁止）。\n"
        )

    # If we can't extract rules, fallback to old short prompt.
    if not rules:
        return _system_prompt(language)

    return base + "\n\n" + rules


def _system_prompt(language: str) -> str:
    lang = _norm_lang(language)
    if lang == "zh":
        return (
            "你是一名面试评测教练。你只评估【内容表达类】四个维度：clarity/evidence/impact/engagement。\n"
            "不要做视觉/语音分析（不看视频帧），不要编造非语言信息。\n"
            "请输出严格 JSON。分数范围 0-100。\n"
            "brief_feedback：45-55字；detailed_feedback：必须包含两段：'🔸 详细评价：' 与 '💡 改善提案：'。\n"
            "brief_feedback要求：简练、自然，针对具体内容点评，避免机械套话（如重复'你提到...'）。\n"
        )
    if lang == "en":
        return (
            "You are an interview feedback coach. Evaluate ONLY text-based dimensions: clarity/evidence/impact/engagement.\n"
            "Do NOT perform visual/voice analysis and do NOT invent nonverbal observations.\n"
            "Return STRICT JSON. Score range: 0-100.\n"
            "brief_feedback: 45-55 characters (roughly); detailed_feedback must include two sections: "
            "'🔸 Detailed evaluation:' and '💡 Improvement suggestions:'.\n"
        )
    # ja
    return (
        "あなたは面接フィードバックコーチです。テキストから【4次元】のみ評価します：clarity/evidence/impact/engagement。\n"
        "視覚/音声の分析はしない（動画フレームは見ない）。非言語情報を捏造しない。\n"
        "厳密に JSON を返す。スコアは 0-100。\n"
        "brief_feedback：45-55文字。detailed_feedback：必ず '🔸 詳細評価：' と '💡 改善提案：' の2段落。\n"
    )


def _user_prompt(language: str, question: str, answer: str) -> str:
    lang = _norm_lang(language)
    if lang == "zh":
        answer_length = len(answer) if answer else 0
        brief_instruction = ""
        if answer_length > 45:
            brief_instruction = "\n重要：brief_feedback 应简明扼要地指出回答中的关键点或问题，可适当引用原话但不必拘泥于特定格式（如'你提到...'）。请根据回答内容灵活调整语气。"
        return (
            f"【面试官问题】\n{question}\n\n"
            f"【候选人回答】\n{answer}\n\n"
            "请输出 JSON，结构如下（只包含这4个key）：\n"
            "{\n"
            '  "clarity": {"score": 0, "brief_feedback": "...", "detailed_feedback": "🔸 详细评价：...\\n\\n💡 改进建议：...", "revised_response": "..."},\n'
            '  "evidence": {"score": 0, "brief_feedback": "...", "detailed_feedback": "🔸 详细评价：...\\n\\n💡 改进建议：...", "revised_response": "..."},\n'
            '  "impact": {"score": 0, "brief_feedback": "...", "detailed_feedback": "🔸 详细评价：...\\n\\n💡 改进建议：...", "revised_response": "..."},\n'
            '  "engagement": {"score": 0, "brief_feedback": "...", "detailed_feedback": "🔸 详细评价：...\\n\\n💡 改进建议：...", "revised_response": "..."}\n'
            "}\n"
            "注意：detailed_feedback 必须严格包含 '🔸 详细评价：' 和 '💡 改进建议：' 两个标题。"
            f"{brief_instruction}\n"
        )
    if lang == "en":
        answer_length = len(answer) if answer else 0
        brief_instruction = ""
        if answer_length > 45:
            brief_instruction = "\nIMPORTANT: brief_feedback must quote a sentence from the candidate's answer (use quotation marks), e.g., \"You mentioned...\" or \"As you said...\"."
        return (
            f"Question:\n{question}\n\n"
            f"Answer:\n{answer}\n\n"
            "Return JSON with ONLY these 4 keys:\n"
            "{\n"
            '  "clarity": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""},\n'
            '  "evidence": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""},\n'
            '  "impact": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""},\n'
            '  "engagement": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""}\n'
            "}\n"
            f"{brief_instruction}\n"
        )
    # ja
    answer_length = len(answer) if answer else 0
    brief_instruction = ""
    if answer_length > 45:
        brief_instruction = "\n重要：brief_feedback には候補者の回答から一文を引用してください（引用符で囲む）。例：「あなたが言及した...」または「あなたが述べたように...」。"
    return (
        f"【質問】\n{question}\n\n"
        f"【回答】\n{answer}\n\n"
        "次の4キーのみで JSON を返してください：\n"
        "{\n"
        '  "clarity": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""},\n'
        '  "evidence": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""},\n'
        '  "impact": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""},\n'
        '  "engagement": {"score": 0, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""}\n'
        "}\n"
        f"{brief_instruction}\n"
    )


def _dimension_prompt_snippet(language: str, dimension: str) -> str:
    """
    Small per-dimension rubric reminder to reduce ambiguity when splitting into
    parallel single-dimension calls.
    """
    dim = (dimension or "").strip().lower()
    lang = _norm_lang(language)
    if lang == "zh":
        if dim == "clarity":
            return "维度=clarity：结构是否清晰（SDS/先总后分），要点是否明确，是否跑题。"
        if dim == "evidence":
            return "维度=evidence：是否有具体例子/数据/结果支撑，细节是否可验证。"
        if dim == "impact":
            return "维度=impact：是否体现影响/价值/结果，是否有深度与洞察。"
        if dim == "engagement":
            return "维度=engagement：表达是否有互动性/故事性/吸引力，是否引导对话。"
        return f"维度={dim}"
    if lang == "en":
        if dim == "clarity":
            return "Dimension=clarity: structure, clarity, staying on-topic."
        if dim == "evidence":
            return "Dimension=evidence: concrete examples, data, verifiable outcomes."
        if dim == "impact":
            return "Dimension=impact: impact/value/results, depth and insight."
        if dim == "engagement":
            return "Dimension=engagement: engaging delivery, interaction, story, invites dialogue."
        return f"Dimension={dim}"
    # ja
    if dim == "clarity":
        return "次元=clarity：構成の明確さ（SDS/要点）、論旨、質問への適合。"
    if dim == "evidence":
        return "次元=evidence：具体例/数値/成果など根拠の有無、検証可能性。"
    if dim == "impact":
        return "次元=impact：影響/価値/結果、深さ・洞察。"
    if dim == "engagement":
        return "次元=engagement：引き込み・対話性・ストーリー性。"
    return f"次元={dim}"


def _single_dimension_user_prompt(language: str, *, dimension: str, question: str, answer: str) -> str:
    """
    Single-dimension prompt to reduce output tokens and allow parallelization.
    Returns a JSON object ONLY for the requested dimension schema.
    """
    dim = (dimension or "").strip().lower()
    lang = _norm_lang(language)
    rubric = _dimension_prompt_snippet(language, dim)
    
    if lang == "zh":
        answer_length = len(answer) if answer else 0
        brief_instruction = ""
        if answer_length > 45:
            focus = ""
            if dim == "clarity":
                focus = "请重点关注逻辑结构或核心论点，优先引用体现层次或观点的句子。"
            elif dim == "evidence":
                focus = "请重点关注具体事例、数据或细节，优先引用描述行动或事实的句子。"
            elif dim == "impact":
                focus = "请重点关注结果、价值或反思，优先引用描述成果或感悟的句子。"
            elif dim == "engagement":
                focus = "请重点关注表达风格或互动感，优先引用体现态度或情感的句子。"
            
            brief_instruction = f"\n重要：brief_feedback 应简明扼要地指出关键点，可适当引用原话但不必拘泥于格式。{focus} 尽量避免与其他维度重复引用同一句话。"

        return (
            f"【面试官问题】\n{question}\n\n"
            f"【候选人回答】\n{answer}\n\n"
            f"{rubric}\n\n"
            "请只评估上述一个维度，并输出严格 JSON（不要额外文字），结构如下：\n"
            "{\n"
            '  "score": 0,\n'
            '  "brief_feedback": "...",\n'
            '  "detailed_feedback": "🔸 详细评价：...\\n\\n💡 改进建议：...",\n'
            '  "revised_response": ""\n'
            "}\n"
            "注意：detailed_feedback 必须严格包含 '🔸 详细评价：' 和 '💡 改进建议：' 两个标题。"
            f"{brief_instruction}\n"
        )
    if lang == "en":
        answer_length = len(answer) if answer else 0
        brief_instruction = ""
        if answer_length > 45:
            brief_instruction = ""
            if dim == "clarity":
                focus = "Focus on structure/logic. Quote sentences showing organization or main points."
            elif dim == "evidence":
                focus = "Focus on details/data. Quote sentences describing specific actions or facts."
            elif dim == "impact":
                focus = "Focus on results/value. Quote sentences describing outcomes or reflections."
            elif dim == "engagement":
                focus = "Focus on delivery/style. Quote sentences showing attitude or interaction."
                
            brief_instruction = f"\nIMPORTANT: brief_feedback should be concise. {focus} Try to avoid quoting the same sentence used in other feedback dimensions."

        return (
            f"Question:\n{question}\n\n"
            f"Answer:\n{answer}\n\n"
            f"{rubric}\n\n"
            "Evaluate ONLY the single dimension above and return STRICT JSON (no extra text):\n"
            "{\n"
            '  "score": 0,\n'
            '  "brief_feedback": "",\n'
            '  "detailed_feedback": "",\n'
            '  "revised_response": ""\n'
            "}\n"
            f"{brief_instruction}\n"
        )
    # ja
    answer_length = len(answer) if answer else 0
    brief_instruction = ""
    if answer_length > 45:
        focus = ""
        if dim == "clarity":
            focus = "構成や論理に着目し、構造や要点を示す文を優先的に引用してください。"
        elif dim == "evidence":
            focus = "具体例やデータに着目し、具体的な行動や事実を述べている文を優先的に引用してください。"
        elif dim == "impact":
            focus = "結果や価値に着目し、成果や振り返りを述べている文を優先的に引用してください。"
        elif dim == "engagement":
            focus = "表現スタイルに着目し、態度や対話性を示す文を優先的に引用してください。"
            
        brief_instruction = f"\n重要：brief_feedback は簡潔に要点を指摘してください。{focus} 他の評価次元と同じ文を繰り返し引用しないようにしてください。"

    return (
        f"【質問】\n{question}\n\n"
        f"【回答】\n{answer}\n\n"
        f"{rubric}\n\n"
        "上記の1次元のみを評価し、厳密に JSON のみ返してください：\n"
        "{\n"
        '  "score": 0,\n'
        '  "brief_feedback": "",\n'
        '  "detailed_feedback": "",\n'
        '  "revised_response": ""\n'
        "}\n"
        f"{brief_instruction}\n"
    )


async def _generate_single_dimension_cached(
    *,
    dimension: str,
    question: str,
    answer: str,
    language: str,
    client: AsyncOpenAI,
    model: str,
) -> Dict[str, Any]:
    """
    Generate cached feedback for a single text dimension.
    Output schema matches cached_feedback items expected by TwoPhaseEvaluation.
    """
    messages = [
        {"role": "system", "content": _text_only_system_prompt(language)},
        {
            "role": "user",
            "content": _single_dimension_user_prompt(
                language,
                dimension=dimension,
                question=question or "",
                answer=answer or "",
            ),
        },
    ]
    
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError(f"LLM returned empty content for fast text feedback dim={dimension}")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        parsed = {}
    return {
        "score": parsed.get("score", 50),
        "brief_feedback": parsed.get("brief_feedback", ""),
        "detailed_feedback": parsed.get("detailed_feedback", ""),
        "revised_response": parsed.get("revised_response", "") or "",
    }


def _placeholder_nonverbal_feedback(language: str) -> Dict[str, Dict[str, Any]]:
    lang = _norm_lang(language)
    if lang == "zh":
        brief = "语音/视觉评测将在后台补全（不影响本次内容评测）。"
        detail = "🔸 详细评价：\n语音与视觉维度正在后台分析中，稍后会自动补全。\n\n💡 改善提案：\n请先关注本页的内容表达建议，非语言建议会在完成后更新。"
    elif lang == "en":
        brief = "Voice/visual feedback will be filled in shortly (background)."
        detail = "🔸 Detailed evaluation:\nVoice/visual dimensions are being analyzed in the background and will be updated.\n\n💡 Improvement suggestions:\nFocus on text-based feedback now; nonverbal tips will appear once ready."
    else:
        brief = "音声/視覚の評価はバックグラウンドで補完されます。"
        detail = "🔸 詳細評価：\n音声・視覚の次元はバックグラウンドで解析中のため、後ほど自動で反映されます。\n\n💡 改善提案：\nまずは内容面の改善に集中し、非言語の提案は解析完了後に確認してください。"
    placeholder = {
        "score": 50,
        "brief_feedback": brief,
        "detailed_feedback": detail,
        "revised_response": "",
    }
    return {"verbal_performance": placeholder, "visual_performance": placeholder}


async def generate_text_feedback_cached(
    *,
    question: str,
    answer: str,
    language: str = "ja",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate cached feedback dict for text-based dimensions quickly.
    """
    # Scheme B: split into parallel single-dimension calls to reduce wall-clock latency.
    client, default_model = llm_factory.get_non_visual_client()
    target_model = model or default_model
    
    dims = ("clarity", "evidence", "impact", "engagement")
    tasks = [
        _generate_single_dimension_cached(
            dimension=dim,
            question=question,
            answer=answer,
            language=language,
            client=client,
            model=target_model,
        )
        for dim in dims
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: Dict[str, Any] = {}
    for dim, res in zip(dims, results):
        if isinstance(res, Exception):
            # Degrade gracefully: don't fail the whole cached feedback generation.
            print(f"[FastTextFeedback] ⚠️ Dimension {dim} failed: {res}")
            out[dim] = {"score": 50, "brief_feedback": "", "detailed_feedback": "", "revised_response": ""}
        else:
            out[dim] = res
    # Add placeholders so feedback generation can be fully skipped
    out.update(_placeholder_nonverbal_feedback(language))
    return out
