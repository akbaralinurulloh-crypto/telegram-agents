from app.config import AppConfig, Settings
from app.llm.anthropic import AnthropicClient
from app.llm.base import LLMClient
from app.llm.gemini import GeminiClient


def build_llm(settings: Settings, cfg: AppConfig) -> LLMClient:
    c = cfg.llm
    if c.provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError(".env da GEMINI_API_KEY yo'q (config.yaml: llm.provider=gemini)")
        return GeminiClient(settings.gemini_api_key, c.gemini_model, fallback_models=c.gemini_fallback_models, timeout=c.timeout_seconds, max_retries=c.max_retries)
    if not settings.anthropic_api_key:
        raise RuntimeError(".env da ANTHROPIC_API_KEY yo'q (config.yaml: llm.provider=anthropic)")
    return AnthropicClient(settings.anthropic_api_key, c.anthropic_model, timeout=c.timeout_seconds, max_retries=c.max_retries)
