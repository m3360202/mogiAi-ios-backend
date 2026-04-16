"""
Generate interview parameters using OpenAI API (GPT-4o-mini)
"""
import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

router = APIRouter()

# SDS Framework Instructions for all interview modes
SDS_INSTRUCTIONS = """
你是一名面试问答结构分析师，请根据 SDS 法（Summary → Details → Summary）的定义，对面试者提供的发言进行结构判断。

🎯 SDS 原则定义（供判断使用）
根据 SDS 法，优秀的自我介绍或求职回答应包含三个部分：
1. Summary（开头概述）：简洁地提供核心信息（例如姓名、学校、专业、主题概要）
2. Details（中段详细说明）：在概述的基础上展开内容（包含学习内容、校外活动、经验、背景故事等），不需冗长，但必须紧扣概述内容
3. Summary（结尾总结）：回到主题，做简短收束（可以是问候、期待、态度或观点收束），应让听者清楚发言的重点

📘 判断标准
请根据发言内容，逐项判断以下内容：
- 是否存在开头 Summary：是否在最前面清楚交代身份 / 核心信息 / 主旨？
- 是否存在 Details（中段具体内容）：是否在概述后进行与主题一致、逻辑相关的展开？是否有条理、不冗长？
- 是否存在结尾 Summary：是否有简短收束，表达态度或再次回到主旨？
- 整体结构是否符合 SDS 流程：顺序是否为 Summary → Details → Summary？是否有缺失、颠倒或混乱？
- 整体表达是否简洁聚焦（符合 SDS 精神）

📊 输出格式
请按以下格式输出结果：
【SDS 判断结果】
- 开头 Summary：是否存在？理由？
- Details：是否符合？理由？
- 结尾 Summary：是否存在？理由？
- 顺序是否正确？
- 是否整体符合 SDS？（是 / 否）

【结构分析】
- 发言的结构拆解（标出各部分）

【改进建议】
- 若不符合 SDS，请给出结构调整建议
- 若符合，也提出可进一步优化的方向

请保持yoodli的第二人称评测语气（"你..."），语气要鼓励且富有建设性。
"""

class GenerateJDRequest(BaseModel):
    company_name: str
    position: str
    language: Optional[str] = "zh"

@router.post("/generate-jd")
async def generate_job_description(request: GenerateJDRequest):
    """
    Generate a realistic job description based on company and position
    """
    print(f"[GenerateJD] Company: {request.company_name}, Position: {request.position}")
    
    try:
        # 1. 构造 Prompt
        lang_instruction = ""
        if request.language.startswith("zh"):
            lang_instruction = "请使用中文回答。"
        elif request.language.startswith("en"):
            lang_instruction = "Please respond in English."
        else:
            lang_instruction = "日本語で回答してください。"
            
        prompt = f"""
你是一名专业的人力资源专家。请根据以下信息，为目标企业生成一份真实、专业的岗位需求描述（Job Description）。

**企业信息**：{request.company_name}
**招聘岗位**：{request.position}

**生成要求**：
1. **真实性**：请基于你对该企业（如业务领域、企业文化、技术栈/业务模式）的了解来编写。如果企业知名，请尽可能贴近其真实风格。
2. **长度限制**：控制在200-250字左右（或英文150-200词）。不要过长，但要包含关键信息。
3. **内容结构**：
   - **岗位职责**（3-4点）：该岗位在目标企业可能的核心工作内容。
   - **任职要求**（3-4点）：硬性技能、软技能、经验要求等。
4. **格式**：分点列出，条理清晰。直接输出JD内容，不要包含"好的，这是JD"等客套话。

{lang_instruction}
"""

        # 2. 调用 LLM
        model = os.getenv("INTERVIEW_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[GenerateJD] Warning: OPENAI_API_KEY not configured")
            
        client = AsyncOpenAI(api_key=api_key, timeout=30.0)
            
        print(f"[GenerateJD] Calling LLM API with model: {model}...")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional HR expert."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        jd_text = response.choices[0].message.content.strip()
        print(f"[GenerateJD] LLM response length: {len(jd_text)}")
        
        return JSONResponse({
            "job_description": jd_text
        })

    except Exception as e:
        print(f"[GenerateJD] Error: {e}")
        # Fallback
        return JSONResponse({
            "job_description": f"岗位：{request.position}\n企业：{request.company_name}\n\n该岗位负责相关业务的核心开发与维护工作，要求具备扎实的专业基础和良好的团队协作能力。"
        })

class GenerateParamsRequest(BaseModel):
    interview_mode: str  # 'real' or 'practice'
    difficulty: str      # 'basic' or 'advanced'
    position: str        # '销售', '后端开発', etc.
    company_name: Optional[str] = None
    interviewer_style: Optional[str] = None
    job_description: Optional[str] = None
    language: Optional[str] = "zh"

@router.post("/generate-interview-params")
async def generate_interview_params(request: GenerateParamsRequest):
    """
    Generate role and system_message based on interview mode, difficulty, position, company, and style
    """
    print(f"[GenerateParams] Interview Mode: {request.interview_mode}")
    print(f"[GenerateParams] Difficulty: {request.difficulty}")
    print(f"[GenerateParams] Position: {request.position}")
    print(f"[GenerateParams] Company: {request.company_name}")
    print(f"[GenerateParams] Style: {request.interviewer_style}")
    print(f"[GenerateParams] Language: {request.language}")
    
    if request.job_description:
        print(f"[GenerateParams] Using provided Job Description ({len(request.job_description)} chars)")
    
    try:
        # Determine language for prompt
        is_en = request.language and request.language.startswith("en")
        is_ja = request.language and request.language.startswith("ja")
        
        # 1. 构造 Prompt
        if is_en:
            company_context = f"Company: {request.company_name}" if request.company_name else "Company: Unspecified (General Interview)"
            style_context = f"Interviewer Style: {request.interviewer_style}" if request.interviewer_style else "Interviewer Style: Professional, Objective"
            
            mode_desc = {
                'real': 'Real Interview Mode: Simulates a real corporate interview scenario with practical, strict questions to assess actual ability.',
                'practice': 'Practice Mode: Helps candidates practice interview skills with progressive questions and guidance.'
            }.get(request.interview_mode, 'Practice Mode')
            
            difficulty_desc = {
                'basic': 'Basic Level: Simple questions suitable for beginners.',
                'advanced': 'Advanced Level: In-depth, complex questions to assess deep understanding and practical experience.'
            }.get(request.difficulty, 'Basic Level')
            
            jd_context = ""
            if request.job_description:
                jd_context = f"\n**Target Job Description (Reference)**:\n{request.job_description}\n"
                
            prompt = f"""
Please generate appropriate "Interviewer Role Name" and "System Prompt" for the following interview scenario:

**Interview Scenario**:
{jd_context}
- {company_context}
- Position: {request.position}
- {style_context}
- Mode: {mode_desc}
- Difficulty: {difficulty_desc}

**Task Requirements**:
1. **Role Name (role)**: Concise and clear, e.g., "Interviewer-[Company]-[Position]" or "Interviewer-[Position]".
2. **System Prompt (system_message)**:
   - Must include a **Brief Job Description** derived from the context {'(refer to provided JD)' if request.job_description else ', describing core responsibilities for this role at the target company'}.
   - Set the interviewer's persona (matching the specified style).
   - Clarify the focus of the assessment.
   - Emphasize the interview flow: Start with a brief self-introduction, then ask questions based on the resume or job requirements.
   - **Important**: If a company name is provided, customize the question direction based on the company's characteristics (culture, domain).
   - **Language**: The system message must be in ENGLISH.

**Return JSON Format** (Do not use Markdown code blocks):
{{
  "role": "...",
  "system_message": "..."
}}
"""
        elif is_ja:
            company_context = f"企業：{request.company_name}" if request.company_name else "企業：未指定（一般面接）"
            style_context = f"面接官のスタイル：{request.interviewer_style}" if request.interviewer_style else "面接官のスタイル：プロフェッショナル、客観的"
            
            mode_desc = {
                'real': 'リアル面接モード：実際の企業面接をシミュレートし、実用的で厳格な質問で能力を評価します',
                'practice': '練習モード：面接スキルを練習するため、段階的な質問とガイダンスを提供します'
            }.get(request.interview_mode, '練習モード')
            
            difficulty_desc = {
                'basic': '基礎レベル：初心者向けの基本的な質問',
                'advanced': '応用レベル：深い理解と実務経験を問う複雑な質問'
            }.get(request.difficulty, '基礎レベル')
            
            jd_context = ""
            if request.job_description:
                jd_context = f"\n**ターゲット求人票（参考）**：\n{request.job_description}\n"
                
            prompt = f"""
以下の面接シナリオに適した「面接官の役割名」と「システムプロンプト」を生成してください：

**面接シナリオ**：
{jd_context}
- {company_context}
- 職種：{request.position}
- {style_context}
- モード：{mode_desc}
- 難易度：{difficulty_desc}

**タスク要件**：
1. **役割名（role）**：簡潔に、例：「面接官-[企業名]-[職種]」または「面接官-[職種]」。
2. **システムプロンプト（system_message）**：
   - コンテキストに基づいた**簡易な職務記述書（Job Description）**を含めてください{'（提供されたJDを参照）' if request.job_description else '（対象企業での主要な責任を説明）'}。
   - 面接官のペルソナを設定してください（指定されたスタイルに合わせる）。
   - 評価の重点を明確にしてください。
   - 面接の流れを強調：簡単な自己紹介から始め、履歴書や職務要件に基づいて質問します。
   - **重要**：企業名が指定されている場合、その企業の特徴（文化、事業領域）に合わせて質問の方向性を調整してください。
   - **言語**：システムプロンプトは日本語で記述してください。

**JSON形式で返す**（Markdownコードブロックは使用しないでください）：
{{
  "role": "...",
  "system_message": "..."
}}
"""
        else:
            # Default to Chinese
            company_context = f"企业：{request.company_name}" if request.company_name else "企业：未指定（通用面试）"
            style_context = f"面试官风格：{request.interviewer_style}" if request.interviewer_style else "面试官风格：专业、客观"
            
            mode_desc = {
                'real': '真实面试模式：模拟真实企业面试场景，问题更加实际、严格，考察候选人的真实能力',
                'practice': '练习模式：帮助候选人练习面试技巧，问题循序渐进，给予更多指导'
            }.get(request.interview_mode, '练习模式')
            
            difficulty_desc = {
                'basic': '基础难度：问题较为简单，适合初学者或刚入行的候选人',
                'advanced': '进阶难度：问题深入复杂，考察候选人的深度理解和实战经验'
            }.get(request.difficulty, '基础难度')
            
            jd_context = ""
            if request.job_description:
                jd_context = f"\n**目标岗位JD（参考）**：\n{request.job_description}\n"
            
            prompt = f"""
请为以下面试场景生成合适的"面试官角色名称"和"系统提示语"：

**面试场景**：
{jd_context}
- {company_context}
- 职位：{request.position}
- {style_context}
- 模式：{mode_desc}
- 难度：{difficulty_desc}

**任务要求**：
1. **角色名称（role）**：简洁明了，如"面试官-[企业]-[职位]"或"面试官-[职位]"。
2. **系统提示语（system_message）**：
   - 必须包含生成的**简要职位描述（Job Description）**{'（可参考提供的JD）' if request.job_description else '，说明该岗位在目标企业可能的核心职责'}。
   - 设定面试官的人设（符合指定的风格）。
   - 明确考察重点。
   - 强调面试流程：先做简短自我介绍，然后针对简历或职位要求提问。
   - **重要**：如果用户指定了企业名称，请根据该企业的特点（如企业文化、业务领域）定制面试问题方向。
   - **语言**：请使用中文。

**返回JSON格式**（不要使用Markdown代码块）：
{{
  "role": "...",
  "system_message": "..."
}}
"""
        
        # 2. 调用 LLM
        model = os.getenv("INTERVIEW_MODEL", "gpt-4o-mini")
        
        # 强制使用 OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[GenerateParams] Warning: OPENAI_API_KEY not configured")
            
        client = AsyncOpenAI(api_key=api_key, timeout=30.0)
            
        print(f"[GenerateParams] Calling LLM API with model: {model}...")
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        
        result_text = response.choices[0].message.content.strip()
        print(f"[GenerateParams] LLM response: {result_text[:100]}...")
        
        # 3. 解析 JSON
        import json
        import re
        
        # Handle Markdown code blocks
        if '```' in result_text:
            match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result_text, re.DOTALL)
            if match:
                result_text = match.group(1).strip()
        
        # Handle GLM box format
        if '<|begin_of_box|>' in result_text:
            result_text = result_text.replace('<|begin_of_box|>', '').replace('<|end_of_box|>', '').strip()
            
        try:
            result = json.loads(result_text)
            role = result.get('role', f'面试官-{request.position}')
            system_message = result.get('system_message', '')
            
            return JSONResponse({
                "role": role,
                "system_message": system_message
            })
            
        except json.JSONDecodeError:
            print(f"[GenerateParams] JSON parse error, using fallback")
            # Fallback if JSON parse fails
            role = f"面试官-{request.position}"
            system_message = f"你是一名专业的{request.position}面试官。请根据候选人的回答提出有深度的问题。"
            if request.company_name:
                system_message += f" 模拟{request.company_name}的面试场景。"
                
            return JSONResponse({
                "role": role,
                "system_message": system_message
            })

    except Exception as e:
        print(f"[GenerateParams] Error: {e}")
        # Fallback on error
        role = f"面试官-{request.position}"
        system_message = f"你是一名专业的{request.position}面试官。请根据候选人的回答提出有深度的问题。"
        
        return JSONResponse({
            "role": role,
            "system_message": system_message
        })

