"""해석 규칙: 공통 진단의 상태 변화(어느 계통, 어떤 변화, 갑자기/서서히)를 공정의 말로 옮긴다.

규칙은 tables/special/<공정>.yaml에 있다. 일반적인 공정 지식으로 쓴 출발점이라 결과는 "의심"이며,
정비 이력·품질 기록과 맞춰 본 뒤에야 믿을 수 있다. 그래서 신뢰도는 "낮음"으로 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_OBSERVED
from cont.packs.diagnosis.detect import Interval
from cont.packs.diagnosis.equipment import EquipmentDiagnosis
from cont.packs.diagnosis.pack import SignalResult
from cont.packs.diagnosis.profile import Settings, Special, load_special

ONSET = {"abrupt": "갑자기", "gradual": "서서히"}


@dataclass(frozen=True)
class Finding:
    key: str
    label: str
    meaning: str
    system: str
    signal: str         # 현장 열 이름
    change: str         # 공통 진단의 상태 변화 키
    onset: str          # abrupt | gradual
    start: float        # 시간 열의 값
    end: float
    peak_z: float


@dataclass(frozen=True)
class Interpretation:
    answer: PhysicsAnswer
    special: Special
    findings: tuple[Finding, ...]


def onset_of(r: SignalResult, iv: Interval, st: Settings) -> str:
    """이상 구간이 시작될 때 이탈이 한 번에 뛰었는가. 시작 직전과 직후(min_run 표본)의 평균 이탈을 비교한다."""
    k = st.min_run
    before = r.z[max(iv.start - k, 0):iv.start]
    after = r.z[iv.start:iv.start + k]
    jump = abs(float(after.mean()) - (float(before.mean()) if before.size else 0.0))
    return "abrupt" if jump >= st.abrupt_jump_ratio * st.z_limit else "gradual"


def interpret(special: str, eq: EquipmentDiagnosis, question: str = "") -> Interpretation:
    sp = load_special(special)
    found: dict[tuple[str, str, str], Finding] = {}
    for s in eq.systems:
        d = s.diagnosis
        runs: dict[tuple[str, str], list[Interval]] = {}
        for r in d.signals:
            for iv in r.intervals:
                runs.setdefault((r.column, iv.direction), []).append(iv)
        for r in d.signals:
            for direction in ("up", "down"):
                ivs = runs.get((r.column, direction))
                ct = d.module.change_type(r.role, direction)
                if not ivs or ct is None:
                    continue
                # 서서히 커지는 변화는 초입에서 구간이 나뉘어 잡힌다. 같은 신호·같은 방향은 한 사건으로 보고 첫 구간의 시작 모양으로 판단한다.
                first = ivs[0]; onset = onset_of(r, first, d.settings)
                peak = max((iv.peak_z for iv in ivs), key=abs)
                for rule in sp.rules:
                    w = rule["when"]
                    if w["module"] != d.module.name or w["change"] != ct.key or w.get("onset", onset) != onset:
                        continue
                    found[(s.name, r.column, rule["key"])] = Finding(
                        rule["key"], rule["label"], rule["meaning"], s.name, r.column, ct.key, onset,
                        float(d.time[first.start]), float(d.time[ivs[-1].end]), float(peak))
    findings = tuple(sorted(found.values(), key=lambda f: f.start))
    quantities = [Quantity("findings", "공정 해석 건수", float(len(findings)), "건")]
    for i, f in enumerate(findings):
        quantities.append(Quantity(f"finding{i + 1}_{f.key}", f"{f.system}: {f.label}", f.peak_z, "정상 산포의 배수",
                                   note=f"{f.start:g}~{f.end:g}, {ONSET[f.onset]}"))
    basis = [f"특화 진단: {sp.title}. 공통 진단의 상태 변화를 공정 지식표(tables/special/{sp.name}.yaml)의 규칙 {len(sp.rules)}개로 해석함",
             "규칙은 일반적인 공정 지식으로 쓴 출발점이며, 정비 이력·품질 기록과 맞춰 본 것이 아님"]
    for f in findings:
        basis.append(f"[{f.system}] {f.signal}: {f.start:g}부터 {ONSET[f.onset]} 나타난 변화({f.change}) → {f.label}. {f.meaning}")
    unmatched = int(eq.answer.value("systems_with_anomaly")) and not findings
    if not findings:
        basis.append("공통 진단의 변화 가운데 이 공정의 규칙에 해당하는 것이 없음" if unmatched else "공통 진단에서 이상 징후가 없어 해석할 변화가 없음")
    answer = PhysicsAnswer(status=STATUS_OBSERVED, 
        question=question, quantities=tuple(quantities), method="지식표 (공통 진단의 상태 변화 → 공정 해석 규칙)", basis=tuple(basis),
        confidence=Confidence("low", "해석 규칙을 현장의 정비 이력·품질 기록으로 검증하지 않았다. 결과는 점검할 곳을 좁히는 단서다"),
        presentation=("list:findings", "overview:systems"),
        inputs={"special": sp.name, "equipment": eq.equipment, "systems": eq.answer.inputs.get("systems", [])},
    )
    return Interpretation(answer, sp, findings)
