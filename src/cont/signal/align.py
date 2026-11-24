"""센서 시간 정렬(R08). 불규칙한 시각을 일정한 간격으로 맞추되, 건너뛴 구간은 값을 지어내지 않고 비워 둔다."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


class AlignError(ValueError):
    pass


@dataclass(frozen=True)
class Aligned:
    t: np.ndarray
    values: np.ndarray                  # 칸이 비면 NaN
    filled: np.ndarray                  # 결측으로 비운 칸 표시
    report: dict = field(default_factory=dict)


def check_time(t, on_duplicate: str = "reject", on_reverse: str = "reject") -> tuple[np.ndarray, np.ndarray, dict]:
    """시각 열 검사. 반환은 (정리된 시각, 원래 줄 번호, 보고). 기본은 문제가 있으면 거절한다.

    on_reverse="sort"이면 정렬, on_duplicate="mean"이면 같은 시각 값을 평균하도록 인덱스를 돌려준다.
    """
    t = np.asarray(t, dtype=float)
    if t.ndim != 1 or t.size < 2:
        raise AlignError("시각이 두 개 이상 필요합니다")
    if not np.all(np.isfinite(t)):
        raise AlignError("시각에 NaN 또는 무한대가 있습니다")
    idx = np.arange(t.size)
    rep = {"reversed": int(np.sum(np.diff(t) < 0)), "duplicates": 0}
    if rep["reversed"]:
        if on_reverse != "sort":
            raise AlignError(f"시각이 거꾸로 가는 곳이 {rep['reversed']}군데 있습니다 (정렬하려면 on_reverse='sort')")
        idx = np.argsort(t, kind="stable"); t = t[idx]
    dup = np.diff(t) == 0
    rep["duplicates"] = int(dup.sum())
    if rep["duplicates"] and on_duplicate != "mean":
        raise AlignError(f"같은 시각이 {rep['duplicates']}번 반복됩니다 (평균하려면 on_duplicate='mean')")
    return t, idx, rep


def regularize(t, y, dt: float, max_gap: float, on_duplicate: str = "reject", on_reverse: str = "reject") -> Aligned:
    """간격 dt(초)의 일정한 격자로 선형 보간한다. 인접한 관측 사이가 max_gap(초)을 넘으면 그 사이 격자 칸은 비운다(NaN)."""
    if not (dt > 0 and max_gap > 0):
        raise AlignError("dt와 max_gap은 0보다 커야 합니다")
    y = np.asarray(y, dtype=float)
    if y.shape[0] != np.asarray(t).shape[0]:
        raise AlignError("시각과 값의 개수가 다릅니다")
    if not np.all(np.isfinite(y)):
        raise AlignError("값에 NaN 또는 무한대가 있습니다 (조용히 건너뛰지 않습니다)")
    ts, idx, rep = check_time(t, on_duplicate, on_reverse)
    ys = y[idx]
    if rep["duplicates"]:
        uniq, inv = np.unique(ts, return_inverse=True)
        ys = np.bincount(inv, weights=ys) / np.bincount(inv)
        ts = uniq
    n = int(np.floor((ts[-1] - ts[0]) / dt + 1e-9)) + 1
    grid = ts[0] + dt * np.arange(n)
    vals = np.interp(grid, ts, ys)
    gaps = np.diff(ts)
    where = np.searchsorted(ts, grid, side="right") - 1
    where = np.clip(where, 0, gaps.size - 1)
    exact = np.isin(grid, ts)
    empty = (gaps[where] > max_gap) & ~exact
    vals[empty] = np.nan
    rep.update(grid_points=int(n), emptied=int(empty.sum()), longest_gap_s=float(gaps.max()), dt_s=float(dt), max_gap_s=float(max_gap),
               irregularity=float(np.max(np.abs(gaps - np.median(gaps))) / np.median(gaps)))
    return Aligned(grid, vals, empty, rep)


def compare_before_after(t, y, aligned: Aligned) -> dict:
    """맞추기 전후 비교: 평균·최댓값·최솟값 변화와 비운 비율. 판정하지 않는다."""
    y = np.asarray(y, dtype=float); v = aligned.values[~aligned.filled]
    return {"mean_before": float(y.mean()), "mean_after": float(v.mean()), "max_before": float(y.max()), "max_after": float(v.max()),
            "min_before": float(y.min()), "min_after": float(v.min()), "emptied_fraction": float(aligned.filled.mean()), "judged": False}
