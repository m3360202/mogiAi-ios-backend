"""
快速评估适配器 - 使用 FastInterviewEvaluator
单次LLM调用，3-8秒响应
"""
from typing import Dict, Any, List, Optional
from app.services.fast_interview_evaluator import get_fast_evaluator


class FastEvaluationAdapter:
    """快速评估适配器 - 面向流式面试"""
    
    def __init__(self):
        self.evaluator = get_fast_evaluator()
        # 维度映射：从新的6维度到旧的6维度
        self.dimension_mapping = {
            "content": "clarity",      # 内容完整性 -> 清晰度
            "logic": "evidence",        # 逻辑清晰度 -> 论证力
            "expression": "delivery",   # 表达流畅度 -> 表达能力
            "engagement": "engagement", # 互动参与度 -> 互动性
            "professionalism": "politeness",  # 专业素养 -> 礼貌度
            "growth": "impact",         # 成长潜力 -> 影响力
        }
    
    async def evaluate_turn(
        self,
        transcript: str,
        turn_index: int,
        question: Optional[str] = None,
        nonverbal_snapshot: Optional[Dict[str, Any]] = None,
        session_id: str = "stream",
    ) -> Dict[str, Any]:
        """
        评估单轮对话（使用快速评估器）
        
        Args:
            transcript: 用户回答文本
            turn_index: 回合索引（从0开始）
            question: 面试官问题
            nonverbal_snapshot: 非语言表现快照
            session_id: 会话ID
            
        Returns:
            包含评分和反馈的字典
        """
        print(f"[FastAdapter] 🚀 Evaluating turn {turn_index}...")
        
        # 构建对话数据
        interview_data = []
        if question:
            interview_data.append({
                "role": "system",
                "content": question,
            })
        interview_data.append({
            "role": "user",
            "content": transcript,
        })
        
        try:
            # 调用快速评估器
            result = await self.evaluator.evaluate(
                interview_data=interview_data,
                position="候选人"
            )
            
            # 转换为流式格式
            scores = {}
            for new_dim, old_dim in self.dimension_mapping.items():
                if new_dim in result.dimensions:
                    scores[old_dim] = result.dimensions[new_dim].score
                else:
                    scores[old_dim] = None
            
            # 计算平均分
            available_scores = [s for s in scores.values() if s is not None]
            average = sum(available_scores) / len(available_scores) if available_scores else 0.0
            
            # 提取问题点（从各维度的brief中）
            issues = []
            for dim_key, dim_data in result.dimensions.items():
                if dim_data.score <= 2:  # 低分维度
                    issues.append(f"{dim_key}: {dim_data.brief}")
            
            # 生成简要反馈
            brief = self._generate_brief(result, scores, nonverbal_snapshot)
            
            # 非语言表现摘要
            nonverbal_summary = self._summarize_nonverbal(nonverbal_snapshot)
            
            print(f"[FastAdapter] ✅ Turn {turn_index} evaluated: {result.overall_score}/5")
            
            return {
                "turn_index": turn_index,
                "transcript": transcript,
                "question": question,
                "scores": scores,
                "average": average,
                "overall_score": result.overall_score * 20,  # 转换为0-100分
                "brief": brief,
                "issues": issues[:4],  # 最多4个问题点
                "nonverbal_summary": nonverbal_summary,
                "detailed_feedback": {  # 添加详细反馈
                    dim_key: {
                        "score": dim_data.score,
                        "brief": dim_data.brief,
                        "description": dim_data.description
                    }
                    for dim_key, dim_data in result.dimensions.items()
                }
            }
            
        except Exception as e:
            print(f"[FastAdapter] ❌ Evaluation failed: {e}")
            # 返回默认值
            return self._get_fallback_result(turn_index, transcript, question, nonverbal_snapshot)
    
    def _generate_brief(
        self,
        result,
        scores: Dict[str, Optional[int]],
        nonverbal: Optional[Dict[str, Any]],
    ) -> str:
        """生成简要反馈"""
        parts: List[str] = []
        
        # 使用整体简评
        if result.overall_brief:
            parts.append(result.overall_brief)
        
        # 找出低分维度并添加建议
        low_dims = [
            (dim_key, dim_data)
            for dim_key, dim_data in result.dimensions.items()
            if dim_data.score <= 2
        ]
        if low_dims:
            for dim_key, dim_data in low_dims[:2]:  # 最多2个
                parts.append(f"{dim_key}: {dim_data.brief}")
        
        # 添加非语言反馈
        if nonverbal:
            nv_text = self._brief_nonverbal(nonverbal)
            if nv_text:
                parts.append(nv_text)
        
        if not parts:
            return "整体表现良好，继续保持。"
        
        return "；".join(parts)
    
    def _brief_nonverbal(self, nonverbal: Dict[str, Any]) -> str:
        """生成非语言简要反馈"""
        eye = nonverbal.get("eye_contact_rate") or nonverbal.get("eye_contact")
        smile = nonverbal.get("smile_rate") or nonverbal.get("smile")
        posture = nonverbal.get("pose_stability") or nonverbal.get("posture")
        
        fragments: List[str] = []
        if isinstance(eye, (int, float)):
            if eye < 0.4:
                fragments.append("眼神接触不足")
            elif eye > 0.75:
                fragments.append("眼神接触优秀")
        if isinstance(smile, (int, float)):
            if smile < 0.2:
                fragments.append("表情略显紧张")
            elif smile > 0.6:
                fragments.append("表情自然大方")
        if isinstance(posture, (int, float)):
            if posture < 0.4:
                fragments.append("姿态不够稳定")
        
        return "，".join(fragments)
    
    def _summarize_nonverbal(self, nonverbal: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """汇总非语言表现"""
        if not isinstance(nonverbal, dict):
            return None
        
        summary_keys = {
            "eye_contact_rate": nonverbal.get("eye_contact_rate"),
            "smile_rate": nonverbal.get("smile_rate"),
            "pose_stability": nonverbal.get("pose_stability"),
            "confidence": nonverbal.get("confidence"),
        }
        return {k: v for k, v in summary_keys.items() if v is not None}
    
    def _get_fallback_result(
        self,
        turn_index: int,
        transcript: str,
        question: Optional[str],
        nonverbal_snapshot: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """获取降级结果（评估失败时）"""
        scores = {axis: 3 for axis in ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]}
        return {
            "turn_index": turn_index,
            "transcript": transcript,
            "question": question,
            "scores": scores,
            "average": 3.0,
            "overall_score": 60,
            "brief": "评估服务暂时不可用，稍后查看完整评估。",
            "issues": [],
            "nonverbal_summary": self._summarize_nonverbal(nonverbal_snapshot),
        }
    
    def aggregate(self, evaluations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        聚合多轮评估
        
        Args:
            evaluations: 评估结果列表
            
        Returns:
            聚合后的评估结果
        """
        if not evaluations:
            return {
                "overall_score": 0,
                "average_score": 0.0,
                "per_axis": {axis: None for axis in ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]},
                "brief": "面试数据不足，无法生成评估。",
                "turns": [],
            }
        
        per_axis: Dict[str, List[int]] = {
            axis: [] for axis in ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]
        }
        turn_payloads: List[Dict[str, Any]] = []
        
        for ev in evaluations:
            turn_payloads.append({
                "turn_index": ev.get("turn_index", 0),
                "overall_score": ev.get("overall_score", 0),
                "brief": ev.get("brief", ""),
                "scores": ev.get("scores", {}),
                "nonverbal": ev.get("nonverbal_summary"),
            })
            
            scores = ev.get("scores", {})
            for axis, score in scores.items():
                if score is not None:
                    per_axis[axis].append(score)
        
        # 计算各维度平均分
        per_axis_avg: Dict[str, Optional[float]] = {}
        axis_brief_parts: List[str] = []
        for axis, values in per_axis.items():
            if values:
                avg = sum(values) / len(values)
                per_axis_avg[axis] = round(avg, 2)
                if avg < 3:
                    axis_brief_parts.append(f"{axis}得分偏低({avg:.1f}/5)")
            else:
                per_axis_avg[axis] = None
        
        # 计算总体平均分
        all_scores = [score for score_list in per_axis.values() for score in score_list]
        overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0.0
        overall_score = int(round((overall_avg / 5.0) * 100))
        
        # 生成总体反馈
        if axis_brief_parts:
            brief = "；".join(axis_brief_parts)
        else:
            brief = "整体表现均衡，未发现明显短板。"
        
        return {
            "overall_score": overall_score,
            "average_score": round(overall_avg, 2),
            "per_axis": per_axis_avg,
            "brief": brief,
            "turns": turn_payloads,
        }

