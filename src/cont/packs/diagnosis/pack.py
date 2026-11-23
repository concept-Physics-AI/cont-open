"""진단 물리 팩 (공통 이상진단): 입력(dict) → 정상 기준 → 이탈 검출 → 상태 변화 유형 → PhysicsAnswer.

공통 이상진단: 설비 이름과 무관하게 구성요소(구동계 등)에 대해 "같은 운전조건의 평소와 다른가,
다르다면 어떤 변화인가"를 답한다. 공정별 해석(공구 파손, 두께 예측 등)은 특화 진단으로 따로 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_OBSERVED
from cont.packs.diagnosis import baseline as bl
from cont.packs.diagnosis import detect
from cont.packs.diagnosis.profile import Module, Settings, load_module, load_settings


@dataclass(frozen=True)
class SignalResult:
    column: str
    role: str
    label: str
    unit: str
    value: np.ndarray
    center: np.ndarray      # 같은 조건의 정상 중앙값
    scale: np.ndarray       # 같은 조건의 정상 산포
    z: np.ndarray
    intervals: tuple[detect.Interval, ...]
    conditioned_fraction: float   # 조건별 기준을 쓴 표본 비율 (나머지는 전체 기준)


@dataclass(frozen=True)
class Diagnosis:
    """답변 묶음과, 화면이 그림을 그리는 데 쓰는 신호별 상세."""
    answer: PhysicsAnswer
    module: Module
    settings: Settings
    time: np.ndarray
    signals: tuple[SignalResult, ...]


def diagnose(module: str, normal: Mapping[str, Any], current: Mapping[str, Any],
             signals: Mapping[str, str], conditions: Mapping[str, str] | None = None,
             time: str | None = None, question: str = "", profile: str | None = None) -> Diagnosis:
    """signals, conditions: 현장 열 이름 → 모듈의 역할 이름 (현장 적응: 태그 연결)."""
    mod = load_module(module); st = load_settings(profile)
    conditions = dict(conditions or {})
    for col, role in signals.items():
        if role not in mod.roles:
            raise ValueError(f"'{role}' is not a signal role of module '{module}' (roles: {sorted(mod.roles)})")
    for col, role in conditions.items():
        if role not in mod.conditions:
            raise ValueError(f"'{role}' is not a condition of module '{module}' (conditions: {sorted(mod.conditions)})")
    nd = {k: np.asarray(v, float) for k, v in normal.items()}
    cd = {k: np.asarray(v, float) for k, v in current.items()}
    for col in list(signals) + list(conditions):
        if col not in cd:
            raise ValueError(f"current data has no column '{col}'")
    base = bl.fit(nd, list(signals), list(conditions), st.bins_per_condition, st.min_samples_per_bin)
    n = len(cd[next(iter(signals))])
    tt = cd[time] if time else np.arange(n, dtype=float)
    results: list[SignalResult] = []; quantities: list[Quantity] = []; evidence: list[str] = []
    for col, role in signals.items():
        z, used = detect.score(cd, base, col)
        center, scale, _ = base.reference(cd, col)
        ivs = tuple(detect.intervals(z, col, st.z_limit, st.min_run, st.merge_gap))
        info = mod.roles[role]
        results.append(SignalResult(col, role, info.get("label", role), info.get("unit", ""), cd[col], center, scale, z, ivs,
                                    float(used.mean())))
        peak = float(z[np.argmax(np.abs(z))])
        quantities.append(Quantity(f"deviation_{col}", f"{info.get('label', role)} 최대 이탈", peak, "정상 산포의 배수",
                                   (-st.z_limit, st.z_limit)))
        for iv in ivs:
            ct = mod.change_type(role, iv.direction)
            where = f"{tt[iv.start]:g}~{tt[iv.end]:g}"
            dv = float(np.mean(cd[col][iv.start:iv.end + 1] - center[iv.start:iv.end + 1]))
            name = ct.label if ct else f"{info.get('label', role)} {'상승' if iv.direction == 'up' else '하락'}"
            evidence.append(f"{info.get('label', role)}({col}) 값이 {where} 구간에서 같은 운전조건의 정상보다 평균 "
                            f"{dv:+.3g}{info.get('unit', '')} (정상 산포의 {iv.peak_z:+.1f}배까지) 벗어남 → {name}")
    flagged = np.zeros(n, dtype=bool)
    found: dict[str, tuple[str, float]] = {}
    for r in results:
        for iv in r.intervals:
            flagged[iv.start:iv.end + 1] = True
            ct = mod.change_type(r.role, iv.direction)
            if ct and (ct.key not in found or abs(iv.peak_z) > abs(found[ct.key][1])):
                found[ct.key] = (ct.label, iv.peak_z)
    quantities.append(Quantity("anomaly_intervals", "이상 구간 수", float(sum(len(r.intervals) for r in results)), "개"))
    quantities.append(Quantity("anomaly_fraction", "이상 구간이 차지하는 비율", float(flagged.mean()), "-"))
    first = min((iv.start for r in results for iv in r.intervals), default=None)
    quantities.append(Quantity("first_anomaly_time", "첫 이상 시각", None if first is None else float(tt[first]), "시간 열의 단위",
                               note=None if first is not None else "이상 구간이 없다"))
    for key, (label, peak) in found.items():
        quantities.append(Quantity(f"change_{key}", label, float(peak), "정상 산포의 배수"))
    cond_txt = ", ".join(f"{c}({mod.conditions[r].get('label', r)})" for c, r in conditions.items()) or "없음"
    basis = (
        f"공통 진단 모듈: {mod.title}. 정상 기준은 신호를 운전조건 [{cond_txt}]의 1차식으로 맞추고, 남은 차이를 조건 구간별 중앙값과 산포(MAD)로 잡음",
        f"판정 설정: 이탈 기준 정상 산포의 {st.z_limit}배, 연속 {st.min_run}표본 이상, 조건 구간 {st.bins_per_condition}개 "
        f"(config/diagnosis, 현장 검증 전의 출발값)",
        f"정상 표본 {len(nd[next(iter(signals))]):,}개, 진단 표본 {n:,}개",
    ) + (tuple(evidence) if evidence else ("모든 신호가 같은 운전조건의 정상 범위 안에 있음",))
    answer = PhysicsAnswer(status=STATUS_OBSERVED, 
        question=question,
        quantities=tuple(quantities),
        method="통계 기준 비교 (운전조건별 정상 패턴 대비 이탈)",
        basis=basis,
        confidence=Confidence("low", "계산은 가상 신호로 확인했지만 현장 데이터로 검증하지 않았고, 판정 기준값도 현장에서 정한 값이 아니다"),
        presentation=("graph:signal_vs_normal_band", "table:quantities", "list:evidence"),
        inputs={"module": module, "signals": dict(signals), "conditions": conditions, "time": time, "profile": profile},
    )
    return Diagnosis(answer, mod, st, tt, tuple(results))


class DiagnosisPack:
    name = "diagnosis"

    def solve(self, inputs: Mapping[str, Any], question: str = "") -> PhysicsAnswer:
        """계통 하나: {"module": "drive", "normal": {열: 값들}, "current": {열: 값들},
                       "signals": {열: 역할}, "conditions": {열: 역할}, "time": 열 이름(선택)}
        설비 한 대:  {"equipment": 이름, "systems": [위와 같은 항목에 "name"을 더한 것, ...]}
        특화 진단:   {"special": "cutting", "systems": [...]}                        공통 진단 결과를 공정의 말로 해석
                     {"task": "guide", "systems": [...], "special": 공정(선택)}          원인 후보와 점검 안내
                     {"task": "stroke", "normal": 표, "current": 표, "position": 값들}  스트로크 부하 곡선
                     {"task": "quality", "train": {...}, "current": {...}, "target": 열, "features": [열], "spec": [하한, 상한]}"""
        if inputs.get("task") == "stroke":
            from cont.packs.diagnosis.special import diagnose_stroke
            return diagnose_stroke(inputs["normal"], inputs["current"], inputs.get("position"), inputs.get("special", "press"),
                                   inputs.get("unit", ""), question, inputs.get("profile")).answer
        if inputs.get("task") == "quality":
            from cont.packs.diagnosis.special import assess_quality, fit_quality
            model = fit_quality(inputs["train"], inputs["target"], inputs["features"], inputs.get("profile"))
            return assess_quality(model, inputs["current"], tuple(inputs["spec"]), inputs.get("time"), inputs.get("measured"),
                                  inputs.get("label", "두께"), inputs.get("unit", ""), question, inputs.get("profile")).answer
        if "systems" in inputs:
            from cont.packs.diagnosis.equipment import diagnose_equipment
            if inputs.get("special") or inputs.get("task") == "guide":
                from cont.packs.diagnosis.special import interpret
                eq = diagnose_equipment(inputs["systems"], inputs.get("equipment", ""), question, inputs.get("profile"))
                it = interpret(inputs["special"], eq, question) if inputs.get("special") else None
                if inputs.get("task") == "guide":
                    from cont.packs.diagnosis.guidance import guide
                    return guide(eq, it, question).answer
                return it.answer
            return diagnose_equipment(inputs["systems"], inputs.get("equipment", ""), question, inputs.get("profile")).answer
        return diagnose(inputs.get("module", "drive"), inputs["normal"], inputs["current"], inputs["signals"],
                        inputs.get("conditions"), inputs.get("time"), question, inputs.get("profile")).answer
