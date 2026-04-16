"""
動画非言語行動分析サービス
GPT-4o Visionを使用して面接動画の非言語表現を分析
"""
import os
import base64
import tempfile
import asyncio
import json
import re
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI

try:  # pragma: no cover
    import cv2
    _CV2_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    cv2 = None  # type: ignore
    _CV2_AVAILABLE = False
    _CV2_IMPORT_ERROR: Optional[Exception] = exc
else:
    _CV2_IMPORT_ERROR = None

class VideoNonverbalAnalyzer:
    """動画非言語行動分析器"""
    
    def __init__(self):
        # 读取模型选择配置
        # ⚠️ 强制使用 OpenAI GPT-4o 以获得更准确的非语言分析
        self.model_provider = "openai"
        self.max_frames = int(os.getenv("VIDEO_ANALYSIS_MAX_FRAMES", "6"))  # 默认6帧（平衡检测精度和速度）
        
        # OpenAI GPT-4o 配置
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            print("[VideoAnalyzer] Warning: OPENAI_API_KEY not configured")
        
        # ✅ Do not crash module import when OPENAI_API_KEY is missing (dev / CI).
        # In production, this must be configured.
        if openai_api_key:
            self.client = AsyncOpenAI(
                api_key=openai_api_key,
                timeout=30.0,  # 从120s降低到30s，避免长时间等待
                max_retries=2
            )
        else:
            self.client = None
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
        print(f"[VideoAnalyzer] ✓ Initialized with OpenAI: {self.model} (Forced)")
        
        print(f"[VideoAnalyzer] Provider: {self.model_provider}, Model: {self.model}, Timeout: 30s")
    
    async def analyze_video(
        self, 
        video_path: str,
        transcript: str,
        duration: float,
        language: str = "ja"
    ) -> Dict[str, Any]:
        """
        動画中の非言語行動を分析
        
        Args:
            video_path: 動画ファイルパス
            transcript: 音声認識テキスト
            duration: 動画の長さ（秒）
            language: 分析结果的语言 (ja/en/zh)
            
        Returns:
            非言語分析結果辞書
        """
        print(f"[VideoAnalyzer] ▶ Starting video analysis (duration: {duration:.1f}s)")
        
        try:
            # 所有模型统一使用抽帧分析，避免外部上传依赖
            if not _CV2_AVAILABLE:
                print("[VideoAnalyzer] ✗ OpenCV (cv2) not installed; returning default analysis")
                return self._get_default_analysis()
            if not getattr(self, "client", None):
                print("[VideoAnalyzer] ✗ OpenAI client not configured; returning default analysis")
                return self._get_default_analysis()
            
            print(f"[VideoAnalyzer] Using frame-based analysis pipeline ({self.model_provider.upper()})")
            print(f"[VideoAnalyzer] Step 1: Extracting key frames...")
            frames = await asyncio.to_thread(
                self._extract_key_frames,
                video_path,
                self.max_frames,
            )
            
            if not frames:
                print(f"[VideoAnalyzer] ✗ ERROR: No frames extracted from video!")
                return self._get_default_analysis()
            
            print(f"[VideoAnalyzer] ✓ Extracted {len(frames)} frames successfully")
            
            print(f"[VideoAnalyzer] Step 2: Encoding frames to base64...")
            encoded_results = await asyncio.to_thread(self._encode_frames, frames)
            frame_images = []
            for i, item in enumerate(encoded_results):
                frame_images.append(item["base64"])
            
            if not frame_images:
                print(f"[VideoAnalyzer] ✗ ERROR: Failed to encode frames!")
                return self._get_default_analysis()
            
            print(f"[VideoAnalyzer] ✓ Encoded {len(frame_images)} frames")
            
            print(f"[VideoAnalyzer] Step 3: Calling vision model API...")
            analysis = await self._analyze_with_gpt4o(
                frame_images, 
                transcript,
                duration,
                language
            )
            
            print(f"[VideoAnalyzer] ✓ Analysis completed successfully")
            return analysis
            
        except Exception as e:
            print(f"[VideoAnalyzer] ✗ ERROR analyzing video: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # 返回默认分析
            print(f"[VideoAnalyzer] ⚠️  Returning default mock analysis due to error")
            return self._get_default_analysis()
    
    def _extract_key_frames(self, video_path: str, num_frames: int = 6) -> List:
        """動画からキーフレームを抽出"""
        frames = []
        
        try:
            print(f"[VideoAnalyzer] 🔍 Opening video file: {video_path}")
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"[VideoAnalyzer] ✗ ERROR: Failed to open video file")
                return []
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            if total_frames == 0:
                print("[VideoAnalyzer] ⚠️ Warning: Video has no frames")
                cap.release()
                return []
            
            # 均匀采样帧
            frame_indices = [int(total_frames * i / num_frames) for i in range(num_frames)]
            
            for idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    # 调整大小以平衡检测精度和传输速度
                    # 320x240 足够检测人脸，同时保持较小的传输体积
                    frame = cv2.resize(frame, (320, 240))
                    frames.append(frame)
            
            cap.release()
            print(f"[VideoAnalyzer] Extracted {len(frames)} frames")
            
        except Exception as e:
            print(f"[VideoAnalyzer] Error extracting frames: {e}")
        
        return frames
    
    def _encode_frames(self, frames: List) -> List[Dict[str, Any]]:
        """フレームをbase64文字列にエンコードし、解像度を返す"""
        encoded: List[Dict[str, Any]] = []
        for frame in frames:
            try:
                success, buffer = cv2.imencode('.jpg', frame)
                if not success:
                    continue
                base64_image = base64.b64encode(buffer).decode('utf-8')
                encoded.append(
                    {
                        "base64": base64_image,
                        "resolution": (frame.shape[1], frame.shape[0]),
                    }
                )
            except Exception as exc:
                print(f"[VideoAnalyzer] Warning: Failed to encode frame: {exc}")
        return encoded
    
    async def _analyze_with_gpt4o(
        self, 
        frame_images: List[str],
        transcript: str,
        duration: float,
        language: str = "ja"
    ) -> Dict[str, Any]:
        """GPT-4o Visionを使用して動画フレームを分析"""
        
        # 多语言输出指令
        output_instruction = {
            "ja": "Provide concrete observations in Japanese for all description fields.",
            "en": "Provide concrete observations in English for all description fields.",
            "zh": "Provide concrete observations in Chinese (Simplified) for all description fields."
        }
        lang_instruction = output_instruction.get(language, output_instruction["ja"])
        if language.startswith("zh"):
            lang_instruction = output_instruction["zh"]
        elif language.startswith("en"):
            lang_instruction = output_instruction["en"]
            
        # 警告前缀
        warning_prefix = {
            "ja": {"face": "【警告】顔がフレームアウトしています。", "habit": "【警告】不適切な行動（[具体行動]）が検出されました。"},
            "en": {"face": "[WARNING] Face is off-screen.", "habit": "[WARNING] Inappropriate behavior ([specific_behavior]) detected."},
            "zh": {"face": "【警告】检测到人脸在画面外。", "habit": "【警告】检测到不当行为（[具体行为]）。"}
        }
        wp = warning_prefix.get(language, warning_prefix["ja"])
        if language.startswith("zh"):
            wp = warning_prefix["zh"]
        elif language.startswith("en"):
            wp = warning_prefix["en"]
        
        # 构建提示词
        # 構築プロンプト
        prompt = f"""
You are a professional interview communication skills evaluator. Please analyze a {duration:.1f}-second interview practice video.

**⚠️ CRITICAL INSTRUCTION - PRIORITY DETECTION (MANDATORY)**:
You must scan every single frame for the following critical issues. If ANY of these are detected in ANY frame, you must report them immediately.

1. **FACE_PRESENCE (RED CARD)**:
   - Is the candidate's face clearly visible in the frame?
   - **CRITICAL RULES**:
     - ✅ **DO COUNT AS VISIBLE**: Face is visible even if the candidate is moving, gesturing, or making expressions. Movement and actions are NORMAL and should NOT be considered as "face off-screen".
     - ✅ **DO COUNT AS VISIBLE**: Face is visible even if partially obscured by hands during gestures (as long as eyes/nose/mouth are still visible).
     - ❌ **DO NOT COUNT AS VISIBLE**: Only if the video shows a static object (wall, desk, ceiling), a black screen, or if the face is completely missing/obscured in ALL frames.
     - ❌ **DO NOT COUNT AS VISIBLE**: Only if the face is too blurry/dark/obscured to be seen clearly in ALL frames (not just some frames).
   - **If face is NOT visible in ANY frame**:
     - Set `face_off_screen_detected` to true.
     - Set `face_frames_count` to 0.
     - `face_visibility_score_label` MUST be "Poor".
     - You MUST start `face_visibility` description with "{wp['face']}"
   - **If face IS visible in at least one frame**:
     - Set `face_off_screen_detected` to false.
     - Set `face_frames_count` to the actual number of frames where face is visible (1-{len(frame_images)}).
     - `face_visibility_score_label` should be "Good" or "Fair" based on visibility quality.

2. **BAD HABITS (RED CARD)**:
   - Check for specific unprofessional behaviors in ANY frame:
     - **Touching face inappropriately**: Rubbing eyes, touching face excessively, scratching face
     - **Nose-related**: Picking nose, touching nose repeatedly, wiping nose
     - **Ear-related**: Scratching ears, touching ears repeatedly, pulling ears
     - **Eating / Drinking**: Eating food, drinking beverages during interview
     - **Yawning**: Yawning visibly
     - **Distracted behavior**: Looking away for long periods, checking phone, looking at other screens
     - **Fidgeting**: Excessive hand movements, playing with objects, tapping fingers nervously
   - If ANY of these are detected in ANY frame:
     - Set `bad_habit_detected` to true.
     - Set `bad_habit_details` to the specific behavior observed (e.g., "picking nose", "scratching ears", "touching face excessively").
     - `body_posture_score_label` MUST be "Poor".
     - You MUST start `body_posture` description with "{wp['habit']}"

3. **SMILE (BONUS)**:
   - Is the candidate smiling?
   - If yes (and no Red Cards), `smile_detected` = true.

**REPORTING REQUIREMENT**:
In the `visual_performance` JSON object, you MUST include a special `metadata` field with these exact keys:
- `face_frames_count`: Number of frames where face is clearly visible (0-{len(frame_images)})
- `total_frames`: {len(frame_images)}
- `face_off_screen_detected`: true if ANY frame has face missing/obscured, false otherwise
- `bad_habit_detected`: true if ANY bad habit is detected, false otherwise
- `bad_habit_details`: string describing the habit (e.g. "rubbing eyes") or null
- `smile_detected`: true if a genuine smile is detected in ANY frame, false otherwise
- `smile_frames_count`: Number of frames with a smile

**Transcript**: "{transcript}"

**VOICE PERFORMANCE ANALYSIS (Based on Transcript and Video Context)**:
Analyze the candidate's voice performance based on the transcript and video context. Pay special attention to:

1. **SPEECH QUALITY ISSUES (RED CARD)**:
   - **Coughing**: Any coughing sounds or interruptions in speech
   - **Unclear pronunciation**: Mumbling, slurred words, or words that are difficult to understand
   - **Throat clearing**: Frequent throat clearing or "ahem" sounds
   - **Stuttering or hesitations**: Excessive "um", "uh", "er" sounds or repeated words
   - **Voice breaks**: Sudden voice breaks or cracks during speech
   - **Inconsistent volume**: Sudden volume drops or spikes that affect clarity
   
   If ANY of these are detected:
   - Set the relevant score label (e.g., `pronunciation_score_label`, `pause_score_label`) to "Poor"
   - Clearly describe the issue in the corresponding field (e.g., `pronunciation`, `pause`, `volume`)
   - Mention the specific problem in the `summary` field

2. **Normal Voice Evaluation**:
   - **Speed**: Speaking rate (too fast/slow/normal)
   - **Tone**: Emotional expression and intonation
   - **Volume**: Overall volume level
   - **Pronunciation**: Clarity of articulation (when no issues detected)
   - **Pause**: Appropriate use of pauses and silence

**OUTPUT FORMAT (JSON ONLY)**:
{{
  "voice_performance": {{
    "speed": "Description of speaking speed",
    "tone": "Description of tone and emotional expression",
    "volume": "Description of volume level",
    "pronunciation": "Description of pronunciation clarity (mention coughing, unclear words, etc. if detected)",
    "pause": "Description of pause usage (mention stuttering, hesitations if detected)",
    "summary": "Overall voice performance summary",
    "speed_score_label": "Good/Fair/Poor",
    "tone_score_label": "Good/Fair/Poor",
    "volume_score_label": "Good/Fair/Poor",
    "pronunciation_score_label": "Good/Fair/Poor",
    "pause_score_label": "Good/Fair/Poor"
  }},
  "visual_performance": {{
    "metadata": {{
      "face_frames_count": 8,
      "total_frames": 8,
      "face_off_screen_detected": false,
      "bad_habit_detected": false,
      "bad_habit_details": null,
      "smile_detected": true,
      "smile_frames_count": 2
    }},
    "face_visibility": "...",
    "eye_contact": "...",
    "facial_expression": "...",
    "body_posture": "...",
    "appearance": "...",
    "summary": "...",
    "face_visibility_score_label": "Good",
    "eye_contact_score_label": "Good",
    "facial_expression_score_label": "Good",
    "body_posture_score_label": "Good",
    "appearance_score_label": "Good"
  }},
  "overall_impression": "..."
}}

**{lang_instruction}**
"""
        
        try:
            print(f"[VideoAnalyzer] ▶ Preparing Vision API call...")
            print(f"[VideoAnalyzer]    Provider: {self.model_provider.upper()}")
            print(f"[VideoAnalyzer]    Model: {self.model}")
            print(f"[VideoAnalyzer]    Using {min(len(frame_images), 8)} frames")
            print(f"[VideoAnalyzer]    API Key configured: {bool(self.client.api_key)}")
            
            # 构建消息内容
            content = [{"type": "text", "text": prompt}]
            
            # 添加图片（使用8帧以获得更全面的分析）
            for i, img_base64 in enumerate(frame_images[:8]):  # 从3帧增加到8帧
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_base64}",
                        "detail": "low"  # 使用低分辨率模式
                    }
                })
                print(f"[VideoAnalyzer]    Added frame {i+1} (size: {len(img_base64)} chars)")
            
            print(f"[VideoAnalyzer] ▶ Sending request to {self.model_provider.upper()} API...")
            
            # 构建请求参数
            request_params = {
                "model": self.model,
                "messages": [{
                    "role": "system",
                    "content": "You are a professional interview communication skills evaluator. Provide output in JSON format only."
                }, {
                    "role": "user",
                    "content": content
                }],
                "max_tokens": 1500,
                "temperature": 0.3, # Lower temperature for more consistent JSON
                "response_format": { "type": "json_object" } # Force JSON mode
            }
            
            # 添加重试机制（最多重试2次）
            max_retries = 2
            response = None
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    response = await self.client.chat.completions.create(**request_params)
                    break  # 成功则退出循环
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        print(f"[VideoAnalyzer] ⚠️  Attempt {attempt + 1} failed: {e}, retrying...")
                        await asyncio.sleep(1)  # 等待1秒后重试
                    else:
                        print(f"[VideoAnalyzer] ✗ All {max_retries + 1} attempts failed")
                        raise
            
            if response is None:
                raise Exception(f"Failed to get response after {max_retries + 1} attempts: {last_error}")
            
            print(f"[VideoAnalyzer] ✓ Received response from {self.model_provider.upper()}")
            result_text = response.choices[0].message.content
            print(f"[VideoAnalyzer] Response length: {len(result_text)} chars")
            
            # 解析JSON结果
            analysis = json.loads(result_text)
            print(f"[VideoAnalyzer] ✓ Successfully parsed JSON")
            
            print(f"[VideoAnalyzer] Formatting analysis result...")
            formatted = self._format_analysis(analysis)
            print(f"[VideoAnalyzer] ✓ Analysis formatted and ready")
            return formatted
            
        except Exception as e:
            print(f"[VideoAnalyzer] ✗ GPT-4o analysis error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            print(f"[VideoAnalyzer] ⚠️  Returning default mock analysis")
            return self._get_default_analysis()
    
    def _format_analysis(self, raw_analysis: Dict) -> Dict[str, Any]:
        """分析結果を標準形式にフォーマット"""

        def _first_valid_dict(*candidates: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            for candidate in candidates:
                if isinstance(candidate, dict) and candidate:
                    return candidate
            return {}

        # 支持多种字段命名（不同模型可能返回不同 key）
        voice_source = _first_valid_dict(
            raw_analysis.get("voice_performance"),
            raw_analysis.get("voicePerformance"),
            raw_analysis.get("voice")
        )

        visual_source = _first_valid_dict(
            raw_analysis.get("visual_performance"),
            raw_analysis.get("visualPerformance"),
            raw_analysis.get("visual")
        )

        overall_impression = (
            raw_analysis.get("overall_impression")
            or raw_analysis.get("overallImpression")
            or raw_analysis.get("overall")
            or raw_analysis.get("summary")
        )

        def _extract_field(source: Dict[str, Any], key: str, default: str) -> str:
            if not isinstance(source, dict):
                return default
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            return default

        neutral_defaults = {
            "speed": "明確な評価がありません",
            "tone": "明確な評価がありません",
            "volume": "明確な評価がありません",
            "pronunciation": "明確な評価がありません",
            "pause": "明確な評価がありません",
            "summary_voice": "音声部分で有効な分析結果が得られませんでした",
            "face_visibility": "顔の可視性を確認できませんでした",
            "eye_contact": "明確な評価がありません",
            "facial_expression": "明確な評価がありません",
            "body_posture": "明確な評価がありません",
            "appearance": "明確な評価がありません",
            "summary_visual": "視覚部分で有効な分析結果が得られませんでした",
            "overall": "全体的な評価がありません",
            "speed_score_label": "Fair",
            "tone_score_label": "Fair",
            "volume_score_label": "Fair",
            "pronunciation_score_label": "Fair",
            "pause_score_label": "Fair",
            "face_visibility_score_label": "Fair",
            "eye_contact_score_label": "Fair",
            "facial_expression_score_label": "Fair",
            "body_posture_score_label": "Fair",
            "appearance_score_label": "Fair"
        }

        formatted = {
            "voice": {
                "speed": _extract_field(voice_source, "speed", neutral_defaults["speed"]),
                "tone": _extract_field(voice_source, "tone", neutral_defaults["tone"]),
                "volume": _extract_field(voice_source, "volume", neutral_defaults["volume"]),
                "pronunciation": _extract_field(voice_source, "pronunciation", neutral_defaults["pronunciation"]),
                "pause": _extract_field(voice_source, "pause", neutral_defaults["pause"]),
                "summary": _extract_field(voice_source, "summary", neutral_defaults["summary_voice"]),
                "speed_score_label": _extract_field(voice_source, "speed_score_label", neutral_defaults["speed_score_label"]),
                "tone_score_label": _extract_field(voice_source, "tone_score_label", neutral_defaults["tone_score_label"]),
                "volume_score_label": _extract_field(voice_source, "volume_score_label", neutral_defaults["volume_score_label"]),
                "pronunciation_score_label": _extract_field(voice_source, "pronunciation_score_label", neutral_defaults["pronunciation_score_label"]),
                "pause_score_label": _extract_field(voice_source, "pause_score_label", neutral_defaults["pause_score_label"])
            },
            "visual": {
                "face_visibility": _extract_field(visual_source, "face_visibility", neutral_defaults["face_visibility"]),
                "eye_contact": _extract_field(visual_source, "eye_contact", neutral_defaults["eye_contact"]),
                "facial_expression": _extract_field(visual_source, "facial_expression", neutral_defaults["facial_expression"]),
                "body_posture": _extract_field(visual_source, "body_posture", neutral_defaults["body_posture"]),
                "appearance": _extract_field(visual_source, "appearance", neutral_defaults["appearance"]),
                "summary": _extract_field(visual_source, "summary", neutral_defaults["summary_visual"]),
                "face_visibility_score_label": _extract_field(visual_source, "face_visibility_score_label", neutral_defaults["face_visibility_score_label"]),
                "eye_contact_score_label": _extract_field(visual_source, "eye_contact_score_label", neutral_defaults["eye_contact_score_label"]),
                "facial_expression_score_label": _extract_field(visual_source, "facial_expression_score_label", neutral_defaults["facial_expression_score_label"]),
                "body_posture_score_label": _extract_field(visual_source, "body_posture_score_label", neutral_defaults["body_posture_score_label"]),
                "appearance_score_label": _extract_field(visual_source, "appearance_score_label", neutral_defaults["appearance_score_label"]),
                # 保留元数据以供后续处理使用
                "metadata": visual_source.get("metadata", {})
            },
            "overall_impression": overall_impression or neutral_defaults["overall"]
        }

        # 如果模型返回的是总结性字符串，则放入 summary 字段
        if isinstance(voice_source, str) and voice_source.strip():
            formatted["voice"]["summary"] = voice_source.strip()
        if isinstance(visual_source, str) and visual_source.strip():
            formatted["visual"]["summary"] = visual_source.strip()

        return formatted
    
    def _get_default_analysis(self) -> Dict[str, Any]:
        """デフォルトの分析結果を返す（分析が失敗した場合に使用）"""
        return {
            "voice": {
                "speed": "明確な評価がありません",
                "tone": "明確な評価がありません",
                "volume": "明確な評価がありません",
                "pronunciation": "明確な評価がありません",
                "pause": "明確な評価がありません",
                "summary": "音声部分で有効な分析結果が得られませんでした",
                "speed_score_label": "Fair",
                "tone_score_label": "Fair",
                "volume_score_label": "Fair",
                "pronunciation_score_label": "Fair",
                "pause_score_label": "Fair"
            },
            "visual": {
                "face_visibility": "顔の可視性を確認できませんでした",
                "eye_contact": "明確な評価がありません",
                "facial_expression": "明確な評価がありません",
                "body_posture": "明確な評価がありません",
                "appearance": "明確な評価がありません",
                "summary": "視覚部分で有効な分析結果が得られませんでした（分析エラー）",
                "face_visibility_score_label": "Fair",
                "eye_contact_score_label": "Fair",
                "facial_expression_score_label": "Fair",
                "body_posture_score_label": "Fair",
                "appearance_score_label": "Fair",
                "metadata": {
                    "face_frames_count": 0,
                    "total_frames": 0,
                    "analysis_failed": True
                }
            },
            "overall_impression": "全体的な評価がありません"
        }


# 创建单例实例
video_nonverbal_analyzer = VideoNonverbalAnalyzer()
