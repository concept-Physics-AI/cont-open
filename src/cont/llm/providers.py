"""Built-in provider types.

openai_compatible covers OpenAI, Azure-style gateways, Ollama (/v1), vLLM, OpenRouter,
Upstage, DeepSeek, Groq, xAI ... anything that speaks POST {base_url}/chat/completions.
anthropic and gemini use their official SDKs (optional extras: pip install -e .[anthropic] / .[gemini]).
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from .base import LLMResponse, Message


def _key(env_name: str | None) -> str | None:
    if not env_name:
        return None
    val = os.environ.get(env_name)
    if not val:
        raise RuntimeError(f"API key env var '{env_name}' is not set")
    return val


class OpenAICompatible:
    def __init__(self, name: str, model: str, base_url: str, api_key_env: str | None = None,
                 timeout: float = 120, headers: dict[str, str] | None = None, **_: Any):
        self.name, self.model, self.base_url = name, model, base_url.rstrip("/")
        self.api_key_env, self.timeout, self.headers = api_key_env, timeout, headers or {}

    def complete(self, messages: list[Message], **opts: Any) -> LLMResponse:
        body = {"model": opts.pop("model", self.model),
                "messages": [{"role": m.role, "content": m.content} for m in messages], **opts}
        req = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **self.headers}, method="POST")
        key = _key(self.api_key_env)
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        return LLMResponse(data["choices"][0]["message"]["content"], self.name, body["model"],
                           data.get("usage", {}), data)


class Anthropic:
    def __init__(self, name: str, model: str, api_key_env: str = "ANTHROPIC_API_KEY",
                 max_tokens: int = 4096, **_: Any):
        self.name, self.model, self.api_key_env, self.max_tokens = name, model, api_key_env, max_tokens

    def complete(self, messages: list[Message], **opts: Any) -> LLMResponse:
        import anthropic  # optional extra
        client = anthropic.Anthropic(api_key=_key(self.api_key_env))
        system = "\n".join(m.content for m in messages if m.role == "system") or None
        msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        kw = {"model": opts.pop("model", self.model), "max_tokens": opts.pop("max_tokens", self.max_tokens),
              "messages": msgs, **opts}
        if system:
            kw["system"] = system
        r = client.messages.create(**kw)
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return LLMResponse(text, self.name, kw["model"], dict(r.usage.__dict__) if r.usage else {}, r)


class Gemini:
    def __init__(self, name: str, model: str, api_key_env: str = "GEMINI_API_KEY", **_: Any):
        self.name, self.model, self.api_key_env = name, model, api_key_env

    def complete(self, messages: list[Message], **opts: Any) -> LLMResponse:
        from google import genai  # optional extra
        client = genai.Client(api_key=_key(self.api_key_env))
        system = "\n".join(m.content for m in messages if m.role == "system") or None
        contents = [{"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                    for m in messages if m.role != "system"]
        cfg = {"system_instruction": system, **opts} if system else opts or None
        model = cfg.pop("model", self.model) if cfg else self.model
        r = client.models.generate_content(model=model, contents=contents, config=cfg)
        return LLMResponse(r.text or "", self.name, model, {}, r)


class Echo:
    """Offline stand-in for tests and demos."""

    def __init__(self, name: str = "echo", model: str = "echo", **_: Any):
        self.name, self.model = name, model

    def complete(self, messages: list[Message], **opts: Any) -> LLMResponse:
        return LLMResponse(messages[-1].content if messages else "", self.name, self.model)


BUILTIN_TYPES = {"openai_compatible": OpenAICompatible, "anthropic": Anthropic, "gemini": Gemini, "echo": Echo}
