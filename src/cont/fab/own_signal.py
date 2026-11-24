"""올린 CSV(내 신호)를 신호 분석 엔진에 넣어 FAB 카드 하나(샘플)로 돌려준다. 파일은 저장하지 않는다."""
from __future__ import annotations

from typing import Any, Mapping

from cont.signal import distribution, peaks, spectrogram, spectrum
from cont.signal.csvio import parse_table, sampling

MIN_WAVE, MIN_VALUES, MAX_JITTER, WARN_JITTER = 64, 10, 0.10, 0.01
SOURCE = "올린 파일 (내 자료, 검증하지 않음)"


def _pick(n: int, i: Any, what: str) -> int:
    try:
        k = int(i)
    except (TypeError, ValueError):
        raise ValueError(f"{what}을(를) 골라 주세요") from None
    if not 0 <= k < n:
        raise ValueError(f"{what}이(가) 범위를 벗어났습니다")
    return k


def _window(n: int) -> int:
    w = 1 << max(6, (max(n // 100, 1) - 1).bit_length())          # 조각 수가 200개쯤 되게
    w = min(w, 4096)
    while w > n:
        w //= 2
    return w


def analyze(mode: str, p: Mapping[str, Any]) -> dict[str, Any]:
    """mode: 'spectrum', 'spectrogram', 'values'. 카드 샘플(dict)을 돌려준다. 못 읽으면 ValueError(사용자에게 보일 이유)."""
    from cont.fab.signal_views import distribution_sample, spectrogram_sample, spectrum_sample
    t = parse_table(str(p.get("csv", "")))
    col = _pick(len(t.names), p.get("column"), "값 열")
    x = t.columns[col]
    unit = str(p.get("unit") or "").strip()[:16]
    name = str(p.get("filename") or "내 파일").strip()[:60] or "내 파일"
    label = f"내 신호 · {name}"
    head = [("파일", name), ("열", t.names[col]), ("개수", f"{x.size:,}개")]
    if mode == "values":
        if x.size < MIN_VALUES:
            raise ValueError(f"값이 {MIN_VALUES}개 이상 있어야 분포를 볼 수 있습니다 (지금 {x.size}개)")
        s = distribution_sample(distribution(x, 12), label, unit, SOURCE, head[:2], observed=True)
    elif mode in ("spectrum", "spectrogram"):
        if x.size < MIN_WAVE:
            raise ValueError(f"값이 {MIN_WAVE}개 이상 있어야 주파수를 볼 수 있습니다 (지금 {x.size}개)")
        tcol = int(p.get("time_column", -1) if p.get("time_column") not in (None, "") else -1)
        warn: list[tuple[str, str]] = []
        if tcol >= 0:
            tcol = _pick(len(t.names), tcol, "시간 열")
            if tcol == col:
                raise ValueError("값 열과 시간 열이 같습니다")
            fs, jit = sampling(t.columns[tcol])
            if jit > MAX_JITTER:
                raise ValueError(f"샘플 간격이 일정하지 않습니다 (중앙 간격보다 최대 {jit * 100:.0f}% 벗어남). 일정한 간격으로 맞춘 파일을 올려 주세요")
            if jit > WARN_JITTER:
                warn.append(("간격 흔들림", f"최대 {jit * 100:.1f}% (결과가 조금 흐려질 수 있음)"))
            head.append(("시간 열", f"{t.names[tcol]} (초 단위로 읽음)"))
        else:
            try:
                fs = float(p.get("fs"))
            except (TypeError, ValueError):
                raise ValueError("시간 열을 고르거나 샘플링 주파수(Hz)를 적어 주세요") from None
            if not fs > 0:
                raise ValueError("샘플링 주파수는 0보다 커야 합니다")
        head += [("샘플링 주파수", f"{fs:.6g} Hz"), ("신호 길이", f"{x.size / fs:.4g} 초")] + warn
        try:
            given = float(p.get("fmax")) if p.get("fmax") not in (None, "") else 0.0
        except (TypeError, ValueError):
            raise ValueError("표시 주파수 상한은 숫자로 적어 주세요") from None
        fmax = min(given, fs / 2) if given > 0 else fs / 2
        if given <= 0:                                       # 상한을 안 적으면 가장 높은 뚜렷한 봉우리의 1.6배까지만 보인다 (봉우리가 보이게)
            top = peaks(spectrum(x, fs), 5, 0.1)
            if top:
                fmax = min(fs / 2, 1.6 * max(f for f, _ in top))
        if mode == "spectrum":
            s = spectrum_sample(spectrum(x, fs), label, fmax, 5, 0.1, unit, SOURCE, head, observed=True)
        else:
            w = _window(x.size)
            s = spectrogram_sample(spectrogram(x, fs, window=w, overlap=0.5), label, fmax, w, SOURCE, head, observed=True)
    else:
        raise ValueError("이 카드는 내 신호를 받지 않습니다")
    s["own"] = True
    return s
