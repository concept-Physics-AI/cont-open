"""해석 기준표(토크계수 K와 단순식으로 만든 기준 값)와 엔진을 같은 조건에서 견준다 (C6 검증의 입력 쪽).

기준표의 한 줄은 한 조건이다: 조임 토크 T, 토크계수 K, 기준 체결력 F = T/(K d), 기준 늘어남 = F·Leff/(E·A).
엔진은 마찰계수 mu로 계산하므로, K를 같은 조이는 조건의 mu로 옮겨(vdi2230.friction_from_torque_coefficient) 엔진의 체결력과 늘어남을 구한다.

두 비교는 따로 읽는다.
- 체결력: K를 mu로 옮겼을 때 엔진의 토크 식이 같은 체결력을 내는지 보는 일관성 점검이다. 편차가 크면 옮기는 식이 틀린 것이다.
- 늘어남: 같은 체결력에서 엔진의 볼트 컴플라이언스(VDI 2230)와 기준표의 Leff/(E·A)가 얼마나 다른지 보는 정의 차이다.
기준표의 출처 열(data_origin)이 ANALYTICAL 또는 SYNTHETIC으로 시작하면 측정이 아니라 가정한 식의 값이라고 적고, 정확도를 검증한 것이 아니라고 밝힌다. 판정하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from cont.packs.fastening import vdi2230
from cont.packs.fastening.intake import Assumptions, Row
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from cont.tolerance import Tolerance, check, load_profile

REQUIRED = ("case_id", "bolt_size", "strength_class", "plate_1_thickness_mm", "plate_2_thickness_mm", "torque_Nm", "torque_coefficient_K",
            "elastic_modulus_MPa", "reference_force_N", "reference_elongation_mm")


def compare_reference(path: Path | str, assumptions: Assumptions | None = None, profile: dict[str, Tolerance] | None = None) -> dict[str, Any]:
    a, profile = assumptions or Assumptions(), profile if profile is not None else load_profile()
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("필요한 열이 없습니다: " + ", ".join(missing))
        records = list(reader)
    rows: list[Row] = []
    origins = sorted({r.get("data_origin", "") for r in records})
    for i, r in enumerate(records, start=2):
        try:
            e_mod = float(r["elastic_modulus_MPa"])
            joint = BoltedJoint(r["bolt_size"], r["strength_class"], Plate(float(r["plate_1_thickness_mm"]), e_mod, None),
                                Plate(float(r["plate_2_thickness_mm"]), e_mod, None), outer_diameter=a.outer_diameter)
            k = float(r["torque_coefficient_K"])
            mu = vdi2230.friction_from_torque_coefficient(joint, k)
            result = vdi2230.calculate(joint, LoadCase(float(r["torque_Nm"]), mu, mu))
            ref_force, ref_elong = float(r["reference_force_N"]), float(r["reference_elongation_mm"])
        except (ValueError, KeyError) as e:
            raise ValueError(f"{i}번째 줄 ({r.get('case_id', '?')}): {e}") from None
        engine_elong = result.preload * result.delta_s
        rows.append(Row(r["case_id"], f"체결력 (K={k:g}를 mu={mu:.4f}로 옮겨 엔진 토크 식으로)", result.preload, ref_force, "N",
                        check(profile["torque_to_preload"], result.preload, ref_force), "K와 mu를 옮기는 식의 일관성 점검 (같은 토크 식이므로 거의 0이어야 한다)"))
        rows.append(Row(r["case_id"], "늘어남 (같은 체결력에서 엔진의 볼트 컴플라이언스 대 기준표의 Leff/(E·A))", engine_elong, ref_elong, "mm",
                        check(profile["bolt_compliance"], engine_elong, ref_elong), "컴플라이언스 정의 차이"))
    assumed = any(o.upper().startswith(("ANALYTICAL", "SYNTHETIC")) for o in origins)
    notes = ["데이터 출처 표시: " + (", ".join(origins) or "없음")]
    if assumed:
        notes.append("기준 값은 측정이 아니라 가정한 식으로 만든 값이다. 엔진의 정확도를 검증한 것이 아니다.")
    notes.append(f"기준표에 없어 가정한 값: 체결부 바깥지름 {a.outer_diameter:g} mm")
    judged = [r for r in rows if r.check is not None and r.check.passed is not None]
    notes.append("허용 오차를 정하지 않아 판정은 하지 않았다." if not judged else f"한계가 정해진 {len(judged)}개 중 {sum(bool(r.check.passed) for r in judged)}개가 한계 안이다.")
    return {"cases": len(records), "assumed": assumed, "rows": rows, "notes": notes}


def text(rep: dict[str, Any]) -> str:
    lines = [f"해석 기준표 대조: 조건 {rep['cases']}개"] + ["- " + n for n in rep["notes"]] + [""]
    for r in rep["rows"]:
        rel = 100 * (r.engine - r.reference) / r.reference if r.reference else float("nan")
        lines.append(f"{r.specimen} | {r.quantity} | 엔진 {r.engine:.6g} {r.unit} | 기준 {r.reference:.6g} {r.unit} | 상대 편차 {rel:+.2f}%")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="해석 기준표 CSV 경로 (저장소 밖에 둔다)")
    ap.add_argument("--outer-diameter", type=float, default=Assumptions.outer_diameter)
    a = ap.parse_args(argv)
    print(text(compare_reference(a.csv, Assumptions(outer_diameter=a.outer_diameter))))


if __name__ == "__main__":
    main()
