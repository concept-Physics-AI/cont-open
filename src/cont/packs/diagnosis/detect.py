"""공통 코어 ② 이상 징후 검출: "현재 신호가 같은 조건의 정상 상태와 다른가?"

표본마다 같은 운전조건 구간의 정상 기준과의 차이를 정상 산포의 배수(z)로 나타내고,
그 차이가 기준(z_limit)을 넘어 일정 길이(min_run) 이상 이어진 구간을 이상 구간으로 본다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cont.packs.diagnosis.baseline import Baseline


@dataclass(frozen=True)
class Interval:
    signal: str
    start: int          # 시작 표본 번호
    end: int            # 끝 표본 번호 (포함)
    direction: str      # up | down
    peak_z: float       # 구간 안에서 가장 큰 이탈 (부호 포함)
    mean_z: float


def score(current: dict[str, np.ndarray], baseline: Baseline, signal: str) -> tuple[np.ndarray, np.ndarray]:
    """표본별 z와, 조건별 기준을 쓴 표본인지 여부."""
    x = np.asarray(current[signal], float)
    center, scale, used = baseline.reference(current, signal)
    return (x - center) / scale, used


def intervals(z: np.ndarray, signal: str, z_limit: float, min_run: int, merge_gap: int) -> list[Interval]:
    out: list[Interval] = []
    for sign, direction in ((1, "up"), (-1, "down")):
        idx = np.flatnonzero(sign * z > z_limit)
        if idx.size == 0:
            continue
        runs = []; start = prev = int(idx[0])
        for i in idx[1:].tolist():
            if i - prev - 1 > merge_gap:
                runs.append((start, prev)); start = i
            prev = i
        runs.append((start, prev))
        for a, b in runs:
            if int(np.count_nonzero(sign * z[a:b + 1] > z_limit)) >= min_run:
                seg = z[a:b + 1]
                out.append(Interval(signal, a, b, direction, float(seg[np.argmax(sign * seg)]), float(seg.mean())))
    return sorted(out, key=lambda i: i.start)
