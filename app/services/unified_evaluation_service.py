"""
统一评估服务 - 并行执行视觉、语音、以及4个内容维度评估，加快响应速度
Unified Evaluation Service - Parallel Execution of Visual, Voice, Clarity, Evidence, Impact, Engagement
"""

import json
import yaml
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from uuid import UUID

from openai import AsyncOpenAI
from app.core.config import settings

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False
    print("[UnifiedEvaluation] ⚠️ PyYAML not installed, config loading will fail")


class UnifiedEvaluationService:
    """统一评估服务"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"  # 使用GPT-4o Vision支持图片输入
        self.config_path = Path(__file__).parent.parent / "config" / "evaluation" / "unified_evaluation_config.yaml"
        self.config = self._load_config()
        
        # 维度定义（用于加载Prompt）
        self.content_dimensions = {
            "clarity": "明确性",
            "evidence": "根据",
            "impact": "影响力",
            "engagement": "参与度"
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置"""
        if not _YAML_AVAILABLE:
            print("[UnifiedEvaluation] ⚠️ PyYAML not available, using default config")
            return {
                "model": {"max_tokens": 4000, "temperature": 0.3},
                "inputs": {"video_frames": {"count": 6}}
            }
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"[UnifiedEvaluation] ⚠️ Failed to load config: {e}")
            return {
                "model": {"max_tokens": 4000, "temperature": 0.3},
                "inputs": {"video_frames": {"count": 6}}
            }
    
    async def evaluate_unified(
        self,
        frame_images: List[str],
        transcript: str,
        question: Optional[str] = None,
        duration: float = 0.0,
        audio_features: Optional[Dict[str, Any]] = None,
        previous_scores: Optional[Dict[str, float]] = None,
        language: str = "zh"
    ) -> Dict[str, Any]:
        """
        统一评估：并行执行视觉分析、语音分析、4个内容维度反馈生成
        共 6 个并行 LLM 任务
        """
        try:
            print(f"[UnifiedEvaluation] 🚀 Starting 6-way parallel evaluation (lang: {language})...")
            
            # 1. 准备并行任务
            tasks = []
            
            # Task 1: Visual Evaluation (Need frames)
            tasks.append(self._execute_visual_task(frame_images, duration, language))
            
            # Task 2: Voice Evaluation (Need transcript, audio_features)
            tasks.append(self._execute_voice_task(transcript, audio_features, language))
            
            # Task 3-6: Content Dimensions (Clarity, Evidence, Impact, Engagement)
            for dim_key in self.content_dimensions.keys():
                tasks.append(self._execute_dimension_task(dim_key, transcript, question, previous_scores, language))
            
            # 2. 并行执行
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 3. 聚合结果
            visual_result = results[0]
            voice_result = results[1]
            content_results = results[2:] # List of 4 results
            
            final_result = {
                "visual_analysis": {},
                "voice_analysis": {},
                "tone_analysis": {},
                "feedback": {}
            }
            
            # Process Visual Result
            if isinstance(visual_result, dict):
                final_result["visual_analysis"] = visual_result.get("visual_analysis", {})
                if "feedback" in visual_result:
                    final_result["feedback"].update(visual_result["feedback"])
            else:
                print(f"[UnifiedEvaluation] ❌ Visual task failed: {visual_result}")

            # Process Voice Result
            if isinstance(voice_result, dict):
                final_result["voice_analysis"] = voice_result.get("voice_analysis", {})
                final_result["tone_analysis"] = voice_result.get("tone_analysis", {})
                if "feedback" in voice_result:
                    final_result["feedback"].update(voice_result["feedback"])
            else:
                print(f"[UnifiedEvaluation] ❌ Voice task failed: {voice_result}")

            # Process Content Results (4 dimensions)
            for i, res in enumerate(content_results):
                dim_key = list(self.content_dimensions.keys())[i]
                if isinstance(res, dict):
                    if "feedback" in res:
                        final_result["feedback"].update(res["feedback"])
                else:
                    print(f"[UnifiedEvaluation] ❌ Dimension task '{dim_key}' failed: {res}")
            
            print(f"[UnifiedEvaluation] ✅ 6-way Parallel evaluation completed")
            return final_result
            
        except Exception as e:
            print(f"[UnifiedEvaluation] ❌ Error in parallel evaluation: {e}")
            import traceback
            traceback.print_exc()
            return {
                "visual_analysis": {},
                "voice_analysis": {},
                "tone_analysis": {},
                "feedback": {}
            }

    async def _execute_visual_task(self, frame_images: List[str], duration: float, language: str) -> Dict[str, Any]:
        """执行视觉评估任务"""
        try:
            # Load from visual/system_msg_zh.md
            system_prompt = self._load_system_prompt(language, "visual")
            user_prompt = self._load_user_prompt(language, "visual", 
                frame_images=frame_images, duration=duration)
            
            content = [{"type": "text", "text": user_prompt}]
            max_frames = self.config.get("inputs", {}).get("video_frames", {}).get("count", 6)
            for img_base64 in frame_images[:max_frames]:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_base64}", "detail": "low"}
                })
                
            return await self._call_llm(system_prompt, [{"role": "user", "content": content}])
        except Exception as e:
            print(f"[UnifiedEvaluation] ❌ Visual task error: {e}")
            raise

    async def _execute_voice_task(self, transcript: str, audio_features: Optional[Dict[str, Any]], language: str) -> Dict[str, Any]:
        """执行语音评估任务"""
        try:
            # Load from voice/system_msg_zh.md
            system_prompt = self._load_system_prompt(language, "voice")
            user_prompt = self._load_user_prompt(language, "voice", 
                transcript=transcript, audio_features=audio_features)
            
            return await self._call_llm(system_prompt, [{"role": "user", "content": user_prompt}])
        except Exception as e:
            print(f"[UnifiedEvaluation] ❌ Voice task error: {e}")
            raise

    async def _execute_dimension_task(self, dim_key: str, transcript: str, question: Optional[str], previous_scores: Optional[Dict[str, float]], language: str) -> Dict[str, Any]:
        """执行单个内容维度评估任务"""
        try:
            # Load specific dimension prompt
            # e.g., content/clarity/system_msg_zh.md
            system_prompt = self._load_dimension_system_prompt(language, dim_key)
            user_prompt = self._load_dimension_user_prompt(language, dim_key, 
                transcript=transcript, question=question, previous_scores=previous_scores)
            
            return await self._call_llm(system_prompt, [{"role": "user", "content": user_prompt}])
        except Exception as e:
            print(f"[UnifiedEvaluation] ❌ Dimension '{dim_key}' task error: {e}")
            raise

    async def _call_llm(self, system_prompt: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """调用LLM通用方法"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            max_tokens=self.config.get("model", {}).get("max_tokens", 4000),
            temperature=self.config.get("model", {}).get("temperature", 0.3),
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    def _load_system_prompt(self, language: str, category: str) -> str:
        """加载系统prompt (visual/voice)"""
        # path: v3/{category}/system_msg_{language}.md
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / category / f"system_msg_{language}.md"
        
        if not prompt_path.exists():
            prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / category / "system_msg_zh.md"
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"[UnifiedEvaluation] ⚠️ Failed to load system prompt ({category}): {e}")
            return ""
    
    def _load_user_prompt(self, language: str, category: str, **kwargs) -> str:
        """加载用户prompt (visual/voice)"""
        # path: v3/{category}/user_msg_{language}.md
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / category / f"user_msg_{language}.md"
        
        if not prompt_path.exists():
            prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / category / "user_msg_zh.md"
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                template = f.read()
            return self._format_user_prompt(template, language, **kwargs)
        except Exception as e:
            print(f"[UnifiedEvaluation] ⚠️ Failed to load user prompt ({category}): {e}")
            return ""

    def _load_dimension_system_prompt(self, language: str, dim_key: str) -> str:
        """加载维度特定系统prompt"""
        # path: v3/content/{dim_key}/system_msg_{language}.md
        # If not found, generate dynamically from template (optional fallback)
        # For now, we assume files exist or we use template
        
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / dim_key / f"system_msg_{language}.md"
        if not prompt_path.exists():
             prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / dim_key / "system_msg_zh.md"
        
        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
            
        # Fallback: Load template and fill
        template_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / f"base_content_system_template_{language}.md"
        if not template_path.exists():
            template_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / "base_content_system_template_zh.md"
            
        try:
            template = template_path.read_text(encoding='utf-8')
            # Fill template with dimension info
            # Ideally we need definition and vocab. 
            # For simplicity now, we can hardcode or load from a config.
            # Let's define simple maps here for fallback generation
            defs = {
                "clarity": "回答的逻辑结构清晰，结论明确，没有歧义。",
                "evidence": "回答提供了具体的事实、数据、案例或经验作为支持。",
                "impact": "回答内容具有说服力，能给面试官留下深刻印象，展现专业性。",
                "engagement": "回答展现出积极的态度，甚至引导对话，不仅仅是单向陈述。"
            }
            vocab_p = {
                "clarity": "结论、意图、清晰、逻辑、焦点",
                "evidence": "佐证、成果、案例、实绩、说服力",
                "impact": "印象、要点、力度、传递性",
                "engagement": "提问意图、对话性、契合、交流"
            }
            vocab_a = {
                "clarity": '"具体"、"通俗易懂"',
                "evidence": '"具体例子"、"具体"',
                "impact": '"具体"',
                "engagement": '"具体"'
            }
            
            return template.format(
                dimension_name=self.content_dimensions.get(dim_key, dim_key),
                dimension_key=dim_key,
                dimension_definition=defs.get(dim_key, ""),
                priority_vocabulary=vocab_p.get(dim_key, ""),
                avoid_vocabulary=vocab_a.get(dim_key, "")
            )
        except Exception as e:
            print(f"[UnifiedEvaluation] ⚠️ Failed to load dimension prompt ({dim_key}): {e}")
            return ""

    def _load_dimension_user_prompt(self, language: str, dim_key: str, **kwargs) -> str:
        """加载维度特定用户prompt"""
        # path: v3/content/{dim_key}/user_msg_{language}.md
        # Fallback to template
        
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / dim_key / f"user_msg_{language}.md"
        if not prompt_path.exists():
             prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / dim_key / "user_msg_zh.md"
        
        template = ""
        if prompt_path.exists():
            template = prompt_path.read_text(encoding='utf-8')
        else:
            # Fallback template
            template_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / f"base_content_user_template_{language}.md"
            if not template_path.exists():
                template_path = Path(__file__).parent.parent / "config" / "prompts" / "evaluation" / "v3" / "content" / "base_content_user_template_zh.md"
            template = template_path.read_text(encoding='utf-8')
            
        # Format
        return self._format_user_prompt(template, language, dimension_name=self.content_dimensions.get(dim_key, dim_key), dimension_key=dim_key, **kwargs)

    def _format_user_prompt(self, template: str, language: str, **kwargs) -> str:
        """Helper to format user prompt with common args"""
        format_args = {"language": language}
        format_args.update(kwargs) # Add specific args like dimension_name
        
        if "frame_images" in kwargs and isinstance(kwargs["frame_images"], list):
            format_args["total_frames"] = len(kwargs["frame_images"])
            format_args["frame_images"] = f"共 {len(kwargs['frame_images'])} 帧视频帧（已作为图片附件提供）"
        
        # Ensure optional fields are handled strings
        if "audio_features" in kwargs:
            feats = kwargs["audio_features"]
            format_args["audio_features"] = "无"
            if feats:
                format_args["audio_features"] = "\n".join([f"- {k}: {v}" for k, v in feats.items() if v is not None])
        
        if "previous_scores" in kwargs:
            scores = kwargs["previous_scores"]
            format_args["previous_scores"] = "无"
            if scores:
                format_args["previous_scores"] = "\n".join([f"- {k}: {v:.1f}" for k, v in scores.items()])
                
        # Handle missing keys in template gracefully? No, let it error if keys missing to fix bugs.
        return template.format(**format_args)
