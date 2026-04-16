"""Google Cloud Text-to-Speech 服务"""

from __future__ import annotations

import os
from typing import Optional

from google.cloud import texttospeech
from google.oauth2 import service_account


class GoogleTTSService:
    """Google Cloud Text-to-Speech 服务封装"""

    def __init__(self):
        """初始化 Google TTS 客户端"""
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        # 如果没有设置环境变量，尝试使用 Application Default Credentials (ADC)
        # 这在 Cloud Run 等 GCP 环境中会自动使用服务账号
        if not credentials_path:
            try:
                # 使用默认凭证（在 GCP 环境中自动工作）
                self.client = texttospeech.TextToSpeechClient()
                return
            except Exception as e:
                raise RuntimeError(
                    "Failed to initialize Google TTS client. "
                    "Please set GOOGLE_APPLICATION_CREDENTIALS environment variable "
                    "or ensure your application is running in a GCP environment with proper service account permissions. "
                    f"Error: {str(e)}"
                )
        
        # 如果设置了环境变量，检查文件是否存在
        full_path = credentials_path
        if not os.path.isabs(credentials_path):
            # 相对路径：相对于 backend 目录
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            full_path = os.path.join(backend_dir, credentials_path)
        
        if not os.path.exists(full_path):
            raise RuntimeError(
                f"Google service account file not found: {full_path}. "
                f"Please download your service account JSON file and place it at this location."
            )
        
        # 使用服务账号认证
        credentials = service_account.Credentials.from_service_account_file(full_path)
        self.client = texttospeech.TextToSpeechClient(credentials=credentials)
        
    async def synthesize(
        self,
        text: str,
        language_code: str = "ja-JP",
        voice_name: Optional[str] = None,
        speaking_rate: float = 1.0,
        pitch: float = 0.0,
        audio_encoding: str = "MP3"
    ) -> bytes:
        """
        合成语音
        
        Args:
            text: 要合成的文本
            language_code: 语言代码 (如 'ja-JP', 'zh-CN', 'en-US')
            voice_name: 语音名称 (如 'ja-JP-Neural2-B')
                       如果为 None，将自动选择该语言的默认语音
            speaking_rate: 语速 (0.25-4.0，默认 1.0)
            pitch: 音调 (-20.0 到 20.0，默认 0.0)
            audio_encoding: 音频编码格式 ('MP3', 'LINEAR16', 'OGG_OPUS')
        
        Returns:
            音频数据 (bytes)
        """
        # 构建合成输入
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # 如果没有指定语音名称，使用默认语音
        if not voice_name:
            voice_name = self._get_default_voice(language_code)
        
        # 构建语音选择
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name
        )
        
        # 映射音频编码
        encoding_map = {
            "MP3": texttospeech.AudioEncoding.MP3,
            "LINEAR16": texttospeech.AudioEncoding.LINEAR16,
            "OGG_OPUS": texttospeech.AudioEncoding.OGG_OPUS,
        }
        audio_encoding_enum = encoding_map.get(audio_encoding.upper(), texttospeech.AudioEncoding.MP3)
        
        # 构建音频配置
        audio_config = texttospeech.AudioConfig(
            audio_encoding=audio_encoding_enum,
            speaking_rate=speaking_rate,
            pitch=pitch
        )
        
        # 调用 Google TTS API
        response = self.client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        return response.audio_content
    
    @staticmethod
    def _get_default_voice(language_code: str) -> str:
        """根据语言代码返回推荐的默认语音"""
        default_voices = {
            "ja-JP": "ja-JP-Neural2-B",  # 日语女声（自然）
            "zh-CN": "cmn-CN-Standard-A",  # 中文女声
            "en-US": "en-US-Neural2-C",  # 英语女声
            "ko-KR": "ko-KR-Neural2-A",  # 韩语女声
        }
        return default_voices.get(language_code, "en-US-Standard-A")
    
    def get_available_voices(self, language_code: Optional[str] = None) -> list:
        """
        获取可用的语音列表
        
        Args:
            language_code: 可选的语言代码过滤器
        
        Returns:
            语音列表
        """
        response = self.client.list_voices(language_code=language_code)
        
        voices = []
        for voice in response.voices:
            voices.append({
                "name": voice.name,
                "language_codes": list(voice.language_codes),
                "ssml_gender": texttospeech.SsmlVoiceGender(voice.ssml_gender).name,
                "natural_sample_rate_hertz": voice.natural_sample_rate_hertz
            })
        
        return voices

