"""신호 분석 결과를 FAB 카드의 그림과 사실 목록으로 만든다. 가상 신호 샘플과 올린 파일(내 신호)이 같은 코드를 쓴다."""
from __future__ import annotations

import html
from typing import Any, Sequence

import numpy as np

from cont.signal import Distribution, Spectrogram, Spectrum, peaks
from cont.signal.analysis import Spectrum as _Spectrum

W, H = 320, 190
MAX_POINTS, MAX_ROWS, MAX_COLS = 600, 64, 160       # 그림 하나에 그리는 점·칸의 최대 수 (긴 신호도 가볍게)


def _pool(a: np.ndarray, n: int) -> np.ndarray:
    """앞쪽 축을 n개 이하로 줄인다. 평균이 아니라 최댓값으로 줄여서 좁은 봉우리가 사라지지 않게 한다."""
    if a.shape[0] <= n:
        return a
    edges = np.linspace(0, a.shape[0], n + 1).astype(int)
    return np.stack([a[edges[i]:max(edges[i + 1], edges[i] + 1)].max(axis=0) for i in range(n)])


def _g(v: float) -> str:
    return f"{v:.4g}"


def spectrum_sample(sp: Spectrum, label: str, fmax: float, count: int, min_ratio: float, unit: str, source: str, extra: Sequence[tuple[str, str]] = ()) -> dict[str, Any]:
    from cont.fab.previews import _line
    keep = sp.freq <= fmax
    cut = _Spectrum(sp.freq[keep], sp.amp[keep], sp.fs, sp.resolution)
    top = peaks(cut, count, min_ratio)
    f, a = cut.freq, cut.amp
    if f.size > MAX_POINTS:                                   # 봉우리를 지키려고 구간 최댓값으로 줄인다
        idx = np.linspace(0, f.size, MAX_POINTS + 1).astype(int)
        f = np.array([f[idx[i]:idx[i + 1]][a[idx[i]:idx[i + 1]].argmax()] for i in range(MAX_POINTS)])
        a = _pool(a, MAX_POINTS)
    u = f" {unit}" if unit else ""
    facts = [("봉우리", " · ".join(f"{x:.4g} Hz" for x, _ in sorted(top)) or "뚜렷한 봉우리 없음")] + [(f"{x:.4g} Hz 성분", f"{amp_:.3g}{u}") for x, amp_ in sorted(top)]
    facts += [("주파수 간격", f"{sp.resolution:.3g} Hz"), ("보인 범위", f"0 ~ {cut.freq[-1]:.4g} Hz"), *extra, ("신호", source)]
    svg = _line([(float(x), float(y)) for x, y in zip(f, a)], "Hz", f"진폭{(' ' + unit) if unit else ''}", tuple((x, f"{x:.4g} Hz") for x, _ in top), ".3g")
    return {"label": label, "html": svg, "facts": facts, "params": {}}


def spectrogram_sample(sg: Spectrogram, label: str, fmax: float, window: int, source: str, extra: Sequence[tuple[str, str]] = ()) -> dict[str, Any]:
    keep = sg.freq <= fmax
    amp, fr = sg.amp[keep], sg.freq[keep]
    track = fr[amp.argmax(axis=0)]
    pooled = _pool(_pool(amp, MAX_ROWS).T, MAX_COLS).T         # [주파수, 시간]을 둘 다 줄인다
    top = float(pooled.max()) or 1.0
    rows, cols = pooled.shape
    cw, ch = (W - 60) / cols, (H - 52) / rows
    cells = "".join(f'<rect class="dot" x="{44 + j * cw:.2f}" y="{H - 30 - (i + 1) * ch:.2f}" width="{cw + 0.4:.2f}" height="{ch + 0.4:.2f}" fill-opacity="{pooled[i, j] / top:.2f}"/>'
                    for i in range(rows) for j in range(cols) if pooled[i, j] / top >= 0.05)
    span = sg.time[-1] + window / sg.fs / 2
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="시간별 주파수 변화"><rect x="44" y="22" width="{W - 60}" height="{H - 52}" fill="none" class="ax"/>{cells}'
           f'<text class="tick" x="44" y="{H - 10}">0 s</text><text class="tick" x="{W - 16}" y="{H - 10}" text-anchor="end">{_g(span)} s</text>'
           f'<text class="tick" x="40" y="{H - 30}" text-anchor="end">0</text><text class="tick" x="40" y="30" text-anchor="end">{_g(fr[-1])}</text><text class="tick" x="44" y="14">주파수 Hz · 진할수록 큼</text></svg>')
    facts = [("가장 큰 성분", f"{track[0]:.3g} Hz → {track[-1]:.3g} Hz"), ("구간", f"{sg.time.size}개 · 조각 길이 {window / sg.fs * 1000:.3g} ms"),
             ("주파수 간격", f"{sg.fs / window:.3g} Hz"), *extra, ("신호", source)]
    return {"label": label, "html": svg, "facts": facts, "params": {}}


def distribution_sample(d: Distribution, label: str, unit: str, source: str, extra: Sequence[tuple[str, str]] = ()) -> dict[str, Any]:
    x0, x1 = float(d.edges[0]), float(d.edges[-1])
    for o in d.outliers:
        x0, x1 = min(x0, o), max(x1, o)
    px = lambda v: 44 + (v - x0) / ((x1 - x0) or 1.0) * (W - 60)
    top = int(d.counts.max()) or 1
    bw = (px(d.edges[-1]) - px(d.edges[0])) / len(d.counts)
    bars = "".join(f'<rect class="bar" x="{px(d.edges[0]) + i * bw + 1:.1f}" y="{118 - n / top * 92:.1f}" width="{max(bw - 2, 0.5):.1f}" height="{n / top * 92:.1f}"/>' for i, n in enumerate(d.counts))
    y = 146
    box = (f'<line class="ax" x1="{px(d.whisker_low):.1f}" y1="{y}" x2="{px(d.whisker_high):.1f}" y2="{y}"/><rect class="bar" x="{px(d.q1):.1f}" y="{y - 9}" width="{max(px(d.q3) - px(d.q1), 1):.1f}" height="18"/>'
           f'<line class="ax" x1="{px(d.median):.1f}" y1="{y - 9}" x2="{px(d.median):.1f}" y2="{y + 9}"/>' + "".join(f'<circle class="dot" cx="{px(o):.1f}" cy="{y}" r="2.6"/>' for o in d.outliers))
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="값의 분포"><line class="ax" x1="44" y1="118" x2="{W - 16}" y2="118"/>{bars}{box}'
           f'<text class="tick" x="44" y="{H - 10}">{_g(x0)}</text><text class="tick" x="{W - 16}" y="{H - 10}" text-anchor="end">{html.escape(unit)} {_g(x1)}</text><text class="tick" x="44" y="14">횟수 · 최대 {top}</text></svg>')
    u = f" {unit}" if unit else ""
    facts = [("개수", f"{d.n}개"), ("평균", f"{d.mean:.4g}{u}"), ("표준편차", f"{d.std:.3g}{u}"), ("중앙값", f"{d.median:.4g}{u}"),
             ("벗어난 값", f"{len(d.outliers)}개 (상자 수염 밖)"), *extra, ("값", source)]
    return {"label": label, "html": svg, "facts": facts, "params": {}}
