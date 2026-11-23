from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Message:
    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class Provider(Protocol):
    name: str
    model: str

    def complete(self, messages: list[Message], **opts: Any) -> LLMResponse: ...
