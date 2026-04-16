"""
视频内容分析评估器 - 多维度评估系统
提供视频面试的综合评估功能
"""
from __future__ import annotations
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# 元信息
# ============================================================
VERSION = "7axis-backend-1.0"
FEATURES = [
    "target",
    "target_text",
    "sample_fix",
    "improved_text",
    "scenario_aware_engagement",
    "langchain_integration",
]


# ============================================================
# 标签定义（7轴）- 中日双语
# ============================================================
AXIS_LABELS: List[Tuple[str, str, str]] = [
    ("clarity", "理解のしやすさ", "清晰度/易懂性"),
    ("evidence", "根拠・具体性", "证据/具体性"),
    ("delivery", "表現力・伝達力", "表达力/传达力"),
    ("engagement", "やりとり・双方向性", "互动性/双向性"),
    ("politeness", "礼儀・態度", "礼貌/态度"),
    ("impact", "印象・影響力", "影响力/记忆点"),
    ("nonverbal", "非言語表現（音声＋表情/身体）", "非语言表现（音频+视觉）"),
]


# ============================================================
# 规则评估关键词词典（中日混合）
# ============================================================
# 日语关键词
STRUCTURE_KWS_JA = ["まず", "次に", "続いて", "そのため", "したがって", "結論として", "要するに", "つまり", "最後に"]
AMBIG_JA = ["いろいろ", "様々", "とか", "など", "ある程度"]
FILLERS_JA = ["えー", "えっと", "そのー", "あのー", "まあ", "なんか"]
CONF_POS_JA = ["できます", "やり遂げます", "必ず", "自信が", "強みは", "貢献します", "いたします", "やり切ります"]
HEDGES_JA = ["かもしれ", "と思い", "と考えており", "可能性", "かと存じ", "〜だと思っており"]
POLITE_TOKENS_JA = ["です", "ます", "お願いいたします", "よろしくお願いいたします", "よろしくお願いします", "失礼", "恐れ入ります"]
GREET_JA = ["はじめまして", "お世話になっております", "よろしくお願いいたします", "よろしくお願いします", "失礼します"]
Q_MARKERS_JA = ["？", "でしょうか", "いかがですか", "教えてください", "お伺い"]
REF_MARKERS_JA = ["先ほど", "おっしゃる", "いただいた", "ご質問"]

# 中文关键词
STRUCTURE_KWS_ZH = ["首先", "其次", "接着", "因此", "所以", "总之", "也就是说", "最后", "综上"]
AMBIG_ZH = ["各种", "一些", "之类", "等等", "某种程度", "什么的"]
FILLERS_ZH = ["呃", "嗯", "那个", "就是", "然后", "其实", "有点儿", "这个"]
CONF_POS_ZH = ["能够", "一定", "保证", "有信心", "可以做到", "优势", "贡献", "必将"]
HEDGES_ZH = ["可能", "也许", "感觉", "认为", "大概", "我觉得", "或许", "似乎"]
POLITE_TOKENS_ZH = ["请", "谢谢", "劳驾", "麻烦您", "拜托", "打扰了", "您好"]
GREET_ZH = ["您好", "你好", "初次见面", "请多关照", "感谢"]
Q_MARKERS_ZH = ["？", "吗", "能否", "请问", "可以告诉我", "是否"]
REF_MARKERS_ZH = ["您刚才", "您提到", "刚才说的", "您的意思"]

# 合并中日关键词
STRUCTURE_KWS = STRUCTURE_KWS_JA + STRUCTURE_KWS_ZH
AMBIG = AMBIG_JA + AMBIG_ZH
FILLERS = FILLERS_JA + FILLERS_ZH
CONF_POS = CONF_POS_JA + CONF_POS_ZH
HEDGES = HEDGES_JA + HEDGES_ZH
POLITE_TOKENS = POLITE_TOKENS_JA + POLITE_TOKENS_ZH
GREET = GREET_JA + GREET_ZH
Q_MARKERS = Q_MARKERS_JA + Q_MARKERS_ZH
REF_MARKERS = REF_MARKERS_JA + REF_MARKERS_ZH

# 证据相关关键词
EVIDENCE_KWS_JA = ["経験", "実績", "活動", "成果", "プロジェクト", "達成"]
EVIDENCE_KWS_ZH = ["经验", "成绩", "活动", "成果", "案例", "项目", "达成"]
EVIDENCE_KWS = EVIDENCE_KWS_JA + EVIDENCE_KWS_ZH

# 影响力关键词
IMPACT_KWS_JA = ["強み", "結果", "価値", "効果", "向上"]
IMPACT_KWS_ZH = ["强み", "结果", "价值", "效果", "提升", "转化"]
IMPACT_KWS = IMPACT_KWS_JA + IMPACT_KWS_ZH

# 数字检测正则（支持中日数字）
NUM_RE = re.compile(r"[0-9０-９]+|[一二三四五六七八九十百千万億兆％%]")

# 句子分割（中日标点）
SENT_SPLIT = re.compile(r"[。！？\n]+")


# ============================================================
# 工具函数
# ============================================================
def _split_sentences(text: str) -> List[str]:
    """分割句子"""
    text = (text or "").strip()
    if not text:
        return []
    parts = SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _rate_1to5(value: float, thresholds: List[float], reverse: bool = False) -> int:
    """
    将数值映射到1-5分
    
    Args:
        value: 待评分的数值
        thresholds: 阈值列表（降序）
        reverse: 是否反向评分（越小越好）
    
    Returns:
        1-5的整数评分
    """
    ts = sorted(thresholds, reverse=True)
    if reverse:
        # 小值高分
        if value <= ts[-1]:
            return 5
        if value <= ts[-2]:
            return 4
        if value <= ts[-3]:
            return 3
        if value <= ts[-4]:
            return 2
        return 1
    else:
        # 大值高分
        if value >= ts[0]:
            return 5
        if value >= ts[1]:
            return 4
        if value >= ts[2]:
            return 3
        if value >= ts[3]:
            return 2
        return 1


def _pick_sentence_by_keywords(sentences: List[str], kws: List[str]) -> int:
    """根据关键词选择最佳句子索引"""
    if not sentences:
        return -1
    best_i, best_cnt = -1, 0
    for i, s in enumerate(sentences):
        c = sum(s.count(k) for k in kws)
        if c > best_cnt:
            best_cnt, best_i = c, i
    return best_i


def _pick_sentence_by_regex(sentences: List[str], pattern: re.Pattern) -> int:
    """根据正则表达式选择句子"""
    if not sentences:
        return -1
    for i, s in enumerate(sentences):
        if pattern.search(s):
            return i
    return -1


def _sample_fix_engagement_contextual(text: str, scenario: Optional[str]) -> str:
    """根据场景生成互动建议"""
    scenario_lower = (scenario or "").lower()
    
    if scenario_lower in {"self_intro", "self-intro", "intro", "自我介绍"}:
        return "【例】自己紹介のあと『私の強みは◯◯です。御社だと◯◯に活かせると考えていますが、期待に沿っていますか？』と相手の意図を確認する。\n【例】自我介绍后可以说：'我的优势是XX，在贵公司可以应用于XX领域，不知是否符合您的期待？'"
    
    if scenario_lower in {"sales", "bizdev", "营销", "商务"}:
        return "【例】本件の優先度は「納期・品質・コスト」のどれを最重視されていますか？背景も一言伺えますか。\n【例】本次项目在'交期、质量、成本'三方面，您最看重哪一个？能否简单说明一下背景？"
    
    # 通用模板
    return "【例】本件の重要度や期待する成果のイメージを一言伺えますか？差し支えなければ背景もお願いします。\n【例】能否请您简单说明一下本次的重要程度和期待的成果？如果方便的话，也想了解一下背景。"


def _compose_improved_text(sentences: List[str], language: str = "ja") -> str:
    """生成改进后的文本示例"""
    if language == "zh":
        return (
            "初次见面，我是XX大学XX专业的XX。"
            "【结论】我的优势是'发现问题和执行力'，可以在贵公司的XX领域创造价值。"
            " 大学期间担任XX社团负责人，带领【10人】团队，组织了【3次】月度活动，满意度达到【92%】。"
            " 每周通过'梳理状况→制定对策→执行→验证'的循环，提升了改进速度。"
            " 入职后将发挥这种执行力，向前辈学习，首先在XX项目中争取【3个月】内快速上手并做出贡献。"
            " 今天请多多关照。"
        )
    else:
        return (
            "はじめまして。◯◯大学◯◯学部の◯◯と申します。"
            "【結論】強みは「課題発見とやり切る力」で、御社では◯◯領域で価値提供できます。"
            " 学生時代は◯◯サークルで【10名】を率い、月次イベント【3回】を運営、満足度【92%】を達成。"
            " 状況整理→打ち手立案→実行→検証を毎週回し、改善速度を高めました。"
            " 入社後はこの実行力を活かしつつ、先輩から学び、まずは◯◯プロジェクトで【3ヶ月】以内に立ち上がりに貢献します。"
            " 本日はどうぞよろしくお願いいたします。"
        )


# ============================================================
# 主评估器类
# ============================================================
class VideoContentEvaluator:
    """视频内容七轴评估器"""
    
    def __init__(self):
        pass
    
    def evaluate(
        self,
        human_text: str,
        ai_text: Optional[str] = None,
        nonverbal: Optional[Dict[str, Any]] = None,
        scenario: Optional[str] = None,
        language: str = "ja"
    ) -> Dict[str, Any]:
        """
        执行七轴评估
        
        Args:
            human_text: 用户发言文本
            ai_text: AI发言文本（可选，用于上下文分析）
            nonverbal: 非语言特征字典，包含voice和visual
            scenario: 场景类型（self_intro, sales等）
            language: 语言（ja/zh）
            
        Returns:
            评估结果字典
        """
        text = (human_text or "").strip()
        sentences = _split_sentences(text)
        
        # ==================== 计算6个语言维度分数 ====================
        
        # 1. Clarity（清晰度）：句长、结构词、模糊词
        avg_len = statistics.mean([len(s) for s in sentences]) if sentences else 0
        struct_hits = sum(text.count(w) for w in STRUCTURE_KWS)
        ambig_hits = sum(w in text for w in AMBIG)
        
        clarity_mix = (
            _rate_1to5(abs(avg_len - 40), [30, 20, 10, 5], reverse=True) * 0.5
            + _rate_1to5(struct_hits, [5, 3, 2, 1], reverse=False) * 0.3
            + _rate_1to5(ambig_hits, [4, 3, 2, 1], reverse=True) * 0.2
        )
        clarity = int(max(1, min(5, round(clarity_mix))))
        
        # 2. Evidence（证据/具体性）：数字、实绩词
        evid_hits_num = 1 if NUM_RE.search(text) else 0
        evid_hits_kw = sum(w in text for w in EVIDENCE_KWS)
        evidence_score = _rate_1to5(evid_hits_num + evid_hits_kw, [4, 3, 2, 1], reverse=False)
        evidence = int(max(1, min(5, round(evidence_score))))
        
        # 3. Delivery（表达力）：自信词 vs 犹豫词+填充词
        conf_hits = sum(w in text for w in CONF_POS)
        hedge_hits = sum(w in text for w in HEDGES + FILLERS)
        delivery_score = _rate_1to5(conf_hits - hedge_hits, [3, 2, 1, 0], reverse=False)
        delivery = int(max(1, min(5, round(delivery_score))))
        
        # 4. Engagement（互动性）：提问、对方指称
        engage_hits = sum(w in text for w in Q_MARKERS + REF_MARKERS)
        engagement_score = _rate_1to5(engage_hits, [3, 2, 1, 0], reverse=False)
        engagement = int(max(1, min(5, round(engagement_score))))
        
        # 5. Politeness（礼貌）：礼貌用语、问候
        polite_hits = sum(w in text for w in POLITE_TOKENS + GREET)
        politeness_score = _rate_1to5(polite_hits, [4, 3, 2, 1], reverse=False)
        politeness = int(max(1, min(5, round(politeness_score))))
        
        # 6. Impact（影响力）：优势/价值词 + 自信词
        impact_hits = sum(w in text for w in (IMPACT_KWS + CONF_POS))
        impact_score = _rate_1to5(impact_hits, [4, 3, 2, 1], reverse=False)
        impact = int(max(1, min(5, round(impact_score))))
        
        # ==================== 选择目标句（最能体现该维度的句子） ====================
        clarity_i = _pick_sentence_by_keywords(sentences, STRUCTURE_KWS)
        evid_i = _pick_sentence_by_regex(sentences, NUM_RE)
        if evid_i == -1:
            evid_i = _pick_sentence_by_keywords(sentences, EVIDENCE_KWS)
        deliv_i = _pick_sentence_by_keywords(sentences, HEDGES + FILLERS)
        engage_i = _pick_sentence_by_keywords(sentences, Q_MARKERS + REF_MARKERS)
        polite_i = _pick_sentence_by_keywords(sentences, GREET)
        imp_i = _pick_sentence_by_keywords(sentences, IMPACT_KWS + CONF_POS)
        
        def _target_tuple(idx: int) -> Tuple[str, str]:
            """获取目标句元组"""
            if idx is None or idx < 0 or idx >= len(sentences):
                return ("全体" if language == "ja" else "整体", "—")
            return (f"文{idx + 1}" if language == "ja" else f"句{idx + 1}", sentences[idx])
        
        tar_c, txt_c = _target_tuple(clarity_i)
        tar_e, txt_e = _target_tuple(evid_i)
        tar_d, txt_d = _target_tuple(deliv_i)
        tar_g, txt_g = _target_tuple(engage_i)
        tar_p, txt_p = _target_tuple(polite_i)
        tar_i, txt_i = _target_tuple(imp_i)
        
        # ==================== 非语言维度（可选） ====================
        nonverbal_score: Optional[int] = None
        nonverbal_reason = "非言語情報は未提供（音声/映像未解析）" if language == "ja" else "非语言信息未提供（音频/视频未解析）"
        nonverbal_details = {}
        
        if nonverbal:
            v = nonverbal or {}
            voice = v.get("voice", {})
            visual = v.get("visual", {})
            
            # 音频特征
            vol = float(voice.get("volume_db_norm", 0.0))  # 音量（归一化0-1）
            pros = float(voice.get("prosody_var", 0.0))     # 抑扬变化
            rate = float(voice.get("speech_rate_norm", 0.5)) # 语速（0.5为最佳）
            rate_score = max(0.0, 1 - abs(rate - 0.5) * 2)
            
            # 视觉特征
            smile = float(visual.get("smile_rate", 0.0))           # 微笑占比
            eye = float(visual.get("eye_contact_rate", 0.0))       # 目光接触
            posture = float(visual.get("posture_stability", 0.0))  # 姿态稳定
            
            # 综合计算（权重）
            composite = (
                vol * 0.25 + 
                pros * 0.20 + 
                rate_score * 0.15 + 
                smile * 0.20 + 
                eye * 0.10 + 
                posture * 0.10
            )
            
            nonverbal_score = max(1, min(5, int(round(1 + composite * 4))))
            
            nonverbal_details = {
                "volume": vol,
                "prosody": pros,
                "speech_rate": rate,
                "smile": smile,
                "eye_contact": eye,
                "posture": posture,
                "composite": composite
            }
            
            if language == "ja":
                nonverbal_reason = (
                    f"音声/表情指標: vol={vol:.2f}, pros={pros:.2f}, rate={rate:.2f}, "
                    f"smile={smile:.2f}, eye={eye:.2f}, posture={posture:.2f}"
                )
            else:
                nonverbal_reason = (
                    f"音频/表情指标: 音量={vol:.2f}, 抑扬={pros:.2f}, 语速={rate:.2f}, "
                    f"微笑={smile:.2f}, 视线={eye:.2f}, 姿态={posture:.2f}"
                )
        
        # ==================== 构建建议与改进示例 ====================
        sample_engage = _sample_fix_engagement_contextual(text, scenario)
        
        # 语言特定的建议文本
        if language == "zh":
            advice_clarity = "段落开头使用结构词明确论点。控制单句在40字左右，将模糊词具体化。"
            advice_evidence = "主张与根据（数字/事例/专有名词）配套呈现。"
            advice_delivery = "结论前置，增加断定表达，减少犹豫词和口头禅。"
            advice_engagement = "增加开放式提问，确认对方的意图和优先级。"
            advice_politeness = "开头和结尾整理问候与请求语句，避免过度谦卑。"
            advice_impact = "先简洁说明价值和结果，用专有名词和数字增强可信度。"
            advice_nonverbal = "保持音量、抑扬、语速的稳定，适度保持微笑、视线和姿态。"
            
            sample_clarity = "【例】首先说结论，其次说根据，最后说今后的对策。"
            sample_evidence = "【例】同比去年增长【12%】，通过实施XX策略，CVR提升了【1.3pt】。"
            sample_delivery = "【例】结论是，我将执行XX。理由是XX，预想风险是XX。"
            sample_politeness = "【例】感谢您抽出时间。我只分享要点部分。"
            sample_impact = "【例】我的优势是执行力，可以在XX项目中【3个月】内快速上手并做出贡献。"
            sample_nonverbal = "【例】语尾轻微上扬/每3个词稍作停顿/重点处点头。"
        else:
            advice_clarity = "段落頭に構造語を入れて論旨を明示。1文40字程度を目安に簡潔化し、曖昧語を具体化する。"
            advice_evidence = "主張と根拠（数値/事例/固有名詞）をセットで提示する。"
            advice_delivery = "結論先出し＋断定表現を増やし、ヘッジ・フィラーは削減。"
            advice_engagement = "オープンな問いを増やし、相手の意図・優先度を確認する。"
            advice_politeness = "冒頭/末尾の挨拶と依頼句を整え、過度なへりくだりは避ける。"
            advice_impact = "先に価値・結果を端的に示し、固有名/数値で確からしさを補強。"
            advice_nonverbal = "声量・抑揚・話速の安定、微笑・視線・姿勢を適度に保つ。"
            
            sample_clarity = "【例】まず結論、次に根拠、最後に今後の打ち手を述べます。"
            sample_evidence = "【例】前年同期比【12%】増、◯◯施策の実施でCVR【1.3pt】改善。"
            sample_delivery = "【例】結論として、◯◯を実行します。理由は◯◯、想定リスクは◯◯です。"
            sample_politeness = "【例】お時間を頂きありがとうございます。要点のみ共有いたします。"
            sample_impact = "【例】強みは実行力で、◯◯で【3ヶ月】以内に立ち上がりに貢献します。"
            sample_nonverbal = "【例】語尾で軽く上げる/3語ごとに小休止/要所で頷く。"
        
        # ==================== 构建详细结果 ====================
        table_rows = [
            {
                "key": "clarity",
                "label": AXIS_LABELS[0][1] if language == "ja" else AXIS_LABELS[0][2],
                "score": f"{clarity}/5",
                "target": tar_c,
                "target_text": txt_c,
                "snippet": txt_c,
                "reason": "文長の適正・構造語（まず/次に/最後に）・曖昧語の少なさを総合評価。" if language == "ja" else "句长适当性、结构词（首先/其次/最后）、模糊词较少的综合评价。",
                "advice": advice_clarity,
                "sample_fix": sample_clarity,
            },
            {
                "key": "evidence",
                "label": AXIS_LABELS[1][1] if language == "ja" else AXIS_LABELS[1][2],
                "score": f"{evidence}/5",
                "target": tar_e,
                "target_text": txt_e,
                "snippet": txt_e,
                "reason": "数値・固有表現・実績語の有無で具体性を評価。" if language == "ja" else "根据数字、专有名词、实绩词的有无评价具体性。",
                "advice": advice_evidence,
                "sample_fix": sample_evidence,
            },
            {
                "key": "delivery",
                "label": AXIS_LABELS[2][1] if language == "ja" else AXIS_LABELS[2][2],
                "score": f"{delivery}/5",
                "target": tar_d,
                "target_text": txt_d,
                "snippet": txt_d,
                "reason": "断定系（できます/やり切ります）とためらい語/フィラーのバランスを評価。" if language == "ja" else "断定表达（能够/一定）与犹豫词/口头禅的平衡评价。",
                "advice": advice_delivery,
                "sample_fix": sample_delivery,
            },
            {
                "key": "engagement",
                "label": AXIS_LABELS[3][1] if language == "ja" else AXIS_LABELS[3][2],
                "score": f"{engagement}/5",
                "target": tar_g,
                "target_text": txt_g,
                "snippet": txt_g,
                "reason": "質問・相手参照（先ほど/ご質問/いかがですか）の有無を評価。" if language == "ja" else "提问、对方指称（刚才/您提到/是否）的有无评价。",
                "advice": advice_engagement,
                "sample_fix": sample_engage,
            },
            {
                "key": "politeness",
                "label": AXIS_LABELS[4][1] if language == "ja" else AXIS_LABELS[4][2],
                "score": f"{politeness}/5",
                "target": tar_p,
                "target_text": txt_p,
                "snippet": txt_p,
                "reason": "挨拶・丁寧語（です/ます/お願いいたします）を評価。" if language == "ja" else "问候、礼貌用语（请/谢谢/您好）的评价。",
                "advice": advice_politeness,
                "sample_fix": sample_politeness,
            },
            {
                "key": "impact",
                "label": AXIS_LABELS[5][1] if language == "ja" else AXIS_LABELS[5][2],
                "score": f"{impact}/5",
                "target": tar_i,
                "target_text": txt_i,
                "snippet": txt_i,
                "reason": "強み/価値/結果などの強調語の有無を評価。" if language == "ja" else "强项/价值/结果等强调词的有无评价。",
                "advice": advice_impact,
                "sample_fix": sample_impact,
            },
            {
                "key": "nonverbal",
                "label": AXIS_LABELS[6][1] if language == "ja" else AXIS_LABELS[6][2],
                "score": f"{nonverbal_score}/5" if nonverbal_score else "N/A",
                "target": ("全体", "—") if language == "ja" else ("整体", "—"),
                "target_text": "—",
                "snippet": "—",
                "reason": nonverbal_reason,
                "advice": advice_nonverbal,
                "sample_fix": sample_nonverbal,
                "details": nonverbal_details,
            },
        ]
        
        # ==================== 总结与改进文本 ====================
        provided_scores = [clarity, evidence, delivery, engagement, politeness, impact]
        total_score = sum(provided_scores)
        max_score = len(provided_scores) * 5
        
        if language == "zh":
            summary = f"总分 {total_score}/{max_score}（非语言维度仅在提供时计入）"
        else:
            summary = f"総合 {total_score}/{max_score}（非言語は提供時のみ加点）"
        
        improved_text = _compose_improved_text(sentences, language)
        
        # ==================== 构建最终结果 ====================
        result: Dict[str, Any] = {
            "labels": {k: (v1 if language == "ja" else v2) for k, v1, v2 in AXIS_LABELS},
            "scores": {
                "clarity": clarity,
                "evidence": evidence,
                "delivery": delivery,
                "engagement": engagement,
                "politeness": politeness,
                "impact": impact,
                "nonverbal": nonverbal_score,
                "total": total_score,
                "max": max_score,
            },
            "details": {
                r["key"]: {
                    "reason": r["reason"],
                    "advice": r["advice"],
                    "snippet": r["snippet"],
                    "target": r["target"],
                    "target_text": r["target_text"],
                    "sample_fix": r["sample_fix"],
                    "details": r.get("details", {}),
                }
                for r in table_rows
            },
            "table_rows": table_rows,
            "improved_text": improved_text,
            "summary": summary,
            "__meta": {
                "version": VERSION,
                "features": FEATURES,
                "language": language,
                "scenario": scenario,
            },
        }
        
        return result


# 创建全局实例
video_evaluator = VideoContentEvaluator()

