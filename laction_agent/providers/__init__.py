"""Abstraksi LLM provider — model-agnostic seperti Hermes."""
from .base import BaseProvider, Message, ProviderResponse, ToolCall
from .mock import MockProvider
from .openai_compat import OpenAICompatProvider

__all__ = [
    "BaseProvider", "Message", "ProviderResponse", "ToolCall",
    "MockProvider", "OpenAICompatProvider", "create_provider",
]

_DEFAULT_BASES = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
    "nous": "https://inference-api.nousresearch.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


def create_provider(cfg) -> BaseProvider:
    name = (cfg.provider or "mock").lower()
    if name == "mock":
        return MockProvider(model=cfg.model)
    if name in ("openai", "openrouter", "ollama", "nous", "gemini", "openai_compat", "custom"):
        api_base = cfg.api_base or _DEFAULT_BASES.get(name, "")
        if not api_base:
            raise ValueError(
                "LACTION_API_BASE wajib diisi untuk provider custom/openai_compat. "
                "Contoh: https://api.openai.com/v1 atau endpoint Gemini OpenAI-compatible."
            )
        return OpenAICompatProvider(model=cfg.model, api_base=api_base, api_key=cfg.api_key)
    raise ValueError(
        f"Provider tidak dikenal: {name}. Pakai: mock, openai, openrouter, gemini, ollama, nous, custom"
    )
