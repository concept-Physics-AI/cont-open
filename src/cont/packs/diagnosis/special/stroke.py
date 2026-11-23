"""스트로크 부하 곡선 진단: 반복 동작 한 번(스트로크)의 부하 곡선에서 어느 구간이 평소와 다른가.

입력은 (스트로크 수 × 위치 수) 표다. 한 줄이 스트로크 한 번이고, 열은 같은 위치(또는 같은 각도)에서 잰 부하다.
정상 스트로크들로 위치마다 중앙값과 산포를 잡고, 진단할 스트로크가 그 범위를 연속해서 벗어난 구간을 찾는다.
사이클 요약값(최대 부하)만 보는 공통 진단과 달리, 최대값은 같아도 곡선 모양이 달라진 경우를 찾는다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_OBSERVED
from cont.packs.diagnosis.baseline import MAD_TO_SIGMA
from cont.packs.diagnosis.detect import Interval, intervals
from cont.packs.diagnosis.pack import SignalResult
from cont.packs.diagnosis.profile import Settings, load_settings, load_special


@dataclass(frozen=True)
class StrokeDiagnosis:
    answer: PhysicsAnswer
    settings: Settings
    position: np.ndarray
    curve: SignalResult                 # 이상 스트로크들의 평균 곡선(없으면 전체 평균)과 정상 범위. 화면용
    flagged: np.ndarray                 # 스트로크별 이상 여부
    zones: tuple[tuple[str, Interval], ...]   # (구간 이름, 위치 구간)


def diagnose_stroke(normal, current, position=None, special: str = "press", unit: str = "", question: str = "",
                    profile: str | None = None) -> StrokeDiagnosis:
    st = load_settings(profile); sp = load_special(special)
    nm = np.asarray(normal, float); cu = np.asarray(current, float)
    if nm.ndim != 2 or cu.ndim != 2 or nm.shape[1] != cu.shape[1]:
        raise ValueError("normal and current must be 2-D (strokes x positions) with the same number of positions")
    if nm.shape[0] < st.min_samples_per_bin:
        raise ValueError(f"need at least {st.min_samples_per_bin} normal strokes, got {nm.shape[0]}")
    m = nm.shape[1]
    pos = np.arange(m, dtype=float) if position is None else np.asarray(position, float)
    if pos.shape != (m,):
        raise ValueError("position must have one value per column")
    center = np.median(nm, axis=0)
    floor = max(float(np.median(np.abs(center))) * 1e-6, 1e-12)
    scale = np.maximum(np.median(np.abs(nm - center), axis=0) * MAD_TO_SIGMA, floor)
    z = (cu - center) / scale
    per_stroke = [intervals(row, "load", st.z_limit, st.min_run, st.merge_gap) for row in z]
    flagged = np.array([bool(iv) for iv in per_stroke])
    rows = cu[flagged] if flagged.any() else cu
    mean_curve = rows.mean(axis=0)
    mean_z = (mean_curve - center) / scale
    zone_ivs = intervals(mean_z, "load", st.z_limit, st.min_run, st.merge_gap) if flagged.any() else []
    span = float(pos[-1] - pos[0]) or 1.0

    def zone_name(iv: Interval) -> str:
        mid = (float(pos[iv.start] + pos[iv.end]) / 2 - float(pos[0])) / span
        for zdef in sp.stroke_zones:
            if zdef["from"] <= mid <= zdef["to"]:
                return str(zdef["name"])
        return "스트로크 구간"

    zones = tuple((zone_name(iv), iv) for iv in zone_ivs)
    first = int(np.argmax(flagged)) if flagged.any() else None
    quantities = [
        Quantity("strokes_checked", "진단한 스트로크 수", float(len(cu)), "회"),
        Quantity("strokes_flagged", "곡선이 정상 범위를 벗어난 스트로크 수", float(flagged.sum()), "회"),
        Quantity("flagged_fraction", "벗어난 스트로크 비율", float(flagged.mean()), "-"),
        Quantity("first_flagged_stroke", "처음 벗어난 스트로크 번호", None if first is None else float(first), "번째",
                 note=None if first is not None else "벗어난 스트로크가 없다"),
    ]
    basis = [f"특화 진단: {sp.title}, 스트로크 부하 곡선. 정상 스트로크 {len(nm):,}회로 위치 {m}곳마다 중앙값과 산포(MAD)를 잡음",
             f"판정 설정: 정상 산포의 {st.z_limit}배를 위치 {st.min_run}곳 이상 연속해서 벗어나면 그 스트로크를 이상으로 봄 (config/diagnosis, 출발값)"]
    for i, (name, iv) in enumerate(zones):
        dv = float(np.mean(mean_curve[iv.start:iv.end + 1] - center[iv.start:iv.end + 1]))
        word = "높음" if iv.direction == "up" else "낮음"
        quantities.append(Quantity(f"zone{i + 1}_deviation", f"{name}: 평균 부하 차이", dv, unit,
                                   note=f"위치 {pos[iv.start]:.3g}~{pos[iv.end]:.3g}"))
        basis.append(f"벗어난 스트로크 {int(flagged.sum())}회의 평균 곡선이 위치 {pos[iv.start]:.3g}~{pos[iv.end]:.3g}에서 정상보다 평균 "
                     f"{dv:+.3g}{unit} (정상 산포의 {iv.peak_z:+.1f}배까지) {word} → {name}의 가공 부하 이상")
    if not flagged.any():
        basis.append("모든 스트로크의 부하 곡선이 정상 범위 안에 있음")
    elif not zones:
        basis.append("벗어난 스트로크는 있으나 벗어난 위치가 스트로크마다 달라 공통된 구간으로 모이지 않음")
    answer = PhysicsAnswer(status=STATUS_OBSERVED, 
        question=question, quantities=tuple(quantities), method="통계 기준 비교 (스트로크 위치별 정상 부하 곡선 대비 이탈)",
        basis=tuple(basis),
        confidence=Confidence("low", "계산은 가상 곡선으로 확인했지만 현장 데이터로 검증하지 않았고, 구간 이름과 판정 기준값도 현장에서 정한 것이 아니다"),
        presentation=("graph:stroke_curve_vs_normal_band", "table:quantities", "list:evidence"),
        inputs={"special": sp.name, "positions": m, "profile": profile},
    )
    curve = SignalResult("load", "stroke_load", "스트로크 부하 곡선" + (" (벗어난 스트로크의 평균)" if flagged.any() else " (평균)"), unit,
                         mean_curve, center, scale, mean_z, tuple(iv for _, iv in zones), 1.0)
    return StrokeDiagnosis(answer, st, pos, curve, flagged, zones)
