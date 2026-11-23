from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Spectrum:
    freq: np.ndarray        # Hz
    amp: np.ndarray         # 한쪽 진폭 (입력과 같은 단위, 사인파의 진폭이 그대로 나온다)
    fs: float
    resolution: float       # Hz (주파수 간격)


@dataclass(frozen=True)
class Spectrogram:
    time: np.ndarray        # 각 조각의 가운데 시각 (s)
    freq: np.ndarray        # Hz
    amp: np.ndarray         # [주파수, 시간] 한쪽 진폭
    fs: float


@dataclass(frozen=True)
class Distribution:
    edges: np.ndarray
    counts: np.ndarray
    n: int
    mean: float
    std: float
    q1: float
    median: float
    q3: float
    whisker_low: float      # 상자 수염: 1.5 x IQR 안의 가장 작은/큰 값
    whisker_high: float
    outliers: tuple[float, ...]


def _clean(x: np.ndarray, fs: float) -> np.ndarray:
    a = np.asarray(x, dtype=float).ravel()
    if fs <= 0:
        raise ValueError("샘플링 주파수는 0보다 커야 합니다")
    if a.size < 8 or not np.all(np.isfinite(a)):
        raise ValueError("신호가 너무 짧거나 숫자가 아닌 값이 있습니다")
    return a


def spectrum(x: np.ndarray, fs: float, detrend: bool = True) -> Spectrum:
    """한쪽 진폭 스펙트럼 (한(Hann) 창). 사인파를 넣으면 그 진폭이 봉우리 높이로 나온다."""
    a = _clean(x, fs)
    if detrend:
        a = a - a.mean()
    w = np.hanning(a.size)
    amp = 2.0 * np.abs(np.fft.rfft(a * w)) / w.sum()
    amp[0] /= 2.0                                           # 직류 성분은 두 배로 세지 않는다
    return Spectrum(np.fft.rfftfreq(a.size, 1.0 / fs), amp, float(fs), float(fs / a.size))


def peaks(sp: Spectrum, count: int = 5, min_ratio: float = 0.1) -> list[tuple[float, float]]:
    """가장 큰 봉우리 몇 개: (주파수 Hz, 진폭). 가장 큰 봉우리의 min_ratio 배보다 작은 것은 뺀다. 봉우리 사이 보간으로 주파수를 다듬는다."""
    a, f = sp.amp, sp.freq
    top = a.max()
    if top <= 0:
        return []
    idx = [i for i in range(1, a.size - 1) if a[i] > a[i - 1] and a[i] >= a[i + 1] and a[i] >= min_ratio * top]
    idx.sort(key=lambda i: -a[i])
    out = []
    for i in idx[:count]:
        l, c, r = a[i - 1], a[i], a[i + 1]
        den = l - 2 * c + r
        d = 0.5 * (l - r) / den if den else 0.0           # 세 점을 지나는 포물선의 꼭짓점
        out.append((float(f[i] + d * sp.resolution), float(c - 0.25 * (l - r) * d)))
    return out


def spectrogram(x: np.ndarray, fs: float, window: int = 256, overlap: float = 0.5) -> Spectrogram:
    """짧은 구간마다 스펙트럼을 구해 시간에 따른 주파수 변화를 낸다."""
    a = _clean(x, fs)
    window = int(min(window, a.size))
    if not 0 <= overlap < 1:
        raise ValueError("겹침은 0 이상 1 미만이어야 합니다")
    hop = max(1, int(round(window * (1 - overlap))))
    w = np.hanning(window)
    starts = list(range(0, a.size - window + 1, hop))
    cols = []
    for s in starts:
        seg = a[s:s + window]
        seg = seg - seg.mean()
        col = 2.0 * np.abs(np.fft.rfft(seg * w)) / w.sum()
        col[0] /= 2.0
        cols.append(col)
    return Spectrogram(np.array([(s + window / 2) / fs for s in starts]), np.fft.rfftfreq(window, 1.0 / fs), np.array(cols).T, float(fs))


def distribution(values: np.ndarray, bins: int = 12) -> Distribution:
    """값의 분포: 막대 분포(히스토그램)와 상자 그림 값."""
    v = np.asarray(values, dtype=float).ravel()
    if v.size < 4 or not np.all(np.isfinite(v)):
        raise ValueError("값이 너무 적거나 숫자가 아닌 값이 있습니다")
    counts, edges = np.histogram(v, bins=bins)
    q1, med, q3 = (float(x) for x in np.percentile(v, [25, 50, 75]))
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = v[(v >= lo) & (v <= hi)]
    return Distribution(edges, counts, int(v.size), float(v.mean()), float(v.std(ddof=1)), q1, med, q3,
                        float(inside.min()), float(inside.max()), tuple(float(x) for x in np.sort(v[(v < lo) | (v > hi)])))
