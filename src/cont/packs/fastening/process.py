"""조이는 과정: 조임 토크를 0에서 지금 값까지 나눠, 토크마다 같은 계산식으로 다시 계산한다.

시간에 따른 거동의 해석이 아니다. 조이는 동안의 마찰 변화, 속도, 조인 뒤의 풀림은 담지 않는다.
운전 하중이 걸리기 전(조립 시)의 값만 낸다. 토크 0에서는 체결력이 0이다 (식이 토크에 비례한다).
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any

import yaml

from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.pack import answer
from cont.tolerance import CONFIG_DIR


@lru_cache(maxsize=1)
def settings() -> dict[str, float]:
    with open(CONFIG_DIR / "fastening" / "default.yaml", encoding="utf-8") as f:
        p = (yaml.safe_load(f) or {})["process"]
    return {"steps": int(p["steps"]), "play_seconds": float(p["play_seconds"])}


def tightening(joint: BoltedJoint, load: LoadCase, steps: int | None = None) -> list[dict[str, Any]]:
    """토크 0 → 지금 토크. 한 칸: torque(N·m), preload(N), stress(조립 시 등가응력 MPa), use(응력 ÷ 항복강도), elongation(볼트 늘어남 mm)."""
    n = steps or settings()["steps"]
    if n < 1:
        raise ValueError("steps must be at least 1")
    frames: list[dict[str, Any]] = [{"torque": 0.0, "preload": 0.0, "stress": 0.0, "use": 0.0, "elongation": 0.0}]
    for i in range(1, n + 1):
        torque = load.tightening_torque * i / n
        a = answer(joint, replace(load, tightening_torque=torque))
        preload, stress = a.value("preload"), a.value("bolt_equivalent_stress_assembly")
        frames.append({"torque": torque, "preload": preload, "stress": stress, "use": stress / joint.yield_strength,
                       "elongation": preload * a.value("bolt_resilience")})
    return frames
