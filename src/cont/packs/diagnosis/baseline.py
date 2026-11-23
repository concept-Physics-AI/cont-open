"""공통 코어 ① 정상 운전 패턴 분석: "이 조건에서 평소 어떻게 운전했는가?"

정상 기준은 두 단계로 잡는다.
 1) 신호를 운전조건(부하, 속도 등)의 1차식으로 맞춘다. 조건이 연속으로 변해도 기준이 따라간다.
 2) 남은 차이(잔차)를 조건 구간별로 나눠 구간마다 중앙값과 산포(MAD)를 둔다.
    1차식으로 설명되지 않는 굽은 관계와, 조건에 따라 달라지는 산포를 여기서 반영한다.
평균·표준편차 대신 중앙값·MAD를 쓰는 이유는 정상 데이터에 섞인 튀는 값에 기준이 끌려가지 않게 하기 위해서다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAD_TO_SIGMA = 1.4826  # 정규분포에서 MAD를 표준편차로 바꾸는 계수
OUTLIER_CUT = 5.0      # 1차식을 다시 맞출 때 제외하는 잔차 (산포의 배수). 기준값이 아니라 맞춤 절차의 일부다.


@dataclass(frozen=True)
class Baseline:
    signals: tuple[str, ...]
    conditions: tuple[str, ...]
    coef: dict[str, np.ndarray]               # 신호별 [절편, 조건1 계수, 조건2 계수, ...]
    edges: dict[str, np.ndarray]              # 조건별 구간 경계 (안쪽 경계만)
    offset: dict[tuple, dict[str, float]]     # (구간 번호들) → 신호별 잔차 중앙값
    scale: dict[tuple, dict[str, float]]      # (구간 번호들) → 신호별 잔차 산포
    count: dict[tuple, int]
    global_scale: dict[str, float]
    min_samples: int

    def _design(self, data: dict[str, np.ndarray]) -> np.ndarray:
        n = len(next(iter(data.values())))
        return np.column_stack([np.ones(n)] + [np.asarray(data[c], float) for c in self.conditions])

    def bin_of(self, data: dict[str, np.ndarray]) -> np.ndarray:
        """각 표본이 속한 조건 구간 번호. 모양: (표본 수, 조건 수)."""
        n = len(next(iter(data.values())))
        if not self.conditions:
            return np.zeros((n, 0), dtype=int)
        return np.stack([np.searchsorted(self.edges[c], np.asarray(data[c], float), side="right")
                         for c in self.conditions], axis=1)

    def reference(self, data: dict[str, np.ndarray], signal: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """표본마다 적용할 정상 기대값, 산포, 그리고 구간별 기준을 썼는지(False면 전체 산포)."""
        bins = self.bin_of(data)
        n = bins.shape[0]
        center = self._design(data) @ self.coef[signal]
        scale = np.full(n, self.global_scale[signal]); used = np.zeros(n, dtype=bool)
        for key in {tuple(r) for r in bins.tolist()}:
            if self.count.get(key, 0) >= self.min_samples:
                m = np.all(bins == np.array(key, dtype=int), axis=1) if key else np.ones(n, dtype=bool)
                center[m] += self.offset[key][signal]; scale[m] = self.scale[key][signal]; used[m] = True
        return center, scale, used


def _robust(x: np.ndarray, floor: float) -> tuple[float, float]:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * MAD_TO_SIGMA
    return med, max(mad, floor)


def fit(normal: dict[str, np.ndarray], signals: list[str], conditions: list[str],
        bins_per_condition: int, min_samples_per_bin: int) -> Baseline:
    data = {k: np.asarray(v, float) for k, v in normal.items()}
    for k in list(signals) + list(conditions):
        if k not in data:
            raise ValueError(f"normal data has no column '{k}'")
    n = len(data[signals[0]])
    if n == 0:
        raise ValueError("normal data is empty")
    if any(len(data[k]) != n for k in list(signals) + list(conditions)):
        raise ValueError("all columns must have the same length")
    x = np.column_stack([np.ones(n)] + [data[c] for c in conditions])
    qs = np.linspace(0, 1, bins_per_condition + 1)[1:-1]
    edges = {c: np.unique(np.quantile(data[c], qs)) for c in conditions}
    bins = (np.stack([np.searchsorted(edges[c], data[c], side="right") for c in conditions], axis=1)
            if conditions else np.zeros((n, 0), dtype=int))
    keys = {tuple(r) for r in bins.tolist()}
    coef: dict[str, np.ndarray] = {}; gscale: dict[str, float] = {}
    offset: dict[tuple, dict[str, float]] = {k: {} for k in keys}; scale: dict[tuple, dict[str, float]] = {k: {} for k in keys}
    count = {k: int((np.all(bins == np.array(k, dtype=int), axis=1) if k else np.ones(n, dtype=bool)).sum()) for k in keys}
    for s in signals:
        y = data[s]
        floor = max(float(np.median(np.abs(y))) * 1e-6, 1e-12)  # 거의 변하지 않는 신호에서 0으로 나누지 않도록
        beta = np.linalg.lstsq(x, y, rcond=None)[0]
        r = y - x @ beta
        med, sig = _robust(r, floor)
        keep = np.abs(r - med) <= OUTLIER_CUT * sig
        if keep.sum() >= x.shape[1] + 1:
            beta = np.linalg.lstsq(x[keep], y[keep], rcond=None)[0]
            r = y - x @ beta
        coef[s] = beta
        gscale[s] = _robust(r, floor)[1]
        for k in keys:
            m = np.all(bins == np.array(k, dtype=int), axis=1) if k else np.ones(n, dtype=bool)
            offset[k][s], scale[k][s] = _robust(r[m], floor)
    return Baseline(tuple(signals), tuple(conditions), coef, edges, offset, scale, count, gscale, min_samples_per_bin)
