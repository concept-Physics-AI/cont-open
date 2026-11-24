"""현재 상태와 최근 대화를 공급자 입력으로 묶는다. 물리값을 계산하지 않는다."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

import yaml

from cont.llm import Message
from cont.tolerance import CONFIG_DIR


@dataclass(frozen=True)
class ContextLimits:
    history_turns: int
    max_context_chars: int

    def __post_init__(self) -> None:
        if type(self.history_turns) is not int or self.history_turns < 0:
            raise ValueError("history_turns must be a non-negative integer")
        if type(self.max_context_chars) is not int or self.max_context_chars < 1:
            raise ValueError("max_context_chars must be a positive integer")


@lru_cache(maxsize=1)
def configured_limits() -> ContextLimits:
    data = yaml.safe_load((CONFIG_DIR / "dialogue.yaml").read_text(encoding="utf-8"))
    return ContextLimits(**data)


def build_messages(
    instruction: str,
    current_state: str,
    history: Sequence[tuple[str, str]],
    question: str,
    limits: ContextLimits,
) -> list[Message]:
    """현재 질문·상태는 유지하고 과거 대화는 완전한 왕복 단위로 제한한다.

    글자 예산이며 공급자별 토큰 수를 보장하지 않는다. 최근 왕복 하나가
    남은 예산보다 크면 더 오래된 이력도 넣지 않아 연속된 꼬리만 보낸다.
    """
    fixed = [Message("system", instruction), Message("system", current_state)]
    remaining = limits.max_context_chars - sum(len(m.content) for m in fixed) - len(question)
    if remaining < 0:
        raise ValueError("current question and state exceed context budget")
    selected: list[tuple[str, str]] = []
    if limits.history_turns:
        for user, assistant in reversed(history[-limits.history_turns:]):
            size = len(user) + len(assistant)
            if size > remaining:
                break
            selected.append((user, assistant))
            remaining -= size
    messages = list(fixed)
    for user, assistant in reversed(selected):
        messages.extend((Message("user", user), Message("assistant", assistant)))
    messages.append(Message("user", question))
    return messages
