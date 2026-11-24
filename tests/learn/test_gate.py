"""문지기 시험: 범위만 본다. 한계값은 건전성 확인용이며 제품 허용 오차가 아니다 (CLAUDE.md 규칙 6)."""
import math

import pytest

from cont.learn import gate, heat1d      # torch는 학습·예측을 부를 때만 가져오므로 범위 판정은 torch 없이 시험한다


def _problem():
    return heat1d.Heat1DProblem()


def test_decision_logic_needs_no_torch_and_names_the_reason():
    p = _problem()
    assert gate.decide_heat1d(p, 0.1, 0.5, 0.5).use_pinn
    assert gate.decide_heat1d(p, 0.1, 0.0, 1.0).use_pinn                     # 경계는 범위 안
    late = gate.decide_heat1d(p, 0.1, 0.5, 1.5)
    assert not late.use_pinn and late.in_domain and "시간 구간" in late.reasons[0]
    out = gate.decide_heat1d(p, 0.1, 1.2, 0.5)
    assert not out.use_pinn and not out.in_domain
    other = gate.decide_heat1d(p, 0.2, 0.5, 0.5)
    assert not other.use_pinn and "학습한 값" in other.reasons[0]
    both = gate.decide_heat1d(p, 0.2, 0.5, 5.0)
    assert len(both.reasons) == 2
    for bad in ((0.1, 0.5, -1.0), (0.0, 0.5, 0.5), (0.1, float("nan"), 0.5)):
        with pytest.raises(ValueError):
            gate.decide_heat1d(p, bad[0], bad[1], bad[2])


def test_teacher_matches_analytic_for_other_alpha_and_late_time():
    for alpha, x, t in ((0.1, 0.5, 2.0), (0.2, 0.5, 0.5), (0.5, 0.3, 1.0)):
        assert gate.teacher_value(alpha, x, t) == pytest.approx(math.exp(-alpha * math.pi ** 2 * t) * math.sin(math.pi * x), abs=2e-4)
    assert gate.teacher_value(0.1, 0.25, 0.0) == pytest.approx(math.sin(math.pi * 0.25))


@pytest.fixture(scope="module")
def trained():
    pytest.importorskip("torch")
    from cont.learn import load_profile
    return heat1d.train(heat1d.Heat1DProblem(), load_profile("smoke"))


def test_inside_uses_pinn_with_deviation_and_outside_falls_back(trained):
    a = gate.query(trained, [(0.5, 0.5), (0.5, 2.0), (1.5, 0.5)])
    inside, late, outside = a.get("u_0"), a.get("u_1"), a.get("u_2")
    assert "PINN" in inside.note and a.get("deviation_0").value is not None
    assert "물리 선생" in late.note and late.value == pytest.approx(math.exp(-0.1 * math.pi ** 2 * 2.0), abs=2e-4)
    assert outside.value is None and "영역 밖" in outside.note
    assert "deviation_1" not in {q.key for q in a.quantities}              # 범위 밖의 PINN 값과 편차는 만들지 않는다
    assert a.evidence_level == "E0" and "되돌림" in a.method and any("PINN의 정확도는 판단하지 않는다" in b for b in a.basis)


def test_all_outside_gives_reference_level_and_other_alpha_never_uses_pinn(trained):
    a = gate.query(trained, [(0.5, 0.5)], alpha=0.2)
    assert a.method.startswith("유한차분") and a.evidence_level == "E1" and a.validation == "unvalidated"
    assert a.get("u_0").value == pytest.approx(math.exp(-0.2 * math.pi ** 2 * 0.5), abs=2e-4)
    assert not [q for q in a.quantities if q.key.startswith("deviation")]
    with pytest.raises(ValueError):
        gate.query(trained, [])
