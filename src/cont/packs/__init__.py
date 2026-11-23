"""물리 팩(physics pack) 등록부.

물리 영역(체결, 절삭가공, 사출 ...)마다 팩 하나. 팩은 입력(dict)을 받아 PhysicsAnswer를 돌려준다.
코어와 화면은 팩 내부를 모르고 이 인터페이스만 쓴다. 영역을 추가할 때는 팩을 새로 만들어 등록한다.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from cont.answer import PhysicsAnswer


class PhysicsPack(Protocol):
    name: str

    def solve(self, inputs: Mapping[str, Any], question: str = "") -> PhysicsAnswer: ...


_REGISTRY: dict[str, PhysicsPack] = {}


def register(pack: PhysicsPack) -> PhysicsPack:
    if pack.name in _REGISTRY:
        raise ValueError(f"physics pack '{pack.name}' is already registered")
    _REGISTRY[pack.name] = pack
    return pack


def get(name: str) -> PhysicsPack:
    if name not in _REGISTRY:
        _load_builtin()
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown physics pack '{name}' (available: {sorted(_REGISTRY)})") from None


def names() -> list[str]:
    _load_builtin()
    return sorted(_REGISTRY)


def _load_builtin() -> None:
    from cont.packs import diagnosis, fastening, machining  # noqa: F401  (등록은 import 시점에 일어난다)
