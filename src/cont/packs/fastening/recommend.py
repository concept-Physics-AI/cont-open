"""설계 추천: 안전율 목표를 주면, 그 목표를 만족하는 규격·강도 등급·조임 토크의 조합을 찾는다.

방법
- 표준 데이터에 있는 규격과 강도 등급을 모두 놓고, 조합마다 조임 토크를 훑어 모든 목표를 만족하는 토크 범위를 찾는다.
  계산은 VDI 2230 식(vdi2230.calculate)을 그대로 쓴다. 새 식이 없다.
- 토크는 그 범위 안에서 지금 토크에 가장 가까운 값으로 잡는다.
- 순서는 "지금 설계에서 가장 적게 바꾸는 것부터"다: 토크만 → 등급까지 → 규격까지, 규격은 가까운 것부터.
  비용이나 무게로 고른 순서가 아니다. 그 기준은 아직 정하지 않았다.

목표는 "어떤 안전율이 얼마 이상"이다. 합격·불합격 기준을 코드가 정하지 않는다. 목표 값은 묻는 사람이 준다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any, Mapping

import yaml

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_GENERATED
from cont.packs.fastening import standards, vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.tolerance import CONFIG_DIR

TARGETS = {
    "safety_yield": "항복 안전율", "safety_opening": "벌어짐 안전율", "safety_slip": "미끄럼 안전율",
    "safety_pressure_head": "면압 안전율 (머리 쪽)", "safety_pressure_nut": "면압 안전율 (너트 쪽)", "safety_fatigue": "피로 안전율",
}
NEEDS = {"safety_opening": "축방향 운전 하중", "safety_slip": "축직각 하중과 판 사이 마찰계수", "safety_pressure_head": "판의 한계 면압",
         "safety_pressure_nut": "판의 한계 면압", "safety_fatigue": "변동하는 축방향 하중"}


@lru_cache(maxsize=1)
def settings() -> dict[str, float]:
    with open(CONFIG_DIR / "fastening" / "default.yaml", encoding="utf-8") as f:
        r = (yaml.safe_load(f) or {})["recommend"]
    return {"show": int(r["show"]), "torque_step": float(r["torque_step"]), "torque_samples": int(r["torque_samples"])}


@dataclass(frozen=True)
class Candidate:
    size: str
    property_class: str
    torque: float               # 추천 토크 (N·m)
    torque_min: float           # 모든 목표를 만족하는 토크 범위
    torque_max: float
    changes: dict[str, Any]     # 지금 설계에서 바꿀 것 (대화의 변경 형식과 같다)
    values: dict[str, float]    # 추천 토크에서의 목표 안전율 값
    joint: BoltedJoint
    load: LoadCase


@dataclass(frozen=True)
class Recommendation:
    answer: PhysicsAnswer
    targets: dict[str, float]
    candidates: tuple[Candidate, ...]       # 적게 바꾸는 순서. 설정의 show개까지
    total: int                              # 목표를 만족하는 조합의 수
    current_ok: bool                        # 지금 설계가 이미 목표를 만족하는가


def _values(joint: BoltedJoint, load: LoadCase, keys: tuple[str, ...]) -> dict[str, float | None]:
    r = vdi2230.calculate(joint, load)
    return {k: getattr(r, k) for k in keys}


def _ok(vals: Mapping[str, float | None], targets: Mapping[str, float]) -> bool:
    return all(vals[k] is not None and vals[k] >= t for k, t in targets.items())


def _torque_range(joint: BoltedJoint, load: LoadCase, targets: Mapping[str, float], near: float) -> tuple[float, float] | None:
    """모든 목표를 만족하는 토크 범위. 범위가 여러 토막이면 near에 가장 가까운 토막."""
    keys = tuple(targets)
    st = settings()

    def good(t: float) -> bool:
        return _ok(_values(joint, replace(load, tightening_torque=t), keys), targets)

    # 위 끝: 조임 중 등가응력이 항복강도에 이르는 토크 (마찰이 가장 작을 때). 그보다 큰 토크는 볼 필요가 없다.
    probe = vdi2230.calculate(joint, replace(load, tightening_torque=1.0))
    top = joint.yield_strength / probe.stress_assembly
    n = st["torque_samples"]
    grid = [top * (i + 1) / n for i in range(n)]
    flags = [good(t) for t in grid]
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if flags[i]:
            j = i
            while j + 1 < n and flags[j + 1]:
                j += 1
            blocks.append((i, j)); i = j + 1
        else:
            i += 1
    if not blocks:
        return None
    a, b = min(blocks, key=lambda ab: 0.0 if grid[ab[0]] <= near <= grid[ab[1]] else min(abs(grid[ab[0]] - near), abs(grid[ab[1]] - near)))

    def edge(bad: float, ok: float) -> float:          # 경계를 이분법으로 좁힌다. 돌려주는 값은 만족하는 쪽이다
        for _ in range(40):
            mid = (bad + ok) / 2
            bad, ok = (bad, mid) if good(mid) else (mid, ok)
        return ok

    if a > 0:
        lo = edge(grid[a - 1], grid[a])
    else:                                              # 훑은 가장 작은 토크부터 만족한다. 아주 작은 토크에서도 만족하면 아래 끝은 0
        tiny = grid[0] / 1e3
        lo = 0.0 if good(tiny) else edge(tiny, grid[0])
    hi = edge(grid[b + 1], grid[b]) if b + 1 < n else grid[b]
    return lo, hi


def _pick(lo: float, hi: float, near: float, step: float) -> float:
    """범위 안에서 near에 가장 가깝고 step 단위에 맞는 토크. 범위가 한 단위보다 좁으면 가운데 값."""
    first, last = math.ceil(lo / step - 1e-9) * step, math.floor(hi / step + 1e-9) * step
    if first > last:
        return (lo + hi) / 2
    return min(max(round(near / step) * step, first), last)


def torque_span(c: Candidate) -> str:
    return f"{c.torque_max:.1f} N·m 이하" if c.torque_min == 0 else f"{c.torque_min:.1f}~{c.torque_max:.1f} N·m"


def recommend(joint: BoltedJoint, load: LoadCase, targets: Mapping[str, float], question: str = "") -> Recommendation:
    targets = {k: float(v) for k, v in targets.items()}
    if not targets:
        raise ValueError("at least one target is required")
    for k, v in targets.items():
        if k not in TARGETS:
            raise ValueError(f"unknown target '{k}' (available: {sorted(TARGETS)})")
        if v <= 0:
            raise ValueError("a target must be positive")
    keys = tuple(targets)
    now = _values(joint, load, keys)
    missing = [k for k in keys if now[k] is None]
    if missing:
        raise ValueError("; ".join(f"{TARGETS[k]}은 {NEEDS[k]}을 주어야 계산한다" for k in missing))
    st = settings()
    sizes, classes = standards.thread_sizes(), standards.property_classes()
    found: list[tuple[tuple, Candidate]] = []; skipped: list[str] = []
    for size in sizes:
        for cls in classes:
            try:
                j = joint if (size, cls) == (joint.size, joint.property_class) else joint.modified(size=size, property_class=cls)
                rng = _torque_range(j, load, targets, load.tightening_torque)
            except ValueError as exc:                      # 이 규격으로는 형상이 성립하지 않는다 (구멍이 바깥지름보다 큼 등)
                skipped.append(f"{size} {cls}: {exc}")
                continue
            if rng is None:
                continue
            t = _pick(rng[0], rng[1], load.tightening_torque, st["torque_step"])
            new_load = replace(load, tightening_torque=t)
            changes: dict[str, Any] = {}
            if size != joint.size:
                changes["size"] = size
            if cls != joint.property_class:
                changes["property_class"] = cls
            if abs(t - load.tightening_torque) > 1e-9:
                changes["tightening_torque"] = t
            vals = {k: float(v) for k, v in _values(j, new_load, keys).items()}
            rank = (size != joint.size, cls != joint.property_class, abs(sizes.index(size) - sizes.index(joint.size)),
                    abs(classes.index(cls) - classes.index(joint.property_class)), abs(t - load.tightening_torque))
            found.append((rank, Candidate(size, cls, t, rng[0], rng[1], changes, vals, j, new_load)))
    found.sort(key=lambda rc: rc[0])
    shown = tuple(c for _, c in found[:st["show"]])
    current_ok = _ok(now, targets)
    goal = ", ".join(f"{TARGETS[k]} {v:g} 이상" for k, v in targets.items())
    basis = [f"목표: {goal}",
             f"표준 데이터의 규격 {len(sizes)}개 × 강도 등급 {len(classes)}개를 모두 놓고, 조합마다 VDI 2230 식으로 목표를 만족하는 조임 토크 범위를 찾음",
             "순서는 지금 설계에서 가장 적게 바꾸는 것부터 (토크만 → 등급 → 규격). 비용·무게로 고른 순서가 아님",
             "지금 설계: " + ", ".join(f"{TARGETS[k]} {now[k]:.2f}" for k in keys) + (" → 이미 목표를 만족함" if current_ok else " → 목표에 못 미침")]
    for i, c in enumerate(shown):
        what = ", ".join({"size": f"규격 {c.size}", "property_class": f"강도 등급 {c.property_class}",
                          "tightening_torque": f"조임 토크 {c.torque:g} N·m"}[k] for k in c.changes) or "바꿀 것 없음"
        basis.append(f"{i + 1}안: {what} (가능한 토크 {torque_span(c)}) → "
                     + ", ".join(f"{TARGETS[k]} {v:.2f}" for k, v in c.values.items()))
    if not found:
        basis.append("표준 데이터에 있는 규격과 등급으로는 어떤 조임 토크에서도 목표를 함께 만족하지 못함. 목표를 낮추거나 하중·마찰·판 조건을 바꿔야 함")
    if skipped:
        basis.append(f"형상이 성립하지 않아 뺀 조합 {len(skipped)}개 (예: {skipped[0]})")
    quantities = [Quantity("candidates", "목표를 만족하는 조합 수", float(len(found)), "개"),
                  Quantity("current_meets_targets", "지금 설계가 목표를 만족하는가", 1.0 if current_ok else 0.0, "1=예, 0=아니오")]
    if shown:
        best = shown[0]
        quantities += [Quantity("recommended_torque", "1안의 조임 토크", best.torque, "N·m", (best.torque_min, best.torque_max)),
                       *[Quantity(f"recommended_{k}", f"1안의 {TARGETS[k]}", v, "-") for k, v in best.values.items()]]
    answer = PhysicsAnswer(status=STATUS_GENERATED, 
        question=question, quantities=tuple(quantities), method="해석식 (VDI 2230 Part 1)으로 조합을 모두 계산해 고름", basis=tuple(basis),
        confidence=Confidence("medium", "계산식은 체결 팩과 같다. 표준 예제·FEM 기준값과의 대조는 아직 하지 않았고, 표준 데이터의 규격·등급 범위 안에서만 찾는다"),
        presentation=("table:candidates",),
        inputs={"targets": targets, "size": joint.size, "property_class": joint.property_class, "tightening_torque": load.tightening_torque},
    )
    return Recommendation(answer, targets, shown, len(found), current_ok)
