"""One door for every LLM (external API or in-house model).

Other modules call only:  get_provider().complete(messages)
Provider list lives in config/llm/providers.yaml (+ providers.local.yaml, not in git).
Pick one with CONT_LLM_PROVIDER=<name>. API keys are read from the env var named in the config.
"""
from .base import LLMResponse, Message, Provider
from .registry import get_provider, list_providers, register_type

__all__ = ["LLMResponse", "Message", "Provider", "get_provider", "list_providers", "register_type"]
