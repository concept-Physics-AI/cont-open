"""숨은 물리의 복원: 볼트 늘어남 관측에서 체결력과 마찰계수를 추정한다. 실제 측정이 없어 합성 관측으로 확인한다."""
import math
from dataclasses import replace

import pytest

from cont.answer import STATUS_ESTIMATED, STATUS_INPUT, STATUS_OBSERVED, STATUS_SIMULATED
from cont.dialogue.serve_fastening import example
from cont.packs.fastening import vdi2230
from cont.packs.fastening.estimate import ElongationMeasurement, estimate, settings, synthetic_elongations


def truth(j, l, mu):
    return vdi2230.calculate(j, replace(l, friction_thread=mu, friction_head=mu, friction_range=None))


def test_exact_observation_gives_back_the_preload_and_friction_that_made_it():
    j, l = example()
    t = truth(j, l, 0.11)
    e = estimate(j, l, ElongationMeasurement((t.delta_s * t.preload,), 0.0))
    assert e.preload == pytest.approx(t.preload) and e.friction == pytest.approx(0.11)
    a = e.answer
    assert a.status == STATUS_ESTIMATED and a.status_of("preload_estimated") == STATUS_ESTIMATED
    assert a.status_of("bolt_elongation") == STATUS_OBSERVED and a.status_of("tightening_torque") == STATUS_INPUT
    assert a.status_of("preload_model") == STATUS_SIMULATED and a.statuses()[0] == STATUS_OBSERVED
    assert a.value("safety_yield_estimated") == pytest.approx(t.safety_yield) and a.method.startswith("역문제 복원")
    assert dict(a.trust())["값의 지위"] == "관측, 입력, 해석, 추정"


def test_noisy_synthetic_observations_recover_the_truth_inside_the_reported_range():
    j, l = example()
    t = truth(j, l, 0.13)
    hits = 0
    for seed in range(40):
        m = ElongationMeasurement(synthetic_elongations(j, l, 0.13, noise=0.001, count=5, seed=seed), 0.001, "합성 데이터")
        e = estimate(j, l, m)
        hits += e.preload_range[0] <= t.preload <= e.preload_range[1] and e.friction_range[0] <= 0.13 <= e.friction_range[1]
    assert hits >= 38                                                    # 범위(약 95%)가 참값을 거의 늘 담는다


def test_uncertainty_is_reported_and_grows_with_a_worse_instrument_and_shrinks_with_more_readings():
    j, l = example()
    t = truth(j, l, 0.12)
    x = t.delta_s * t.preload
    fine, coarse = estimate(j, l, ElongationMeasurement((x,), 0.0005)), estimate(j, l, ElongationMeasurement((x,), 0.004))
    width = lambda e: e.preload_range[1] - e.preload_range[0]
    assert width(coarse) > width(fine) > 0
    floor = 2 * settings()["coverage_factor"] * settings()["bolt_resilience_relative_uncertainty"] * fine.preload
    assert width(estimate(j, l, ElongationMeasurement((x,), 0.0))) == pytest.approx(floor)      # 계기가 완벽해도 모형의 불확도는 남는다
    few = ElongationMeasurement((x - 0.002, x + 0.002), 0.0)
    many = ElongationMeasurement((x - 0.002, x + 0.002) * 8, 0.0)
    assert many.standard_uncertainty < few.standard_uncertainty and many.mean == pytest.approx(few.mean)
    a = coarse.answer
    assert "계기의 불확도 0.004 mm" in a.uncertainty and a.get("preload_estimated").expected_range == coarse.preload_range
    lo, hi = a.get("safety_yield_estimated").expected_range
    assert lo < a.value("safety_yield_estimated") < hi


def test_the_gap_to_the_torque_model_is_the_residual_and_is_reported_without_a_verdict():
    j, l = example()                                                     # 토크 모형: 대표 마찰 0.12, 범위 0.10 ~ 0.14
    inside, outside = truth(j, l, 0.13), truth(j, l, 0.20)
    e_in = estimate(j, l, ElongationMeasurement((inside.delta_s * inside.preload,), 0.001))
    e_out = estimate(j, l, ElongationMeasurement((outside.delta_s * outside.preload,), 0.001))
    assert e_in.within_model_range and not e_out.within_model_range
    (r,) = e_out.answer.residuals
    assert r.key == "observation_model_gap" and r.value == pytest.approx(outside.preload - vdi2230.calculate(j, l).preload) and r.value < 0
    assert r.note.endswith("범위 밖이다") and e_in.answer.residuals[0].note.endswith("범위 안이다")
    text = " ".join([r.note] + [q.label + (q.note or "") for q in e_out.answer.quantities])
    assert not any(w in text for w in ("합격", "불합격", "적합", "부적합", "정상", "불량"))
    no_range = estimate(j, replace(l, friction_range=None), ElongationMeasurement((inside.delta_s * inside.preload,), 0.001))
    assert "견줄 수 없다" in no_range.answer.residuals[0].note


def test_observations_that_contradict_the_torque_are_not_turned_into_a_friction_value():
    j, l = example()
    t = truth(j, l, 0.12)
    e = estimate(j, l, ElongationMeasurement((t.delta_s * t.preload * 12,), 0.001))     # 그 토크로는 낼 수 없는 늘어남
    assert math.isnan(e.friction) and e.answer.value("friction_estimated") is None
    assert "맞지 않아" in e.answer.get("friction_estimated").note
    with pytest.raises(KeyError):
        e.answer.get("safety_yield_estimated")
    for bad in ((), (0.0,), (-0.01,)):
        with pytest.raises(ValueError):
            ElongationMeasurement(bad, 0.001)
    with pytest.raises(ValueError):
        ElongationMeasurement((0.05,), -1.0)


def test_estimates_name_their_evidence_and_identifiability_follows_the_measurement():
    from cont.answer import IDENT_NONE, IDENT_OK, IDENT_WEAK
    j, l = example()
    t = truth(j, l, 0.12)
    x = t.delta_s * t.preload
    good = estimate(j, l, ElongationMeasurement((x,), 0.001)).answer
    assert good.get("preload_estimated").evidence == ("bolt_elongation", "bolt_resilience")
    assert [q.key for q in good.evidence_of("friction_estimated")] == ["bolt_elongation", "bolt_resilience", "tightening_torque"]
    assert good.get("preload_estimated").identifiability == IDENT_OK and "상대 표준 불확도 5.1%" in good.get("preload_estimated").identifiability_basis
    assert good.get("safety_yield_estimated").identifiability == good.get("friction_estimated").identifiability == IDENT_OK
    assert good.get("bolt_elongation").evidence == () and good.get("bolt_elongation").identifiability is None      # 관측값에는 적지 않는다
    poor = estimate(j, l, ElongationMeasurement((x,), 0.04)).answer                                             # 늘어남의 3분의 1이 넘는 계기 불확도
    assert poor.get("preload_estimated").identifiability == IDENT_WEAK and poor.get("friction_estimated").identifiability == IDENT_WEAK
    clash = estimate(j, l, ElongationMeasurement((x * 12,), 0.001)).answer
    assert clash.get("friction_estimated").identifiability == IDENT_NONE and "맞지 않는다" in clash.get("friction_estimated").identifiability_basis
    line = dict(good.trust())["증거와 식별가능성"]
    assert "체결력 (늘어남에서 추정) ← 볼트 늘어남 (관측, 평균), 볼트 컴플라이언스 delta_S (계산값). 식별가능성: 가려낼 수 있음" in line
    assert settings()["weak_identifiability_relative_uncertainty"] == 0.25
