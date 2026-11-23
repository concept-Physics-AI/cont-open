"""상태 추이: 진단 구간을 토막으로 나눠, 계통마다 토막별로 얼마나 벗어나 있었는지를 본다.

"언제부터, 어느 계통이 먼저, 나아지는가 나빠지는가"를 한눈에 보기 위한 요약이다. 새 판정을 하지 않고 공통 진단의 결과를 다시 센다.
계통마다 시간 열이 달라도(초, 사이클 번호) 같은 기간을 본다고 보고, 구간 안의 상대 위치로 토막을 맞춘다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cont.packs.diagnosis.equipment import EquipmentDiagnosis


@dataclass(frozen=True)
class SystemTrend:
    name: str
    module: str
    fraction: np.ndarray        # 토막별: 이상 구간에 든 표본의 비율 (0~1)
    peak: np.ndarray            # 토막별: 가장 큰 이탈의 크기 (정상 산포의 배수)
    first_window: int | None    # 처음 벗어난 토막 번호
    direction: str              # worsening | easing | steady | normal


@dataclass(frozen=True)
class Trend:
    windows: int
    systems: tuple[SystemTrend, ...]
    order: tuple[str, ...]      # 이상이 먼저 시작된 계통부터


def trend(eq: EquipmentDiagnosis, windows: int | None = None) -> Trend:
    w = windows or eq.systems[0].diagnosis.settings.trend_windows
    if w < 2:
        raise ValueError("windows must be at least 2")
    out: list[SystemTrend] = []; firsts: list[tuple[float, str]] = []
    for s in eq.systems:
        d = s.diagnosis; n = len(d.time)
        flagged = np.zeros(n, dtype=bool); absz = np.zeros(n)
        for r in d.signals:
            absz = np.maximum(absz, np.abs(r.z))
            for iv in r.intervals:
                flagged[iv.start:iv.end + 1] = True
        edges = np.linspace(0, n, w + 1).astype(int)
        frac = np.array([flagged[a:b].mean() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
        peak = np.array([absz[a:b].max() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
        hit = np.flatnonzero(frac > 0)
        first = int(hit[0]) if hit.size else None
        if first is None:
            direction = "normal"
        else:
            half = w // 2
            early, late = float(frac[:half].mean()), float(frac[half:].mean())
            direction = "worsening" if late > early + 0.1 else "easing" if early > late + 0.1 else "steady"
            firsts.append((float(np.argmax(flagged)) / max(n - 1, 1), s.name))
        out.append(SystemTrend(s.name, d.module.title, frac, peak, first, direction))
    return Trend(w, tuple(out), tuple(name for _, name in sorted(firsts)))
