"""
流式面试评估适配器

将标准的 EvaluationAPI 输出转换为流式接口需要的简化格式。
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.evaluation.business.entities import EvaluationRecord
from app.services.evaluation.business.value_objects import RawDialogInfo, DialogMessage
from app.services.evaluation.business.enums import MessageRole, SuperMetricType
from app.services.evaluation.public import EvaluationAPI


class StreamEvaluationAdapter:
    """适配器：将完整评估结果转换为流式接口的简化格式"""
    
    def __init__(self, evaluation_api: EvaluationAPI):
        self.evaluation_api = evaluation_api
    
    async def evaluate_turn(
        self,
        transcript: str,
        turn_index: int,
        question: Optional[str] = None,
        nonverbal_snapshot: Optional[Dict[str, Any]] = None,
        session_id: str = "stream",
    ) -> Dict[str, Any]:
        """
        评估单轮对话
        
        Args:
            transcript: 用户回答文本
            turn_index: 回合索引（从0开始）
            question: 面试官问题
            nonverbal_snapshot: 非语言表现快照
            session_id: 会话ID
            
        Returns:
            包含评分和反馈的字典
        """
        # 构建对话消息
        messages: List[DialogMessage] = []
        now = datetime.utcnow()
        
        if question:
            messages.append(DialogMessage(
                section_id=f"{session_id}_turn_{turn_index}",
                role=MessageRole.INTERVIEWER,
                content=question,
                start_time=now,
                end_time=now,
            ))
        
        messages.append(DialogMessage(
            section_id=f"{session_id}_turn_{turn_index}",
            role=MessageRole.CANDIDATE,
            content=transcript,
            start_time=now,
            end_time=now,
        ))
        
        # 创建原始对话信息
        raw_dialog = RawDialogInfo(
            dialog_id=f"{session_id}_turn_{turn_index}",
            messages=messages,
        )
        
        # 调用评估API
        evaluation_record: EvaluationRecord = await self.evaluation_api.evaluate(raw_dialog)
        
        # 转换为简化格式
        return self._convert_to_stream_format(
            evaluation_record=evaluation_record,
            turn_index=turn_index,
            transcript=transcript,
            question=question,
            nonverbal_snapshot=nonverbal_snapshot,
        )
    
    def _convert_to_stream_format(
        self,
        evaluation_record: EvaluationRecord,
        turn_index: int,
        transcript: str,
        question: Optional[str],
        nonverbal_snapshot: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """将 EvaluationRecord 转换为流式格式"""
        
        # 提取各维度分数（映射到6轴格式）
        scores = {}
        issues = []
        
        for super_metric in evaluation_record.super_metrics:
            metric_type = super_metric.metadata.super_metric_type
            numeric_score = super_metric.score.numeric_score
            
            # 转换 0-100 分数为 1-5 分
            normalized_score = int(round((numeric_score / 100.0) * 5))
            normalized_score = max(1, min(5, normalized_score))  # 确保在1-5范围内
            
            # 映射到6轴格式
            if metric_type == SuperMetricType.CLARITY:
                scores["clarity"] = normalized_score
            elif metric_type == SuperMetricType.EVIDENCE:
                scores["evidence"] = normalized_score
            elif metric_type == SuperMetricType.VERBAL_PERFORMANCE:
                scores["delivery"] = normalized_score
            elif metric_type == SuperMetricType.ENGAGEMENT:
                scores["engagement"] = normalized_score
            elif metric_type == SuperMetricType.IMPACT:
                scores["impact"] = normalized_score
            
            # 提取反馈作为问题点
            if super_metric.feedback and numeric_score < 60:
                issues.append(f"{metric_type.value}: {super_metric.feedback}")
        
        # 填充缺失的维度
        for axis in ["clarity", "evidence", "delivery", "engagement", "politeness", "impact"]:
            if axis not in scores:
                scores[axis] = None
        
        # 计算平均分
        available_scores = [s for s in scores.values() if s is not None]
        average = sum(available_scores) / len(available_scores) if available_scores else 0.0
        
        # 计算总分（0-100）
        overall_score = int(round(evaluation_record.overall_score.numeric_score))
        
        # 生成简要反馈
        brief = self._generate_brief(scores, issues, nonverbal_snapshot)
        
        # 非语言表现摘要
        nonverbal_summary = self._summarize_nonverbal(nonverbal_snapshot)
        
        return {
            "turn_index": turn_index,
            "transcript": transcript,
            "question": question,
            "scores": scores,
            "average": average,
            "overall_score": overall_score,
            "brief": brief,
            "issues": issues[:4],  # 最多4个问题点
            "nonverbal_summary": nonverbal_summary,
        }
    
    def _generate_brief(
        self,
        scores: Dict[str, Optional[int]],
        issues: List[str],
        nonverbal: Optional[Dict[str, Any]],
    ) -> str:
        """生成简要反馈"""
        parts: List[str] = []
        
        # 找出低分维度
        low_axes = [axis for axis, score in scores.items() if score is not None and score <= 2]
        if low_axes:
            parts.append(f"需要重点提升: {', '.join(low_axes)}")
        
        # 添加第一个问题点
        if issues:
            parts.append(issues[0].split(": ", 1)[-1] if ": " in issues[0] else issues[0])
        
        # 添加非语言反馈
        if nonverbal:
            nv_text = self._brief_nonverbal(nonverbal)
            if nv_text:
                parts.append(nv_text)
        
        if not parts:
            return "整体表现良好，继续保持回答结构与细节。"
        
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

