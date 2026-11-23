"""기준값 대조 (C6 검증): 기준 사례와 계산 결과의 편차를 낸다. 판정은 허용 오차 프로파일이 한계를 정한 환경에서만 한다.

두 가지를 한다.
1. 기준 사례(config/reference/fastening/*.yaml)를 계산해 기준값과의 편차를 보고한다. 출처가 없는 사례는 받지 않는다.
2. 서로 다른 두 방법(VDI 2230 식과 축대칭 수치해석)의 판 컴플라이언스를 견준다. 기준값이 없어도 할 수 있는 상호 대조다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cont.packs.fastening.field import stress_field
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.pack import answer
from cont.tolerance import CONFIG_DIR, Check, Tolerance, check, load_profile


@dataclass(frozen=True)
class Case:
    name: str
    source: str
    joint: BoltedJoint
    load: LoadCase
    expected: dict[str, dict[str, Any]]      # 물리량 이름 → {value, tolerance}
    note: str = ""


@dataclass(frozen=True)
class Row:
    case: str
    quantity: str
    value: float | None                      # 계산값
    reference: float                         # 기준값
    check: Check                             # 편차, 한계, 판정 (한계가 없으면 판정은 None)
    source: str

    def text(self) -> str:
        dev = "계산하지 않음" if self.check.deviation is None else f"{self.check.deviation:.3g}"
        verdict = "판정 없음 (한계를 정하지 않음)" if self.check.passed is None else ("한계 안" if self.check.passed else "한계 밖")
        return f"{self.case} / {self.quantity}: 계산 {self.value}, 기준 {self.reference}, 편차 {dev}, {verdict}. 출처: {self.source}"


def load_cases(directory: Path | None = None) -> list[Case]:
    directory = directory or (CONFIG_DIR / "reference" / "fastening")
    cases: list[Case] = []
    for path in sorted(directory.glob("*.yaml")):
        for raw in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("cases") or []:
            name = str(raw.get("name", "")).strip()
            source = str(raw.get("source", "")).strip()
            if not name or not source:
                raise ValueError(f"{path.name}: 기준 사례에는 이름(name)과 출처(source)가 있어야 합니다. 출처 없는 기준값은 받지 않습니다")
            expected = raw.get("expected") or {}
            for key, spec in expected.items():
                if not isinstance(spec, dict) or "value" not in spec or "tolerance" not in spec:
                    raise ValueError(f"{path.name} / {name} / {key}: 기준값(value)과 허용 오차 항목(tolerance)을 함께 적어야 합니다")
            cases.append(Case(name, source, BoltedJoint.from_dict(raw["joint"]), LoadCase.from_dict(raw["load"]), expected, str(raw.get("note", ""))))
    return cases


def compare(case: Case, profile: dict[str, Tolerance] | None = None) -> list[Row]:
    profile = profile if profile is not None else load_profile()
    a = answer(case.joint, case.load)
    rows = []
    for key, spec in case.expected.items():
        if spec["tolerance"] not in profile:
            raise ValueError(f"{case.name} / {key}: 허용 오차 항목 '{spec['tolerance']}'이(가) 프로파일에 없습니다")
        value = a.value(key)
        tol = profile[spec["tolerance"]]
        chk = check(tol, value, float(spec["value"])) if value is not None else Check(tol.quantity, None, tol.limit, None)
        rows.append(Row(case.name, key, value, float(spec["value"]), chk, case.source))
    return rows


def run(directory: Path | None = None, profile: dict[str, Tolerance] | None = None) -> dict[str, Any]:
    """모든 기준 사례를 견준 결과. 사례가 없으면 없다고 말한다 (통과로 치지 않는다)."""
    cases = load_cases(directory)
    rows = [row for case in cases for row in compare(case, profile)]
    judged = [r for r in rows if r.check.passed is not None]
    summary = ("기준 사례가 없습니다. 표준 예제와는 아직 대조하지 않았습니다" if not cases else
               f"기준 사례 {len(cases)}건, 물리량 {len(rows)}개의 편차를 냈습니다. " +
               (f"한계가 정해진 {len(judged)}개 가운데 {sum(r.check.passed for r in judged)}개가 한계 안입니다" if judged else "한계를 정하지 않아 판정은 하지 않았습니다"))
    return {"cases": len(cases), "rows": rows, "summary": summary}


def cross_check(joint: BoltedJoint, load: LoadCase, profile: dict[str, Tolerance] | None = None) -> Row:
    """VDI 2230 식의 판 컴플라이언스를 축대칭 수치해석 값에 견준다 (허용 오차 항목: stiffness_vs_fem)."""
    profile = profile if profile is not None else load_profile()
    f = stress_field(joint, load)
    fem, vdi = f.value("plate_resilience_fem"), f.value("plate_resilience_vdi")
    return Row("상호 대조: VDI 2230 식과 축대칭 수치해석", "plate_resilience", vdi, fem, check(profile["stiffness_vs_fem"], vdi, fem),
               "이 저장소의 수치해석 (실측이나 다른 해석 프로그램과 대조하지 않은 값). 기준값이 아니라 다른 방법일 뿐이다")
