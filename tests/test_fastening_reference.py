"""기준값 대조의 틀. 실제 기준 사례는 아직 없다 (표준 원문이 없어 기억으로 적지 않았다)."""
import pytest

from cont.dialogue.serve_fastening import example
from cont.packs.fastening import answer
from cont.packs.fastening.reference import compare, cross_check, load_cases, run
from cont.tolerance import Tolerance, load_profile

JOINT = "{size: M10, property_class: '10.9', plate_head: {thickness: 15, youngs_modulus: 205000}, plate_nut: {thickness: 15, youngs_modulus: 205000}, outer_diameter: 40}"
LOAD = "{tightening_torque: 50, friction_thread: 0.12, friction_head: 0.12}"


def write(tmp_path, body):
    (tmp_path / "cases.yaml").write_text(body, encoding="utf-8")
    return tmp_path


def test_the_shipped_case_list_is_empty_and_the_report_says_so_instead_of_passing():
    assert load_cases() == []
    r = run()
    assert r["cases"] == 0 and r["rows"] == [] and r["summary"].startswith("기준 사례가 없습니다")


def test_a_case_reports_deviation_only_until_a_profile_sets_a_limit(tmp_path):
    j, l = example()
    made_up = answer(j, l.__class__(50.0, 0.12, 0.12)).value("preload") * 1.02          # 틀을 확인하려고 만든 값. 기준값이 아니다
    d = write(tmp_path, f"cases:\n  - name: 틀 확인용\n    source: 테스트가 만든 값\n    joint: {JOINT}\n    load: {LOAD}\n"
                        f"    expected:\n      preload: {{value: {made_up}, tolerance: torque_to_preload}}\n"
                        f"      safety_slip: {{value: 2.0, tolerance: slip_and_opening}}\n")
    (case,) = load_cases(d)
    rows = compare(case)
    assert rows[0].check.deviation == pytest.approx(0.02 / 1.02) and rows[0].check.passed is None and "판정 없음" in rows[0].text()
    assert rows[1].value is None and rows[1].check.deviation is None and "계산하지 않음" in rows[1].text()      # 입력이 없어 계산하지 않은 값
    assert "한계를 정하지 않아 판정은 하지 않았습니다" in run(d)["summary"]
    strict = dict(load_profile(), torque_to_preload=Tolerance("torque_to_preload", "relative", 0.01))
    loose = dict(load_profile(), torque_to_preload=Tolerance("torque_to_preload", "relative", 0.05))
    assert compare(case, strict)[0].check.passed is False and "한계 밖" in compare(case, strict)[0].text()
    assert compare(case, loose)[0].check.passed is True and "1개 가운데 1개가 한계 안" in run(d, loose)["summary"]


def test_cases_without_a_source_or_with_a_loose_format_are_refused(tmp_path):
    with pytest.raises(ValueError, match="출처 없는 기준값은 받지 않습니다"):
        load_cases(write(tmp_path, f"cases:\n  - name: 출처 없음\n    joint: {JOINT}\n    load: {LOAD}\n    expected: {{}}\n"))
    with pytest.raises(ValueError, match="함께 적어야 합니다"):
        load_cases(write(tmp_path, f"cases:\n  - name: n\n    source: s\n    joint: {JOINT}\n    load: {LOAD}\n    expected:\n      preload: 30000\n"))
    d = write(tmp_path, f"cases:\n  - name: n\n    source: s\n    joint: {JOINT}\n    load: {LOAD}\n    expected:\n      preload: {{value: 1, tolerance: no_such}}\n")
    with pytest.raises(ValueError, match="프로파일에 없습니다"):
        compare(load_cases(d)[0])


def test_formula_and_numerical_plate_resilience_are_cross_checked_and_not_called_a_reference():
    j, l = example()
    row = cross_check(j, l)
    assert row.quantity == "plate_resilience" and 0 < row.check.deviation < 0.5 and row.check.passed is None
    assert "기준값이 아니라 다른 방법일 뿐이다" in row.source and row.check.quantity == "stiffness_vs_fem"
