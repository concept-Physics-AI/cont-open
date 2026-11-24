"""반복 측정 CSV를 읽어 엔진의 추정을 기준 값에 견주고 편차를 보고한다 (C6 검증의 입력 쪽).

CSV의 한 줄은 한 번의 측정이다. 필요한 열은 REQUIRED, 있으면 쓰는 열은 OPTIONAL이다.
이 모듈은 판정하지 않는다. 허용 오차는 프로파일이 한계를 정할 때만 판정으로 이어진다 (기본은 편차만).
데이터의 출처 열(data_origin)이 SYNTHETIC으로 시작하면 보고서에 합성이라고 적고 정확도 검증이 아니라고 밝힌다.
"""
from __future__ import annotations

import argparse
import csv
import math
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from cont.packs.fastening import vdi2230
from cont.packs.fastening.estimate import ElongationMeasurement, estimate
from cont.packs.fastening.estimate import settings as estimate_settings
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from cont.tolerance import Check, Tolerance, check, load_profile

REQUIRED = ("specimen_id", "torque_set_Nm", "bolt_size", "strength_class", "plate_1_thickness_mm", "plate_2_thickness_mm", "length_error_halfwidth_mm")
LENGTHS = ("elongation_mm", "length_before_mm")          # 둘 중 하나: 늘어남을 직접 주거나, 전후 길이를 준다
OPTIONAL = ("length_after_mm", "data_origin", "simulated_loadcell_force_N", "force_error_halfwidth_N", "effective_elastic_length_mm",
            "tensile_area_mm2", "elastic_modulus_MPa", "repeat_id")
K_RECT = math.sqrt(3.0)                                    # 직사각형 분포: 표준 불확도 = 반너비 / sqrt(3)
COVERAGE = 2.0


@dataclass(frozen=True)
class Specimen:
    specimen_id: str
    torque: float                       # N·m
    bolt_size: str
    strength_class: str
    plate_thickness: tuple[float, float]
    elongations: tuple[float, ...]      # mm, 같은 시편을 반복해 잰 값
    length_halfwidth: float             # mm, 길이 한 번 읽을 때의 오차 반너비
    forces: tuple[float, ...]           # N, 하중셀 반복 읽기 (없으면 비어 있음)
    force_halfwidth: float | None
    leff: float | None                  # 데이터가 가정한 등가 탄성길이 (mm)
    area: float | None                  # mm^2
    modulus: float | None               # MPa
    origins: tuple[str, ...]

    @property
    def length_instrument_uncertainty(self) -> float:
        """전과 후, 두 번 읽은 길이의 차이에 들어가는 계기의 표준 불확도 (두 읽기가 독립이라고 본 값)."""
        return math.sqrt(2.0) * self.length_halfwidth / K_RECT

    @property
    def synthetic(self) -> bool:
        return any(o.upper().startswith("SYNTHETIC") for o in self.origins)


def _num(row: dict[str, str], key: str, line: int) -> float:
    try:
        return float(row[key])
    except (KeyError, ValueError):
        raise ValueError(f"{line}번째 줄: '{key}'가 숫자가 아닙니다 ({row.get(key)!r})") from None


def load_measurements(path: Path | str) -> list[Specimen]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = [c for c in REQUIRED if c not in cols]
        if missing or not (set(LENGTHS) & cols):
            raise ValueError("필요한 열이 없습니다: " + ", ".join(missing + ([] if set(LENGTHS) & cols else ["elongation_mm 또는 length_before_mm+length_after_mm"])))
        if "elongation_mm" not in cols and "length_after_mm" not in cols:
            raise ValueError("length_before_mm를 쓰려면 length_after_mm도 있어야 합니다")
        groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
        for i, row in enumerate(reader, start=2):
            groups.setdefault(row["specimen_id"], []).append((i, row))
    out: list[Specimen] = []
    for sid, rows in groups.items():
        first = rows[0][1]
        elong, forces = [], []
        for line, r in rows:
            if r["torque_set_Nm"] != first["torque_set_Nm"] or r["bolt_size"] != first["bolt_size"]:
                raise ValueError(f"{line}번째 줄: 시편 {sid} 안에서 조임 토크나 규격이 줄마다 다릅니다")
            if r.get("elongation_mm"):
                el = _num(r, "elongation_mm", line)
                if r.get("length_before_mm") and r.get("length_after_mm"):
                    diff = _num(r, "length_after_mm", line) - _num(r, "length_before_mm", line)
                    if abs(diff - el) > 1e-6:
                        raise ValueError(f"{line}번째 줄: elongation_mm가 전후 길이의 차이와 다릅니다 ({el} 대 {diff:.7f})")
            else:
                el = _num(r, "length_after_mm", line) - _num(r, "length_before_mm", line)
            elong.append(el)
            if r.get("simulated_loadcell_force_N") or r.get("loadcell_force_N"):
                forces.append(_num(r, "simulated_loadcell_force_N" if r.get("simulated_loadcell_force_N") else "loadcell_force_N", line))
        opt = lambda k: float(first[k]) if first.get(k) else None
        out.append(Specimen(sid, float(first["torque_set_Nm"]), first["bolt_size"], first["strength_class"],
                            (float(first["plate_1_thickness_mm"]), float(first["plate_2_thickness_mm"])), tuple(elong),
                            float(first["length_error_halfwidth_mm"]), tuple(forces), opt("force_error_halfwidth_N"),
                            opt("effective_elastic_length_mm"), opt("tensile_area_mm2"), opt("elastic_modulus_MPa"),
                            tuple(sorted({r.get("data_origin", "") for _, r in rows}))))
    return out


@dataclass(frozen=True)
class Assumptions:
    """CSV에 없어서 정해야 하는 값. 보고서에 그대로 적는다 (값을 코드에 박지 않는다는 규칙에 따라 호출하는 쪽이 준다)."""
    outer_diameter: float = 40.0
    plate_modulus: float = 205000.0
    friction: float = 0.12


@dataclass(frozen=True)
class Row:
    specimen: str
    quantity: str
    engine: float | None
    reference: float | None
    unit: str
    check: Check | None
    note: str = ""


@dataclass(frozen=True)
class BudgetLine:
    """오차 예산의 한 줄. kind가 '편차'이면 체결력 편차(로그 비율)를 나눈 몫이고, '불확도'이면 상대 표준 불확도(k=1)다."""
    specimen: str
    term: str
    value: float
    kind: str
    note: str = ""


def error_budget(s: Specimen, a: Assumptions) -> list[BudgetLine]:
    """엔진의 체결력 추정과 하중셀의 편차를 항목으로 나눈다 (곱셈 관계라 로그 비율로 나눠야 합이 맞는다).

    체결력 = 늘어남 / 컴플라이언스이므로 ln(엔진 / 하중셀) = ln(데이터 컴플라이언스 / 엔진 컴플라이언스) + ln(데이터 컴플라이언스로 환산한 체결력 / 하중셀).
    앞의 항은 모형의 정의 차이, 뒤의 항은 관측과 하중셀과 그 밖의 것이 합쳐진 남는 편차다.
    """
    ref, ref_u = _force_reference(s)
    if ref is None or not (s.leff and s.area and s.modulus):
        return []
    plates = tuple(Plate(t, s.modulus, None) for t in s.plate_thickness)
    joint = BoltedJoint(s.bolt_size, s.strength_class, plates[0], plates[1], outer_diameter=a.outer_diameter)
    load = LoadCase(s.torque, a.friction, a.friction)
    measured = ElongationMeasurement(s.elongations, s.length_instrument_uncertainty, "측정 CSV")
    est = estimate(joint, load, measured)
    engine_comp = vdi2230.calculate(joint, load).delta_s
    data_comp = s.leff / (s.modulus * s.area)
    from_data = measured.mean / data_comp
    total = math.log(est.preload / ref)
    model_form = math.log(data_comp / engine_comp)
    remainder = math.log(from_data / ref)
    assumed = estimate_settings()["bolt_resilience_relative_uncertainty"]
    lines = [
        BudgetLine(s.specimen_id, "총 편차 (엔진 추정 대 하중셀)", total, "편차"),
        BudgetLine(s.specimen_id, "모형의 정의 차이 (볼트 컴플라이언스)", model_form, "편차",
                   "엔진은 머리·나사 물림·너트 변형을 포함하고 데이터는 Leff/(E·A) 하나로 둔다"),
        BudgetLine(s.specimen_id, "남는 편차 (관측, 하중셀, 그 밖)", remainder, "편차", "데이터의 컴플라이언스로 환산해도 남는 몫"),
        BudgetLine(s.specimen_id, "관측 (늘어남 평균)", measured.standard_uncertainty / measured.mean, "불확도"),
        BudgetLine(s.specimen_id, "하중셀 기준", (ref_u or 0.0) / COVERAGE / ref, "불확도"),
        BudgetLine(s.specimen_id, "엔진의 컴플라이언스 계산값 (잠정 가정)", assumed, "불확도", "표준에서 온 값이 아니라 잠정으로 둔 값"),
    ]
    if abs(model_form) > 2 * assumed:
        lines.append(BudgetLine(s.specimen_id, "점검: 정의 차이가 잠정 불확도의 2배보다 크다", abs(model_form) / assumed, "점검",
                                "엔진의 잠정 불확도로는 이 차이를 덮지 못한다. 실측이 오면 컴플라이언스 불확도를 다시 정한다"))
    return lines


def _force_reference(s: Specimen) -> tuple[float | None, float | None]:
    """하중셀 반복 읽기의 평균과 확장 불확도(k=2). 하중셀의 잔류 편향은 반복해도 줄어들지 않으므로 그대로 둔다."""
    if not s.forces:
        return None, None
    mean = statistics.fmean(s.forces)
    scatter = statistics.stdev(s.forces) / math.sqrt(len(s.forces)) if len(s.forces) > 1 else 0.0
    bias = (s.force_halfwidth or 0.0) / K_RECT
    return mean, COVERAGE * math.hypot(scatter, bias)


def compare_specimen(s: Specimen, a: Assumptions, profile: dict[str, Tolerance]) -> list[Row]:
    plates = tuple(Plate(t, s.modulus or a.plate_modulus, None) for t in s.plate_thickness)
    joint = BoltedJoint(s.bolt_size, s.strength_class, plates[0], plates[1], outer_diameter=a.outer_diameter)
    load = LoadCase(s.torque, a.friction, a.friction)
    measured = ElongationMeasurement(s.elongations, s.length_instrument_uncertainty, "측정 CSV")
    est = estimate(joint, load, measured)
    rows: list[Row] = []
    ref, ref_u = _force_reference(s)
    if ref is not None:
        chk = check(profile["elongation_to_preload"], est.preload, ref)
        inside = est.preload_range[0] <= ref <= est.preload_range[1]
        rows.append(Row(s.specimen_id, "체결력 (엔진 추정 대 하중셀)", est.preload, ref, "N", chk,
                        f"하중셀 확장 불확도 ±{ref_u:.0f} N (k=2). 엔진 추정 범위 {est.preload_range[0]:.0f}~{est.preload_range[1]:.0f} N, "
                        f"하중셀 값은 범위 {'안' if inside else '밖'} (사실 보고, 판정 아님)"))
    if s.leff and s.area and s.modulus:
        data_comp = s.leff / (s.modulus * s.area)
        engine_comp = vdi2230.calculate(joint, load).delta_s
        rows.append(Row(s.specimen_id, "볼트 컴플라이언스 (엔진 VDI 2230 대 데이터의 Leff/(E·A))", engine_comp, data_comp, "mm/N",
                        check(profile["bolt_compliance"], engine_comp, data_comp),
                        "두 값의 정의가 다르다 (엔진은 머리·나사 물림·너트 변형을 포함). 체결력 편차의 주된 원인인지 비율로 본다"))
    return rows


def report(path: Path | str, assumptions: Assumptions | None = None, profile: dict[str, Tolerance] | None = None) -> dict[str, Any]:
    a, profile = assumptions or Assumptions(), profile if profile is not None else load_profile()
    specimens = load_measurements(path)
    rows = [r for s in specimens for r in compare_specimen(s, a, profile)]
    synthetic = any(s.synthetic for s in specimens)
    origin = sorted({o for s in specimens for o in s.origins})
    notes = ["데이터 출처 표시: " + (", ".join(origin) or "없음 (실측인지 확인되지 않음)")]
    if synthetic:
        notes.append("합성 데이터다. 입력 연결, 단위, 불확도 계산, 편차 보고를 시험한 것이며 엔진의 정확도를 검증한 것이 아니다.")
    notes.append(f"CSV에 없어 가정한 값: 체결부 바깥지름 {a.outer_diameter:g} mm, 판 탄성계수 {a.plate_modulus:g} MPa (CSV에 없을 때), 마찰계수 {a.friction:g} (체결력 추정에는 쓰이지 않음)")
    judged = [r for r in rows if r.check is not None and r.check.passed is not None]
    notes.append("허용 오차를 정하지 않아 판정은 하지 않았다." if not judged else f"한계가 정해진 {len(judged)}개 중 {sum(bool(r.check.passed) for r in judged)}개가 한계 안이다.")
    budget = [b for s in specimens for b in error_budget(s, a)]
    return {"specimens": len(specimens), "synthetic": synthetic, "rows": rows, "notes": notes, "budget": budget}


def text(rep: dict[str, Any]) -> str:
    lines = [f"측정 CSV 편차 보고: 시편 {rep['specimens']}개"] + ["- " + n for n in rep["notes"]] + [""]
    for r in rep["rows"]:
        dev = "-" if r.check is None or r.check.deviation is None else f"{r.check.deviation * 100:+.1f}%"
        sign = ""
        if r.engine is not None and r.reference:
            sign = f"{100 * (r.engine - r.reference) / r.reference:+.1f}%"
        lines.append(f"{r.specimen} | {r.quantity} | 엔진 {r.engine:.6g} {r.unit} | 기준 {r.reference:.6g} {r.unit} | 상대 편차 {sign} (절대 {dev})")
        if r.note:
            lines.append(f"    {r.note}")
    if rep.get("budget"):
        lines += ["", "오차 예산 (편차는 로그 비율의 %, 합이 총 편차와 같다. 불확도는 상대 표준 불확도 k=1)"]
        for b in rep["budget"]:
            lines.append(f"{b.specimen} | {b.kind} | {b.term} | {b.value * 100:+.2f}%" if b.kind != "점검" else f"{b.specimen} | 점검 | {b.term} ({b.value:.1f}배)")
            if b.note:
                lines.append(f"    {b.note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="반복 측정 CSV 경로 (저장소 밖에 둔다)")
    ap.add_argument("--outer-diameter", type=float, default=Assumptions.outer_diameter)
    ap.add_argument("--plate-modulus", type=float, default=Assumptions.plate_modulus)
    a = ap.parse_args(argv)
    print(text(report(a.csv, Assumptions(a.outer_diameter, a.plate_modulus))))


if __name__ == "__main__":
    main()
