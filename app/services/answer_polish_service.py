"""
Answer Polish Service
Use OpenAI (gpt-4o-mini) to polish interview answers with a given framework (md file).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app.core.llm_factory import llm_factory
from app.services.interview_framework_service import interview_framework_service


class AnswerPolishService:
    def __init__(self) -> None:
        self.client, self.model = llm_factory.get_non_visual_client()
        print(f"[AnswerPolish] ✓ Initialized with model: {self.model}")

    async def polish_answers(
        self,
        *,
        framework_md: str,
        qas: List[Dict[str, Any]],
        language: Optional[str] = None,
        interview_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """
        Input qas: [{question: str, answer: str, framework: Optional[Dict]}]
        Output items: [{question, original_answer, polished_answer}]
        """
        if not qas:
            return []

        ctx = interview_context or {}
        ctx_json = json.dumps(ctx, ensure_ascii=False)
        qas_json = json.dumps(qas, ensure_ascii=False)

        # Build per-question framework instructions
        framework_instructions = []
        for i, qa in enumerate(qas):
            qa_framework = qa.get("framework")
            if qa_framework and isinstance(qa_framework, dict):
                method_name = qa_framework.get("methodName", "")
                description = qa_framework.get("description", "")
                category = qa_framework.get("category", "")
                best_for = qa_framework.get("bestFor", "")
                
                # Get full framework details from service
                full_framework = interview_framework_service.get_framework_by_name(method_name)
                if full_framework:
                    description = full_framework.get("description", description)
                    best_for = full_framework.get("bestFor", best_for)
                
                framework_instructions.append(
                    f"Question {i + 1}: MUST use the '{method_name}' framework to structure the polished answer.\n"
                    f"  - Framework: {method_name}\n"
                    f"  - Category: {category}\n"
                    f"  - Description: {description}\n"
                    f"  - Best for: {best_for}\n"
                    f"  - Instruction: Structure the polished answer according to the {method_name} framework methodology. "
                    f"Ensure the answer follows the framework's structure and principles."
                )
            else:
                # No framework specified for this question - use default
                framework_instructions.append(
                    f"Question {i + 1}: Use the default framework provided below (no specific framework was used during the interview for this question)."
                )
        
        framework_instructions_text = "\n".join(framework_instructions)
        
        system_prompt = (
            "You are an expert interview coach and editor.\n"
            "Task: For each Q/A, rewrite ONLY the candidate's answer into a 90-point interview answer.\n"
            "Target: make it score ~90/100 on typical interview rubrics (clarity, evidence/logic, impact, engagement, verbal/visual professionalism).\n"
            "Hard constraints:\n"
            "- Keep the original meaning and facts. Do NOT invent achievements, numbers, companies, degrees, or experiences.\n"
            "- Improve clarity, structure, concision, and professionalism.\n"
            "- Length Constraint: The polished answer MUST be at least 300 words (or characters for Chinese/Japanese) to ensure sufficient detail and depth.\n"
            "- If the original answer is empty/very short, produce a strong but still truthful answer using only generic, safe phrasing.\n"
            "- Framework Usage: Follow the framework instructions below for each question. If a question specifies a framework, you MUST structure the answer according to that framework's methodology.\n"
            "- Language: Respond in the same language as the original answer. If unclear, follow `language` or the question language.\n"
            "- Output MUST be valid JSON ONLY (no markdown, no extra text).\n"
        )

        user_prompt = (
            "INTERVIEW CONTEXT (json):\n"
            f"{ctx_json}\n\n"
            "FRAMEWORK INSTRUCTIONS (per question):\n"
            f"{framework_instructions_text}\n\n"
            "DEFAULT FRAMEWORK (markdown) - Use only if no specific framework is specified for a question:\n"
            f"{framework_md}\n\n"
            "QAs (json):\n"
            f"{qas_json}\n\n"
            "Return a JSON array. Each item:\n"
            "{\n"
            '  "question": string,\n'
            '  "original_answer": string,\n'
            '  "polished_answer": string\n'
            "}\n"
            "\n"
            "CRITICAL JSON FORMAT REQUIREMENTS:\n"
            "- The output MUST be valid JSON only (no markdown, no code blocks, no extra text)\n"
            "- Every field MUST have a value (even if empty string)\n"
            "- Every string value MUST be properly quoted with double quotes\n"
            "- The polished_answer field MUST be complete and properly closed\n"
            "- Do NOT truncate the JSON output - ensure all fields are complete\n"
            "\n"
            "IMPORTANT: For each question, check if it has a 'framework' field. If it does, structure the polished answer according to that framework's methodology. "
            "If no framework is specified, use the default framework provided above.\n"
        )

        if language:
            user_prompt += f'\nPreferred language hint (if needed): "{language}"\n'

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=4000,  # 增加token限制，确保能生成完整的润色内容
            # 注意：不使用 response_format，因为我们需要JSON数组而不是对象
        )

        content = (resp.choices[0].message.content or "").strip()
        
        # 🎯 尝试修复不完整的JSON
        def try_fix_json(text: str) -> str:
            """尝试修复不完整的JSON"""
            # 移除可能的markdown代码块标记
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            # 如果以 [ 开头但未闭合，尝试修复
            if text.startswith("[") and not text.endswith("]"):
                # 查找最后一个完整的对象
                last_complete_obj = text.rfind("}")
                if last_complete_obj > 0:
                    # 检查最后一个对象是否完整
                    partial = text[:last_complete_obj + 1]
                    
                    # 检查是否有未完成的字段（如 "polished_answer" 后面没有值）
                    import re
                    # 修复模式1: "polished_answer" 后面直接是换行、空格或什么都没有，然后就是 } 或 ]
                    # 匹配 "polished_answer": 后面可能没有值或值不完整的情况
                    pattern1 = r'"polished_answer"\s*:\s*([^,}\]]*?)(?=[,}\]])'
                    def fix_polished_value(m):
                        val = m.group(1).strip()
                        # 如果值为空、只有空白、或引号未闭合
                        if not val or val.isspace() or (val.startswith('"') and not val.endswith('"')):
                            return '"polished_answer": ""'
                        return m.group(0)
                    partial = re.sub(pattern1, fix_polished_value, partial)
                    
                    # 修复模式2: "polished_answer" 后面没有冒号或值，直接是 } 或换行
                    pattern2 = r'"polished_answer"\s*(?=[,}\]])'
                    partial = re.sub(pattern2, '"polished_answer": ""', partial)
                    
                    # 如果最后一个对象不完整（缺少闭合引号或值），尝试修复
                    if not partial.rstrip().endswith('}'):
                        # 移除末尾不完整的部分，补全对象
                        # 找到最后一个完整的字段
                        last_comma = partial.rfind(',')
                        if last_comma > 0:
                            # 检查最后一个字段是否完整
                            after_comma = partial[last_comma + 1:].strip()
                            if after_comma.startswith('"polished_answer"'):
                                # 如果polished_answer字段不完整，补全
                                if ': ' not in after_comma or (': ' in after_comma and not after_comma.split(': ', 1)[1].strip().endswith('"')):
                                    partial = partial[:last_comma + 1] + '"polished_answer": ""}'
                                else:
                                    # 字段存在但可能值不完整，尝试补全
                                    if not after_comma.rstrip().endswith('"'):
                                        partial = partial[:last_comma + 1] + '"polished_answer": ""}'
                            else:
                                # 其他字段不完整，直接闭合
                                partial = partial[:last_comma] + '}'
                        else:
                            # 没有逗号，可能是第一个字段，直接闭合
                            if not partial.rstrip().endswith('}'):
                                partial = partial.rstrip().rstrip('}') + '}'
                    
                    text = partial + "]"
            
            return text
        
        # 尝试解析JSON
        parsed = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            # 尝试修复JSON
            fixed_content = try_fix_json(content)
            try:
                parsed = json.loads(fixed_content)
                print(f"[AnswerPolish] ✅ Fixed incomplete JSON")
            except json.JSONDecodeError as e2:
                # 如果修复失败，尝试提取部分数据
                print(f"[AnswerPolish] ⚠️ JSON parse failed, attempting partial recovery...")
                # 尝试使用正则表达式提取部分数据
                import re
                items = []
                # 匹配每个对象
                pattern = r'\{[^{}]*"question"[^{}]*"original_answer"[^{}]*"polished_answer"[^{}]*\}'
                matches = re.findall(pattern, content, re.DOTALL)
                for match in matches:
                    try:
                        # 尝试修复单个对象
                        obj_str = match
                        if '"polished_answer"' in obj_str and ': ' in obj_str[obj_str.find('"polished_answer"'):]:
                            # 如果polished_answer不完整，补全为空字符串
                            if not obj_str.rstrip().endswith('"'):
                                obj_str = obj_str.rstrip().rstrip(',') + ': ""}'
                        item = json.loads(obj_str)
                        items.append(item)
                    except:
                        continue
                
                if items:
                    parsed = items
                    print(f"[AnswerPolish] ✅ Recovered {len(items)} items from partial JSON")
                else:
                    # Use the original JSONDecodeError from the first parse attempt (e) for context
                    raise ValueError(f"Failed to parse LLM JSON output: {e}. Raw: {content[:500]}...")
        
        if not isinstance(parsed, list):
            # 如果返回的是对象而不是数组，尝试转换
            if isinstance(parsed, dict):
                if "items" in parsed:
                    parsed = parsed["items"]
                elif "results" in parsed:
                    parsed = parsed["results"]
                else:
                    # 尝试将单个对象转换为数组
                    parsed = [parsed]
            else:
                raise ValueError("LLM output is not a list or object")
        
        out: List[Dict[str, Any]] = []
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            q = str(item.get("question", "") or "")
            oa = str(item.get("original_answer", "") or "")
            pa = str(item.get("polished_answer", "") or "")
            
            # 如果polished_answer为空，使用original_answer作为fallback
            if not pa.strip() and oa.strip():
                pa = oa
                print(f"[AnswerPolish] ⚠️ Item {i+1}: polished_answer is empty, using original_answer as fallback")
            
            # Include framework info from original qas if available
            result_item: Dict[str, Any] = {
                "question": q,
                "original_answer": oa,
                "polished_answer": pa
            }
            
            # Add framework info if it exists in the original qas
            if i < len(qas):
                original_qa = qas[i]
                if original_qa.get("framework"):
                    result_item["framework"] = original_qa["framework"]
            
            out.append(result_item)
        
        if not out:
            raise ValueError(f"No valid items parsed from LLM output. Raw: {content[:500]}...")
        
        return out


