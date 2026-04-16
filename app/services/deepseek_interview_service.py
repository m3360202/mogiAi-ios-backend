"""
Interview Service
Handles interview question generation using OpenAI API (GPT-4o-mini)
支持流式和非流式生成
"""
import os
from typing import List, Dict, Optional, AsyncGenerator
from openai import AsyncOpenAI

class DeepseekInterviewService:
    """Generates interview questions using LLM (OpenAI/DeepSeek)"""
    
    def __init__(self):
        # 根据模型选择 API
        self.model = os.getenv("INTERVIEW_MODEL", "gpt-4o-mini")
        
        # 强制使用 OpenAI API
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[Interview] Warning: OPENAI_API_KEY not configured")
            self.client = None
        else:
            self.client = AsyncOpenAI(
                api_key=api_key,
                timeout=30.0,  # 30秒超时（VPN可能较慢）
            )
        print(f"[Interview] ✓ Initialized with OpenAI model: {self.model}")
    
    async def generate_first_question(self, role: str, system_message: Optional[str] = None, language: str = "ja") -> str:
        """Generate the first interview question (non-stream)"""
        if not system_message:
            system_message = f"あなたは専門的な{role}の面接官です。最初の面接質問を提案し、候補者に自己紹介を依頼してください。"
        
        print(f"[Interview] Role: {role}")
        print(f"[Interview] System message: {system_message[:100]}...")
        
        # 多语言指令
        instructions = {
            "ja": "面接を開始し、最初の面接質問をしてください。質問は簡潔で明確にし、100字以内に抑えてください。重要：回答は日本語のみで記述し、適切な句読点を使用してください。",
            "en": "Start the interview and ask the first question. Keep it concise and clear, within 100 words. IMPORTANT: Respond in ENGLISH only and use proper punctuation.",
            "zh": "请开始面试并提出第一个问题。问题要简洁明确，控制在100字以内。重要：请仅使用中文回答，并务必使用正确的标点符号。"
        }
        
        user_content = instructions.get(language, instructions["ja"])
        if language.startswith("zh"):
            user_content = instructions["zh"]
        elif language.startswith("en"):
            user_content = instructions["en"]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=150,  # 限制为150 tokens（约100字）
                temperature=0.7
            )
            question = response.choices[0].message.content.strip()
            print(f"[Interview] Generated first question: {question[:80]}...")
            return question
        except Exception as e:
            print(f"[Interview] Error generating first question: {e}")
            if language.startswith("en"):
                return "Hello. Please briefly introduce yourself and tell me about a project that best demonstrates your skills."
            elif language.startswith("zh"):
                return "您好。请简单自我介绍一下，并谈谈最能体现您能力的一个项目经历。"
            return "こんにちは。簡単に自己紹介をお願いします。また、あなたの能力を最もよく表すプロジェクト経験についてお聞かせください。"
    
    async def generate_first_question_stream(
        self, 
        role: str, 
        system_message: Optional[str] = None,
        language: str = "ja",
        framework_config: Optional[Dict[str, str]] = None,
        all_frameworks_summary: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成第一个面试问题"""
        if not system_message:
            system_message = f"あなたは専門的な{role}の面接官です。最初の面接質問を提案し、候補者に自己紹介を依頼してください。"
        
        # 注入框架约束（如果 system_message 中还没有 framework 列表）
        # 注意：现在 framework 列表已经在 start-stream 时注入到 system_message 中了
        # 这里只处理向后兼容的情况
        if framework_config and all_frameworks_summary:
            # 检查 system_message 中是否已经包含 framework 列表
            if "框架使用规则" not in system_message and "Framework Usage Rules" not in system_message and "フレームワーク使用ルール" not in system_message:
                # 让LLM根据上下文从框架列表中选择合适的框架
                if language.startswith("zh"):
                    system_message += f"\n\n【框架选择要求】\n请根据当前话题内容和面试目标，从以下框架列表中选择一个最适合提出第一个问题的框架。框架范围如下：\n\n{all_frameworks_summary}\n\n请按照你选择的框架的结构来设计第一个问题，但不要在问题中明确提到框架名称。\n\n重要：在问题文本的最后，添加一个标记来标识你使用的框架，格式为：[FRAMEWORK: 框架名称]，例如：[FRAMEWORK: STAR] 或 [FRAMEWORK: CAR]。这个标记不会显示给候选人，仅用于系统记录。"
                elif language.startswith("en"):
                    system_message += f"\n\n【Framework Selection Requirement】\nBased on the current topic and interview objectives, please select the most appropriate framework from the following list for asking the first question:\n\n{all_frameworks_summary}\n\nDesign your first question according to the structure of the framework you selected, but do NOT explicitly mention the framework name in your question.\n\nIMPORTANT: At the end of your question text, add a marker to identify the framework you used, in the format: [FRAMEWORK: FrameworkName], e.g., [FRAMEWORK: STAR] or [FRAMEWORK: CAR]. This marker will not be shown to the candidate, only for system recording."
                else:
                    system_message += f"\n\n【フレームワーク選択要件】\n現在のトピックと面接の目的に基づいて、最初の質問を出すために最も適切なフレームワークを以下のリストから選択してください：\n\n{all_frameworks_summary}\n\n選択したフレームワークの構造に従って最初の質問を設計してください。ただし、質問の中でフレームワーク名を明確に言及しないでください。\n\n重要：質問テキストの最後に、使用したフレームワークを識別するマーカーを追加してください。形式：[FRAMEWORK: フレームワーク名]、例：[FRAMEWORK: STAR] または [FRAMEWORK: CAR]。このマーカーは候補者には表示されず、システム記録のみに使用されます。"
                print(f"[Interview] (Stream) Framework selection mode: LLM will choose from available frameworks")
        elif framework_config:
            # 向后兼容：如果只有framework_config但没有all_frameworks_summary，使用旧逻辑
            method_name = framework_config.get("methodName")
            category = framework_config.get("category")
            if language.startswith("zh"):
                system_message += f"\n\n约束：请按照「{method_name}」框架（属于{category}类）的结构来设计问题，但不要在问题中明确提到框架名称。"
            elif language.startswith("en"):
                system_message += f"\n\nConstraint: Design your question according to the structure of the '{method_name}' framework (Category: {category}), but do NOT explicitly mention the framework name in your question."
            else:
                system_message += f"\n\n制約事項：質問を「{method_name}」フレームワーク（カテゴリ：{category}）の構造に従って設計してください。ただし、質問の中でフレームワーク名を明確に言及しないでください。"
            print(f"[Interview] (Stream) Framework constraint applied: {framework_config.get('methodName')}")
        
        print(f"[Interview] (Stream) 🌊 Starting stream generation...")
        print(f"[Interview] (Stream) Role: {role}, Model: {self.model}, Language: {language}")
        
        # 多语言指令
        instructions = {
            "ja": "面接を開始し、最初の面接質問をしてください。質問は簡潔で明確にし、100字以内に抑えてください。重要：回答は日本語のみで記述し、適切な句読点を使用してください。",
            "en": "Start the interview and ask the first question. Keep it concise and clear, within 100 words. IMPORTANT: Respond in ENGLISH only and use proper punctuation.",
            "zh": "请开始面试并提出第一个问题。问题要简洁明确，控制在100字以内。重要：请仅使用中文回答，并务必使用正确的标点符号。"
        }
        
        user_content = instructions.get(language, instructions["ja"])
        if language.startswith("zh"):
            user_content = instructions["zh"]
        elif language.startswith("en"):
            user_content = instructions["en"]
        
        try:
            print(f"[Interview] (Stream) 📡 Sending request to API...")
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=150,  # 限制为150 tokens（约100字）
                temperature=0.7,
                stream=True
            )
            
            print(f"[Interview] (Stream) ✅ Stream started, yielding chunks...")
            chunk_count = 0
            total_content = ""
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    chunk_count += 1
                    total_content += content
                    yield content
            
            print(f"[Interview] (Stream) 🏁 Stream completed! Total chunks: {chunk_count}, Total chars: {len(total_content)}")
            print(f"[Interview] (Stream) 📄 Full question: {total_content}")
                    
        except Exception as e:
            print(f"[Interview] Stream error: {e}")
            if language.startswith("en"):
                fallback = "Hello. Please briefly introduce yourself and tell me about a project that best demonstrates your skills."
            elif language.startswith("zh"):
                fallback = "您好。请简单自我介绍一下，并谈谈最能体现您能力的一个项目经历。"
            else:
                fallback = "こんにちは。簡単に自己紹介をお願いします。また、あなたの能力を最もよく表すプロジェクト経験についてお聞かせください。"
            for char in fallback:
                yield char
    
    async def generate_next_question(
        self, 
        conversation_history: List[Dict[str, str]],
        user_answer: str,
        role: str,
        system_message: Optional[str] = None,
        language: str = "ja"
    ) -> str:
        """Generate the next interview question based on conversation history"""
        if not system_message:
            system_message = f"あなたは専門的な{role}の面接官です。候補者の回答に基づいて、深い追及質問または次の関連質問を提出してください。"
        
        # 多语言指令
        instructions = {
            "ja": "候補者の回答に基づいて、次の質問をしてください。質問は簡潔で明確にし、150字以内に抑えてください。重要：回答に対するフィードバックやアドバイスは一切含めないでください。回答は日本語のみで記述し、適切な句読点を使用してください。",
            "en": "Based on the candidate's answer, ask the next question. Keep it concise and clear, within 100 words. IMPORTANT: Do NOT include any feedback or advice on the answer. Please respond in ENGLISH only and use proper punctuation.",
            "zh": "请根据候选人的回答，提出下一个问题。问题要简洁明确，控制在150字以内。重要：不要包含任何对回答的反馈或建议。请仅使用中文回答，并务必使用正确的标点符号。"
        }
        
        # 默认使用日语，如果找不到对应语言
        instruction = instructions.get(language, instructions["ja"])
        
        # 处理 zh-CN 等变体
        if language.startswith("zh"):
            instruction = instructions["zh"]
        elif language.startswith("en"):
            instruction = instructions["en"]
        
        messages = [{"role": "system", "content": system_message}]
        
        # Add conversation history
        for turn in conversation_history[-5:]:  # Last 5 turns for context
            if turn["role"] == "system":
                messages.append({"role": "assistant", "content": turn["content"]})
            else:
                messages.append({"role": "user", "content": turn["content"]})
        
        # Add current answer
        messages.append({"role": "user", "content": user_answer})
        messages.append({"role": "system", "content": instruction})
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200,  # 限制为200 tokens（约150字）
                temperature=0.7
            )
            question = response.choices[0].message.content.strip()
            print(f"[Interview] Generated next question: {question[:50]}...")
            return question
        except Exception as e:
            print(f"[Interview] Error generating next question: {e}")
            if language.startswith("en"):
                return "Could you tell me more about the biggest challenge you faced in this project?"
            elif language.startswith("zh"):
                return "关于在这个项目中遇到的最大挑战，能否请您再详细谈谈？"
            return "このプロジェクトで直面した最大の挑戦について、さらに詳しく教えてください。"
    
    async def generate_next_question_stream(
        self, 
        conversation_history: List[Dict[str, str]],
        user_answer: str,
        role: str,
        system_message: Optional[str] = None,
        language: str = "ja",
        framework_config: Optional[Dict[str, str]] = None,
        all_frameworks_summary: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成下一个面试问题"""
        import time
        call_start = time.time()
        
        if not system_message:
            system_message = f"あなたは専門的な{role}の面接官です。候補者の回答に基づいて、深い追及質問または次の関連質問を提出してください。"
        
        # 注入框架约束
        if framework_config and all_frameworks_summary:
            # 让LLM根据上下文从框架列表中选择合适的框架
            if language.startswith("zh"):
                system_message += f"\n\n【框架选择要求】\n请根据上一个问题和候选人的回答，以及当前话题内容，从以下框架列表中选择一个最适合提出下一个问题的框架。框架范围如下：\n\n{all_frameworks_summary}\n\n请按照你选择的框架的结构来设计下一个问题，但不要在问题中明确提到框架名称。\n\n重要：在问题文本的最后，添加一个标记来标识你使用的框架，格式为：[FRAMEWORK: 框架名称]，例如：[FRAMEWORK: STAR] 或 [FRAMEWORK: CAR]。这个标记不会显示给候选人，仅用于系统记录。"
            elif language.startswith("en"):
                system_message += f"\n\n【Framework Selection Requirement】\nBased on the previous question and candidate's answer, as well as the current topic, please select the most appropriate framework from the following list for asking the next question:\n\n{all_frameworks_summary}\n\nDesign your next question according to the structure of the framework you selected, but do NOT explicitly mention the framework name in your question.\n\nIMPORTANT: At the end of your question text, add a marker to identify the framework you used, in the format: [FRAMEWORK: FrameworkName], e.g., [FRAMEWORK: STAR] or [FRAMEWORK: CAR]. This marker will not be shown to the candidate, only for system recording."
            else:
                system_message += f"\n\n【フレームワーク選択要件】\n前の質問と候補者の回答、および現在のトピックに基づいて、次の質問を出すために最も適切なフレームワークを以下のリストから選択してください：\n\n{all_frameworks_summary}\n\n選択したフレームワークの構造に従って次の質問を設計してください。ただし、質問の中でフレームワーク名を明確に言及しないでください。\n\n重要：質問テキストの最後に、使用したフレームワークを識別するマーカーを追加してください。形式：[FRAMEWORK: フレームワーク名]、例：[FRAMEWORK: STAR] または [FRAMEWORK: CAR]。このマーカーは候補者には表示されず、システム記録のみに使用されます。"
            print(f"[Interview] (Stream) Framework selection mode: LLM will choose from available frameworks")
        elif framework_config:
            # 向后兼容：如果只有framework_config但没有all_frameworks_summary，使用旧逻辑
            method_name = framework_config.get("methodName")
            category = framework_config.get("category")
            if language.startswith("zh"):
                system_message += f"\n\n约束：请按照「{method_name}」框架（属于{category}类）的结构来设计下一个问题，但不要在问题中明确提到框架名称。"
            elif language.startswith("en"):
                system_message += f"\n\nConstraint: Design your next question according to the structure of the '{method_name}' framework (Category: {category}), but do NOT explicitly mention the framework name in your question."
            else:
                system_message += f"\n\n制約事項：次の質問を「{method_name}」フレームワーク（カテゴリ：{category}）の構造に従って設計してください。ただし、質問の中でフレームワーク名を明確に言及しないでください。"
            print(f"[Interview] (Stream) Framework constraint applied: {method_name}")
        
        # 多语言指令
        instructions = {
            "ja": "候補者の回答に基づいて、次の質問をしてください。質問は簡潔で明確にし、100字以内に抑えてください。重要：回答に対するフィードバックやアドバイスは一切含めないでください。回答は日本語のみで記述し、適切な句読点を使用してください。",
            "en": "Based on the candidate's answer, ask the next question. Keep it concise and clear, within 80 words. IMPORTANT: Do NOT include any feedback or advice on the answer. Please respond in ENGLISH only and use proper punctuation.",
            "zh": "请根据候选人的回答，提出下一个问题。问题要简洁明确，控制在100字以内。重要：不要包含任何对回答的反馈或建议。请仅使用中文回答，并务必使用正确的标点符号。"
        }
        
        # 默认使用日语，如果找不到对应语言
        instruction = instructions.get(language, instructions["ja"])
        
        # 处理 zh-CN 等变体
        if language.startswith("zh"):
            instruction = instructions["zh"]
        elif language.startswith("en"):
            instruction = instructions["en"]
            
        # ⚡ 优化：将instruction整合到system message中，避免重复的system role
        system_message_with_instruction = f"{system_message}\n\n{instruction}"
        
        messages = [{"role": "system", "content": system_message_with_instruction}]
        
        # Add conversation history (只取最后3轮，减少token消耗)
        for turn in conversation_history[-3:]:  # Last 3 turns for context
            if turn["role"] == "system":
                messages.append({"role": "assistant", "content": turn["content"]})
            else:
                messages.append({"role": "user", "content": turn["content"]})
        
        # Add current answer
        messages.append({"role": "user", "content": user_answer})
        
        print(f"[Interview] (Stream) 📊 Total messages: {len(messages)}, Total chars: {sum(len(m['content']) for m in messages)}")
        
        try:
            print(f"[Interview] (Stream) 📡 API call started at {time.time():.3f}")
            import asyncio
            
            # ⚡ 创建API调用任务
            async def api_call_with_timeout():
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=150,  # 减少到150 tokens（约100字）
                    temperature=0.7,
                    stream=True
                )
                
                first_chunk = True
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        if first_chunk:
                            ttfb = (time.time() - call_start) * 1000
                            print(f"[Interview] (Stream) ⚡ API TTFB: {ttfb:.1f}ms")
                            first_chunk = False
                        content = chunk.choices[0].delta.content
                        yield content
            
            # 异步迭代并处理超时
            async for content in api_call_with_timeout():
                yield content
                    
        except asyncio.TimeoutError:
            elapsed = (time.time() - call_start) * 1000
            print(f"[Interview] ⚠️ API timeout after {elapsed:.1f}ms, using fallback")
            if language.startswith("en"):
                fallback = "Could you tell me more about the biggest challenge you faced in this project?"
            elif language.startswith("zh"):
                fallback = "关于在这个项目中遇到的最大挑战，能否请您再详细谈谈？"
            else:
                fallback = "このプロジェクトで直面した最大の挑戦について、さらに詳しく教えてください。"
            for char in fallback:
                yield char
        except Exception as e:
            elapsed = (time.time() - call_start) * 1000
            print(f"[Interview] ❌ Stream error after {elapsed:.1f}ms: {e}")
            if language.startswith("en"):
                fallback = "Could you tell me more about the biggest challenge you faced in this project?"
            elif language.startswith("zh"):
                fallback = "关于在这个项目中遇到的最大挑战，能否请您再详细谈谈？"
            else:
                fallback = "このプロジェクトで直面した最大の挑戦について、さらに詳しく教えてください。"
            for char in fallback:
                yield char

