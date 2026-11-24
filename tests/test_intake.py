"""측정 CSV 입력과 편차 보고. 시험 자료는 식으로 만든 가짜 값이고, 실제 측정이 아니다."""
import csv
import math

import pytest

from cont.packs.fastening import intake
from cont.tolerance import Tolerance

HEAD = ["data_origin", "specimen_id", "repeat_id", "bolt_size", "strength_class", "plate_1_thickness_mm", "plate_2_thickness_mm", "torque_set_Nm",
        "length_before_mm", "length_after_mm", "elongation_mm", "simulated_loadcell_force_N", "length_error_halfwidth_mm", "force_error_halfwidth_N",
        "effective_elastic_length_mm", "tensile_area_mm2", "elastic_modulus_MPa"]
LEFF, AREA, E = 40.0, 58.0, 210000.0


def write(path, specimens=2, repeats=5, origin="SYNTHETIC", drop=(), tweak=None):
    rows = []
    for s in range(specimens):
        force = 20000.0 + 1500.0 * s
        el = force * LEFF / (E * AREA)            # 데이터가 가정한 단순식으로 만든 늘어남
        for r in range(repeats):
            e = el + 1e-5 * ((r % 3) - 1)
            rows.append({"data_origin": origin, "specimen_id": f"B{s + 1:02d}", "repeat_id": r + 1, "bolt_size": "M10", "strength_class": "10.9",
                         "plate_1_thickness_mm": 15, "plate_2_thickness_mm": 15, "torque_set_Nm": 50, "length_before_mm": 60.0,
                         "length_after_mm": round(60.0 + e, 9), "elongation_mm": round(e, 9), "simulated_loadcell_force_N": force + 5.0 * ((r % 2) - 0.5),
                         "length_error_halfwidth_mm": 0.0005, "force_error_halfwidth_N": 100, "effective_elastic_length_mm": LEFF,
                         "tensile_area_mm2": AREA, "elastic_modulus_MPa": E})
    if tweak:
        tweak(rows)
    cols = [c for c in HEAD if c not in drop]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    return path


def test_rows_are_grouped_per_specimen_and_instrument_uncertainty_follows_the_two_reading_rule(tmp_path):
    sp = intake.load_measurements(write(tmp_path / "m.csv"))
    assert [s.specimen_id for s in sp] == ["B01", "B02"] and all(len(s.elongations) == 5 and len(s.forces) == 5 for s in sp)
    assert sp[0].length_instrument_uncertainty == pytest.approx(math.sqrt(2) * 0.0005 / math.sqrt(3))
    assert sp[0].synthetic


def test_missing_columns_and_inconsistent_elongation_are_named_not_guessed(tmp_path):
    with pytest.raises(ValueError, match="torque_set_Nm"):
        intake.load_measurements(write(tmp_path / "a.csv", drop=("torque_set_Nm",)))
    def bad(rows): rows[0]["elongation_mm"] = float(rows[0]["elongation_mm"]) + 0.01
    with pytest.raises(ValueError, match="전후 길이의 차이"):
        intake.load_measurements(write(tmp_path / "b.csv", tweak=bad))
    def mixed(rows): rows[1]["torque_set_Nm"] = 60
    with pytest.raises(ValueError, match="조임 토크"):
        intake.load_measurements(write(tmp_path / "c.csv", tweak=mixed))


def test_elongation_can_be_given_by_before_and_after_lengths_only(tmp_path):
    sp = intake.load_measurements(write(tmp_path / "m.csv", drop=("elongation_mm",)))
    assert sp[0].elongations[0] == pytest.approx(20000.0 * LEFF / (E * AREA), rel=1e-3)


def test_report_gives_deviation_only_and_says_synthetic_is_not_validation(tmp_path):
    rep = intake.report(write(tmp_path / "m.csv"))
    assert rep["synthetic"] and any("정확도를 검증한 것이 아니다" in n for n in rep["notes"]) and any("판정은 하지 않았다" in n for n in rep["notes"])
    force_rows = [r for r in rep["rows"] if r.quantity.startswith("체결력")]
    assert len(force_rows) == 2 and all(r.check.passed is None for r in rep["rows"])      # 한계를 정하지 않았으므로 판정 없음
    # 단순식으로 만든 늘어남은 엔진의 VDI 컴플라이언스로 환산하면 체결력이 낮게 나온다: 편차의 원인은 컴플라이언스 정의 차이
    comp = next(r for r in rep["rows"] if r.quantity.startswith("볼트 컴플라이언스"))
    ratio = comp.engine / comp.reference
    assert ratio > 1.1 and all(r.engine / r.reference == pytest.approx(1 / ratio, rel=0.01) for r in force_rows)
    assert all("밖" in r.note for r in force_rows)           # 하중셀 값이 엔진의 추정 범위 밖이라는 사실을 보고한다


def test_a_profile_with_a_limit_turns_the_deviation_into_a_verdict(tmp_path):
    profile = {"elongation_to_preload": Tolerance("elongation_to_preload", "relative", 0.05), "bolt_compliance": Tolerance("bolt_compliance", "relative", None)}
    rep = intake.report(write(tmp_path / "m.csv"), profile=profile)
    assert [r.check.passed for r in rep["rows"] if r.quantity.startswith("체결력")] == [False, False]
    assert any("한계가 정해진 2개 중 0개" in n for n in rep["notes"])


def test_data_without_a_synthetic_mark_is_not_called_measured(tmp_path):
    rep = intake.report(write(tmp_path / "m.csv", origin=""))
    assert not rep["synthetic"] and any("실측인지 확인되지 않음" in n for n in rep["notes"])
    assert not any("합성 데이터다" in n for n in rep["notes"])


def test_text_report_is_printable(tmp_path):
    out = intake.text(intake.report(write(tmp_path / "m.csv")))
    assert "B01" in out and "상대 편차" in out and "합성 데이터다" in out
