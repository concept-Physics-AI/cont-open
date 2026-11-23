"""설비 한 대를 계통별로 묶어 진단한다.

설비는 공통 모듈(구동계, 압력·유동계, 열관리계, 공정 동작·사이클)의 조합이다. 계통마다 공통 진단을 돌리고,
"어느 계통에서 어떤 변화가 있는가"를 답변 묶음 하나로 정리한다. 현장 설정 파일(site)은 열 이름을 역할에 잇는다.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_OBSERVED
from cont.packs.diagnosis.pack import Diagnosis, diagnose


@dataclass(frozen=True)
class SystemResult:
    name: str               # 현장에서 부르는 이름 (예: "주축 구동부")
    diagnosis: Diagnosis

    @property
    def interval_count(self) -> int:
        return sum(len(r.intervals) for r in self.diagnosis.signals)

    @property
    def changes(self) -> list[Quantity]:
        return [q for q in self.diagnosis.answer.quantities if q.key.startswith("change_")]


@dataclass(frozen=True)
class EquipmentDiagnosis:
    answer: PhysicsAnswer
    equipment: str
    systems: tuple[SystemResult, ...]


def diagnose_equipment(systems: Sequence[Mapping[str, Any]], equipment: str = "", question: str = "",
                       profile: str | None = None) -> EquipmentDiagnosis:
    """systems의 각 항목: {"name", "module", "normal", "current", "signals", "conditions"(선택), "time"(선택)}"""
    if not systems:
        raise ValueError("at least one system is required")
    results: list[SystemResult] = []; names: set[str] = set()
    for s in systems:
        d = diagnose(s["module"], s["normal"], s["current"], s["signals"], s.get("conditions"), s.get("time"),
                     question, profile)
        name = s.get("name") or d.module.title
        if name in names:
            raise ValueError(f"system name '{name}' is used twice")
        names.add(name); results.append(SystemResult(name, d))
    quantities: list[Quantity] = []; basis: list[str] = []
    flagged = [r for r in results if r.interval_count]
    quantities.append(Quantity("systems_checked", "진단한 계통 수", float(len(results)), "개"))
    quantities.append(Quantity("systems_with_anomaly", "이상 징후가 있는 계통 수", float(len(flagged)), "개"))
    for i, r in enumerate(results):
        a = r.diagnosis.answer
        quantities.append(Quantity(f"system{i + 1}_anomaly_intervals", f"{r.name}: 이상 구간 수", float(r.interval_count), "개",
                                   note=r.diagnosis.module.title))
        for q in r.changes:
            quantities.append(Quantity(f"system{i + 1}_{q.key}", f"{r.name}: {q.label}", q.value, q.unit))
        found = [b for b in a.basis if "→" in b]
        basis.extend(f"[{r.name}] {b}" for b in found)
        if not found:
            basis.append(f"[{r.name}] 모든 신호가 같은 운전조건의 정상 범위 안에 있음")
    st = results[0].diagnosis.settings
    basis.insert(0, f"계통 {len(results)}개를 공통 진단 모듈로 각각 진단함: "
                    + ", ".join(f"{r.name}({r.diagnosis.module.title})" for r in results))
    basis.insert(1, f"판정 설정: 이탈 기준 정상 산포의 {st.z_limit}배, 연속 {st.min_run}표본 이상 (config/diagnosis, 현장 검증 전의 출발값)")
    answer = PhysicsAnswer(status=STATUS_OBSERVED, 
        question=question, quantities=tuple(quantities),
        method="통계 기준 비교 (계통별, 운전조건별 정상 패턴 대비 이탈)", basis=tuple(basis),
        confidence=Confidence("low", "계산은 가상 신호로 확인했지만 현장 데이터로 검증하지 않았고, 판정 기준값도 현장에서 정한 값이 아니다"),
        presentation=("overview:systems", "graph:signal_vs_normal_band", "list:evidence", "table:quantities"),
        inputs={"equipment": equipment, "profile": profile,
                "systems": [{"name": r.name, "module": r.diagnosis.module.name, **{k: r.diagnosis.answer.inputs[k]
                             for k in ("signals", "conditions", "time")}} for r in results]},
    )
    return EquipmentDiagnosis(answer, equipment, tuple(results))


def read_csv(path: str | Path) -> dict[str, np.ndarray]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path} has no rows")
    return {k: np.array([float(r[k]) for r in rows]) for k in rows[0] if k}


def load_site(path: str | Path) -> tuple[str, list[dict[str, Any]]]:
    """현장 설정 파일을 읽어 (설비 이름, 계통 목록)을 준다. CSV 경로는 설정 파일 위치를 기준으로 푼다.

    equipment: 3호기
    systems:
      - name: 주축 구동부
        module: drive
        normal: normal_drive.csv
        current: today_drive.csv
        time: t
        signals: {MTR01_A: current}
        conditions: {LOAD_PCT: load}
    """
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        d = yaml.safe_load(f) or {}
    out = []
    for s in d.get("systems", []):
        for key in ("module", "normal", "current", "signals"):
            if key not in s:
                raise ValueError(f"{p}: a system is missing '{key}'")
        out.append({**s, "normal": read_csv(p.parent / s["normal"]), "current": read_csv(p.parent / s["current"])})
    return str(d.get("equipment", "")), out


def site_special(path: str | Path) -> str | None:
    """현장 설정 파일의 `special: <공정>` 값. 없으면 None (공통 진단만)."""
    with open(path, encoding="utf-8") as f:
        v = (yaml.safe_load(f) or {}).get("special")
    return str(v) if v else None
