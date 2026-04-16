"""
AI服务（对话生成和评估）
"""
from typing import Dict, Any
import openai
from app.core.config import settings


class AIService:
    """AI服务"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def generate_interview_response(self, user_message: str, context: Dict) -> str:
        """生成面试对话回复"""
        mode = context.get("mode", "advanced")
        scenario = context.get("scenario", "")
        company_name = context.get("company_name", "")
        position = context.get("position", "")
        conversation_history = context.get("conversation_history", {})
        current_round = len(conversation_history.get("messages", [])) // 2 if conversation_history else 0
        
        # 根据轮次和模式确定最大轮次
        if mode == "basic":
            max_rounds = 10
        elif mode == "advanced":
            max_rounds = 18  # 15-20轮，默认18轮
        else:  # corporate
            max_rounds = 12
        
        # 检查是否应该结束面试
        if current_round >= max_rounds - 1:
            if mode == "basic":
                return "今回の練習面接はこれで終了です。ご参加いただきありがとうございました。結果画面で詳細な評価をご確認ください。"
            else:
                return "今回の面接はこれで終了です。最後に、弊社について何かご質問はありますか？"
        
        # 检查用户回答质量，决定是否提前结束
        user_answer_quality = self._assess_answer_quality(user_message)
        if user_answer_quality < 30 and current_round > 3:  # 表现很差且已经进行了几轮
            if mode == "basic":
                return "今回の練習面接はこれで終了です。ご参加いただきありがとうございました。結果画面で詳細な評価をご確認ください。"
            else:
                return "今回の面接はこれで終了です。最後に、弊社について何かご質問はありますか？"
        
        # 构建更简洁的系统提示词，减少评论和填充
        if mode == "advanced":
            system_prompt = f"""
            あなたは日本語の面接官です。以下のルールに従ってください：
            
            1. 簡潔で具体的な質問のみをしてください
            2. 評価やコメントは含めないでください
            3. 自然な会話の流れを保ってください
            4. 質問は1つだけにしてください
            
            現在のシナリオ: {scenario}
            現在の質問ラウンド: {current_round + 1}/{max_rounds}
            
            応募者の回答: {user_message}
            """
        elif mode == "corporate":
            system_prompt = f"""
            あなたは{company_name}の{position}の面接官です。以下のルールに従ってください：
            
            1. 簡潔で具体的な質問のみをしてください
            2. 評価やコメントは含めないでください
            3. 会社の価値観に基づいた質問をしてください
            4. 質問は1つだけにしてください
            
            現在の質問ラウンド: {current_round + 1}/{max_rounds}
            
            応募者の回答: {user_message}
            """
        else:  # basic mode
            system_prompt = f"""
            あなたは日本語の面接官です。以下のルールに従ってください：
            
            1. 簡潔で具体的な質問のみをしてください
            2. 評価やコメントは含めないでください
            3. 基本的な面接スキルを評価する質問をしてください
            4. 質問は1つだけにしてください
            
            現在の質問ラウンド: {current_round + 1}/{max_rounds}
            
            応募者の回答: {user_message}
            """
        
        # 根据用户回答质量添加适当的提示
        if user_answer_quality < 50 and current_round > 0:
            system_prompt += "注意: 応募者の回答が簡潔すぎるか不十分です。もう少し詳しく説明を求める質問をしてください。"
        
        try:
            # 调用GPT-4o生成回复
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.5,  # 降低温度以获得更一致的回复
                max_tokens=200     # 减少token数量，保持简洁
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            # 降级回复 - 更简洁的默认回复
            return "もう少し詳しく教えていただけますか？"
    
    def _assess_answer_quality(self, answer: str) -> float:
        """评估用户回答质量（0-100分）"""
        if not answer or len(answer.strip()) == 0:
            return 0
        
        # 简单的质量评估规则
        score = 50  # 基础分
        
        # 长度加分（适中的长度）
        length = len(answer)
        if 50 <= length <= 300:  # 50-300字符为理想长度
            score += 20
        elif length > 50:  # 超过50字符但不太长
            score += 10
        elif length > 20:  # 超过20字符
            score += 5
        
        # 内容质量检查
        if "。" in answer or "、" in answer:  # 有标点符号
            score += 10
        
        if "例" in answer or "経験" in answer or "具体" in answer:  # 包含具体内容
            score += 15
        
        if "思います" in answer or "考えます" in answer:  # 包含个人观点
            score += 10
        
        return min(score, 100)
    
    async def evaluate_interview(self, transcript: str, mode: str, conversation_history: Dict) -> Dict[str, Any]:
        """评估面试表现"""
        # 构建评估提示词
        evaluation_prompt = f"""
        以下の日本語面試の回答を専門的に評価してください。
        
        面接モード: {mode}
        回答内容: {transcript}
        
        以下の6つの観点から0-100点で評価し、JSONフォーマットで返してください：
        1. 理解清晰度 (clarity): 質問の意図を正確に理解しているか
        2. 証拠具体性 (evidence): 具体的な事例やデータで支持しているか
        3. 表達伝達力 (expression): 表現が明確で流暢か
        4. 互動参与度 (engagement): 積極的なコミュニケーション態度を示しているか
        5. 礼仪態度 (etiquette): 言葉遣いが丁寧で適切か
        6. 印象影響力 (impression): 全体的な印象が良いか
        
        また、詳細なフィードバックと改善提案も提供してください。
        """
        
        try:
            response = self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "あなたは日本の面接評価の専門家です。"},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            # 解析AI返回的评估结果
            # 这里简化处理，实际应该解析JSON
            return {
                "scores": {
                    "clarity": 75.0,
                    "evidence": 70.0,
                    "expression": 80.0,
                    "engagement": 78.0,
                    "etiquette": 85.0,
                    "impression": 77.0,
                    "overall": 77.5
                },
                "feedback": response.choices[0].message.content,
                "suggestions": {
                    "items": [
                        "より具体的な事例を挙げることをお勧めします",
                        "結論を明確に述べることで、より説得力が増します"
                    ]
                },
                "strengths": {
                    "items": ["礼儀正しい言葉遣い", "論理的な構成"]
                },
                "weaknesses": {
                    "items": ["具体例が不足", "声の抑揚が少ない"]
                },
                "audio_features": {},
                "radar_chart_data": {
                    "dimensions": ["理解清晰度", "証拠具体性", "表達伝達力", "互動参与度", "礼仪態度", "印象影響力"],
                    "scores": [75.0, 70.0, 80.0, 78.0, 85.0, 77.0]
                }
            }
        
        except Exception as e:
            # 使用规则基础评估作为降级方案
            return self._rule_based_evaluation(transcript)
    
    def _rule_based_evaluation(self, transcript: str) -> Dict[str, Any]:
        """规则基础评估（降级方案）"""
        # 简单的规则评估
        word_count = len(transcript) if transcript else 0
        
        base_score = min(50 + word_count / 10, 85)
        
        return {
            "scores": {
                "clarity": base_score,
                "evidence": base_score - 5,
                "expression": base_score,
                "engagement": base_score,
                "etiquette": base_score + 5,
                "impression": base_score,
                "overall": base_score
            },
            "feedback": "基本的な評価が完了しました。",
            "suggestions": {"items": ["より詳細な分析のため、もう一度評価を実行してください。"]},
            "strengths": {"items": []},
            "weaknesses": {"items": []},
            "audio_features": {},
            "radar_chart_data": {
                "dimensions": ["理解清晰度", "証拠具体性", "表達伝達力", "互動参与度", "礼仪態度", "印象影響力"],
                "scores": [base_score] * 6
            }
        }

