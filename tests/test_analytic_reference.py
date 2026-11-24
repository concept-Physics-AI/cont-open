"""토크계수 K와 마찰계수 mu의 변환, 해석 기준표 대조, 오차 예산. 시험 자료는 식으로 만든 가짜 값이다."""
import csv
import math

import pytest

from cont.packs.fastening import analytic_reference, intake, vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate
from tests.test_intake import write

HEAD = ["data_origin", "case_id", "bolt_size", "strength_class", "plate_1_thickness_mm", "plate_2_thickness_mm", "torque_Nm", "torque_coefficient_K",
        "elastic_modulus_MPa", "reference_force_N", "reference_elongation_mm"]


def joint():
    return BoltedJoint("M10", "10.9", Plate(15, 210000.0, None), Plate(15, 210000.0, None), outer_diameter=40.0)


def table(path, ks=(0.18, 0.22), origin="ANALYTICAL_ASSUMPTION", torque=50.0):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEAD); w.writeheader()
        for k in ks:
            force = torque * 1000 / (k * 10.0)
            w.writerow({"data_origin": origin, "case_id": f"K{k}", "bolt_size": "M10", "strength_class": "10.9", "plate_1_thickness_mm": 15,
                        "plate_2_thickness_mm": 15, "torque_Nm": torque, "torque_coefficient_K": k, "elastic_modulus_MPa": 210000.0,
                        "reference_force_N": force, "reference_elongation_mm": force * 40.0 / (210000.0 * 58.0)})
    return path


def test_torque_coefficient_and_friction_are_inverse_and_not_equal():
    j = joint()
    for mu in (0.08, 0.12, 0.2):
        k = vdi2230.torque_coefficient_from_friction(j, mu)
        assert vdi2230.friction_from_torque_coefficient(j, k) == pytest.approx(mu)
        assert k != pytest.approx(mu, rel=0.05)                  # K는 마찰계수와 같은 값이 아니다


def test_a_torque_coefficient_below_what_zero_friction_gives_is_refused():
    j = joint()
    with pytest.raises(ValueError, match="not reachable"):
        vdi2230.friction_from_torque_coefficient(j, vdi2230.torque_coefficient_from_friction(j, 0.0) * 0.9)


def test_mapped_friction_reproduces_the_reference_force_and_the_compliance_gap_is_reported(tmp_path):
    rep = analytic_reference.compare_reference(table(tmp_path / "t.csv"))
    force = [r for r in rep["rows"] if r.quantity.startswith("체결력")]
    elong = [r for r in rep["rows"] if r.quantity.startswith("늘어남")]
    assert len(force) == len(elong) == 2
    assert all(r.engine == pytest.approx(r.reference, rel=1e-9) for r in force)         # 옮기는 식의 일관성
    assert all(r.engine / r.reference > 1.1 for r in elong)                              # 정의 차이
    assert rep["assumed"] and any("검증한 것이 아니다" in n for n in rep["notes"]) and any("판정은 하지 않았다" in n for n in rep["notes"])
    assert "상대 편차" in analytic_reference.text(rep)


def test_reference_table_with_missing_column_or_unreachable_k_names_the_problem(tmp_path):
    p = table(tmp_path / "t.csv")
    text = p.read_text(encoding="utf-8-sig").replace("torque_coefficient_K", "K_value")
    p.write_text(text, encoding="utf-8-sig")
    with pytest.raises(ValueError, match="torque_coefficient_K"):
        analytic_reference.compare_reference(p)
    with pytest.raises(ValueError, match="K0.01"):
        analytic_reference.compare_reference(table(tmp_path / "u.csv", ks=(0.01,)))


def test_error_budget_splits_the_force_deviation_into_parts_that_add_up(tmp_path):
    rep = intake.report(write(tmp_path / "m.csv"))
    by = {}
    for b in rep["budget"]:
        by.setdefault(b.specimen, {})[b.term] = b
    for lines in by.values():
        total, model, rest = (lines[k].value for k in ("총 편차 (엔진 추정 대 하중셀)", "모형의 정의 차이 (볼트 컴플라이언스)", "남는 편차 (관측, 하중셀, 그 밖)"))
        assert total == pytest.approx(model + rest, abs=1e-12)
        assert abs(model) > 0.1 and abs(rest) < 0.01          # 단순식으로 만든 늘어남이므로 편차는 거의 모두 정의 차이
        assert any(t.startswith("점검") for t in lines)      # 잠정 불확도 5%의 2배보다 큰 차이
        assert all(b.value >= 0 for b in lines.values() if b.kind == "불확도")
    out = intake.text(rep)
    assert "오차 예산" in out and "모형의 정의 차이" in out


def test_error_budget_is_skipped_when_the_data_lacks_a_reference(tmp_path):
    rep = intake.report(write(tmp_path / "m.csv", drop=("simulated_loadcell_force_N",)))
    assert rep["budget"] == [] and "오차 예산" not in intake.text(rep)
