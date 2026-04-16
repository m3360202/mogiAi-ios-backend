import json
from pathlib import Path
from typing import Tuple
from openai import AsyncOpenAI
from app.core.config import settings

class LLMFactory:
    _config = None
    _config_path = Path(__file__).parent.parent / "config" / "llm_config.json"

    @classmethod
    def _load_config(cls):
        # Always reload config to support hot-swapping if needed, 
        # or load once. For performance, maybe load once, but for "switch" requirement, maybe check timestamp?
        # For now, let's load on first access, but maybe we can add a method to reload.
        if cls._config is None:
            if cls._config_path.exists():
                try:
                    with open(cls._config_path, "r", encoding="utf-8") as f:
                        cls._config = json.load(f)
                except Exception as e:
                    print(f"[LLMFactory] Error loading config: {e}")
                    cls._config = {}
            else:
                cls._config = {}
        return cls._config

    @classmethod
    def get_non_visual_config(cls) -> dict:
        config = cls._load_config()
        provider = config.get("non_visual_model_provider", "openai")
        providers = config.get("providers", {})
        
        # Default to OpenAI if provider not found or config empty
        if provider not in providers:
            return {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": None,
                "api_key": settings.OPENAI_API_KEY
            }
            
        provider_config = providers[provider]
        model = provider_config.get("model", "gpt-4o-mini")
        base_url = provider_config.get("base_url")
        
        api_key = None
        if provider == "deepseek":
            api_key = settings.DEEPSEEK_API_KEY
        else:
            api_key = settings.OPENAI_API_KEY
            
        return {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "api_key": api_key
        }

    @classmethod
    def get_non_visual_client(cls) -> Tuple[AsyncOpenAI, str]:
        """
        Returns (client, model_name) for non-visual tasks.
        """
        conf = cls.get_non_visual_config()
        
        api_key = conf["api_key"]
        base_url = conf["base_url"]
        model = conf["model"]
        
        if not api_key:
            print(f"[LLMFactory] Warning: API Key for {conf['provider']} is missing.")
        
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0
        )
        
        return client, model

    @classmethod
    def get_visual_client(cls) -> Tuple[AsyncOpenAI, str]:
        """
        Returns (client, model_name) for visual tasks (always OpenAI gpt-4o for now).
        """
        api_key = settings.OPENAI_API_KEY
        client = AsyncOpenAI(api_key=api_key, timeout=60.0)
        return client, "gpt-4o"

# Create a global instance
llm_factory = LLMFactory()
