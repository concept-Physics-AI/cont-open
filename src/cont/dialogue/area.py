"""Studio가 질문의 물리 영역을 알아본다. 모르면 추측하지 않는다 (config/dialogue/areas.yaml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_CFG = Path(__file__).resolve().parents[3] / "config" / "dialogue" / "areas.yaml"


@dataclass(frozen=True)
class Area:
    key: str
    name: str
    chat: bool
    note: str


def _areas() -> list[dict[str, Any]]:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8"))["areas"]


def detect(text: str) -> Area | None:
    """질문에서 키워드가 가장 많이 나온 영역. 키워드가 없거나 동점이면 None (추측하지 않는다)."""
    hits = [(sum(1 for k in a["keywords"] if k in text), a) for a in _areas()]
    best = max(h for h, _ in hits)
    top = [a for h, a in hits if h == best]
    if best == 0 or len(top) != 1:
        return None
    a = top[0]
    return Area(a["key"], a["name"], bool(a.get("chat")), a.get("note", ""))


def not_ready_reply(area: Area) -> str:
    """대화로 아직 다루지 못하는 영역의 질문에 하는 정직한 답."""
    return (f"{area.name}에 대한 질문으로 보입니다. {area.note}. 지금 Studio 대화는 체결만 다룰 수 있어서 계산하지 않았습니다. "
            "체결(볼트 조인트)에 대해 물어봐 주세요.")
