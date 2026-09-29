"""Pick the LLM provider from environment variables.

LLM_PROVIDER = anthropic | openai | groq | gemini | deepseek
"""
from __future__ import annotations

import os
from functools import lru_cache

from .base import LLM, LLMError, LLMReply, Message, ToolCall, ToolSpec

# provider -> (API key env var, model env var, default model, OpenAI-compatible base URL)
PROVIDERS: dict[str, tuple[str, str, str, str | None]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001", None),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", "", None),
    "groq": ("GROQ_API_KEY", "GROQ_MODEL", "openai/gpt-oss-120b", "https://api.groq.com/openai/v1"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "gemini-3.8-flash",
               "https://generativelanguage.googleapis.com/v1beta/openai/"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek-flash", "https://api.deepseek.com"),
}


def deepseek_options() -> tuple[dict, bool]:
    """DeepSeek thinking mode (DEEPSEEK_THINKING=enabled|disabled, default disabled).

    Off by default: a trivia host doesn't need deep reasoning, and it's cheaper and faster.
    If enabled, DeepSeek requires the reasoning to be sent back on later tool-calling requests.
    """
    thinking = os.getenv("DEEPSEEK_THINKING", "disabled").strip().lower()
    if thinking not in ("enabled", "disabled"):
        raise LLMConfigError("DEEPSEEK_THINKING must be 'enabled' or 'disabled'")
    return {"thinking": {"type": thinking}}, thinking == "enabled"


class LLMConfigError(Exception):
    """Provider, key, or model missing or invalid."""


def provider_settings() -> tuple[str, str, str, str | None]:
    """Return (provider, api_key, model, base_url) from env, or raise LLMConfigError."""
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    if provider not in PROVIDERS:
        raise LLMConfigError(f"LLM_PROVIDER='{provider}' is not one of {', '.join(PROVIDERS)}")
    key_var, model_var, default_model, base_url = PROVIDERS[provider]
    key = os.getenv(key_var, "").strip()
    if len(key) < 20:
        raise LLMConfigError(f"{key_var} is missing or looks like a placeholder")
    model = os.getenv(model_var, "").strip() or default_model
    if not model:
        raise LLMConfigError(f"Set {model_var} in backend/.env")
    return provider, key, model, base_url


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    provider, key, model, base_url = provider_settings()
    if provider == "anthropic":
        from .anthropic_llm import AnthropicLLM
        return AnthropicLLM(api_key=key, model=model)
    from .openai_compat import OpenAICompatLLM
    if provider == "deepseek":
        extra_body, include_reasoning = deepseek_options()
        return OpenAICompatLLM(provider=provider, api_key=key, model=model, base_url=base_url,
                               extra_body=extra_body, include_reasoning=include_reasoning)
    return OpenAICompatLLM(provider=provider, api_key=key, model=model, base_url=base_url)


__all__ = ["LLM", "LLMConfigError", "LLMError", "LLMReply", "Message", "ToolCall", "ToolSpec",
           "get_llm", "provider_settings"]
