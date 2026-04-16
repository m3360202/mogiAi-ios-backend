"""
Centralized LiteLLM client wrapper.

Why:
- This repo supports switching non-visual LLM provider (e.g., OpenAI -> DeepSeek).
- Many evaluation services call `litellm.acompletion()` directly. When the provider
  is DeepSeek, calling LiteLLM with `model="deepseek-chat"` will fail because LiteLLM
  needs either a provider-prefixed model name (`deepseek/deepseek-chat`) and/or the
  correct `api_key` + `base_url`.

This module makes that routing consistent across all evaluation services.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import litellm

from app.core.config import settings
from app.core.llm_factory import llm_factory


def _normalize_litellm_model(provider: str, model: str) -> str:
    """
    Convert provider/model into a LiteLLM-compatible model string.
    For DeepSeek, LiteLLM expects "deepseek/<model>".
    """
    if provider == "deepseek":
        # If user already provided a provider prefix, keep it.
        if "/" in model:
            return model
        return f"deepseek/{model}"
    return model


def _get_non_visual_litellm_overrides(requested_model: str) -> tuple[str, Dict[str, Any]]:
    """
    Decide which model + credentials to use for NON-VISUAL LiteLLM calls.

    Important design choice:
    - When non_visual_model_provider is set (e.g., deepseek), we route *all*
      LiteLLM calls in the evaluation pipeline through that provider, regardless
      of the model strings stored in `evaluation_strategies.json` (which still
      reference OpenAI model names like gpt-4o-mini).
    """
    conf = llm_factory.get_non_visual_config()
    provider = conf.get("provider", "openai")

    # Default: keep the requested model, but still pass OPENAI key explicitly for robustness.
    if provider == "openai":
        overrides: Dict[str, Any] = {}
        if settings.OPENAI_API_KEY:
            overrides["api_key"] = settings.OPENAI_API_KEY
        # Allow optional base_url override if configured (rare).
        if conf.get("base_url"):
            overrides["base_url"] = conf["base_url"]
        return requested_model, overrides

    # DeepSeek: force DeepSeek routing for non-visual evaluation calls.
    if provider == "deepseek":
        model = _normalize_litellm_model(provider, conf.get("model", "deepseek-chat"))
        overrides = {}
        if settings.DEEPSEEK_API_KEY:
            overrides["api_key"] = settings.DEEPSEEK_API_KEY
        if conf.get("base_url"):
            overrides["base_url"] = conf["base_url"]
        return model, overrides

    # Unknown provider: fall back to requested model without overrides.
    return requested_model, {}


async def acompletion(
    *,
    model: str,
    messages: List,
    temperature: Optional[float] = None,
    response_format: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
):
    """
    Wrapper around `litellm.acompletion` used by evaluation services.
    Applies non-visual provider overrides (DeepSeek/OpenAI) consistently.
    """
    effective_model, overrides = _get_non_visual_litellm_overrides(model)
    merged_kwargs = {**overrides, **kwargs}
    return await litellm.acompletion(
        model=effective_model,
        messages=messages,
        temperature=temperature,
        response_format=response_format,
        **merged_kwargs,
    )


