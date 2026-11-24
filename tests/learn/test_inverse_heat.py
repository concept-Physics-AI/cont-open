"""열전달 역문제 PINN 시험 (합성 센서). 한계값은 건전성 확인용이며 제품 허용 오차가 아니다 (CLAUDE.md 규칙 6)."""
from dataclasses import replace

import numpy as np
import pytest

from cont.answer import IDENT_NONE, IDENT_OK, IDENT_WEAK, STATUS_ESTIMATED, STATUS_OBSERVED, VALIDATION_COMPARED
from cont.learn import load_profile

torch = pytest.importorskip("torch")
from cont.learn import inverse_heat as ih  # noqa: E402

S = ih.InverseSetup.load()


def test_synthetic_data_is_reproducible_and_labeled_synthetic():
    a, b = ih.synthetic_observations(S), ih.synthetic_observations(S)
    assert np.array_equal(a, b) and a.shape == (S.n_times, len(S.sensors))
    assert not np.array_equal(a, ih.synthetic_observations(replace(S, noise_seed=1)))
    ans = ih.answer(ih.train(S, load_profile("smoke")))
    assert STATUS_OBSERVED not in {q.status for q in ans.quantities}       # 합성 값을 관측이라고 하지 않는다
    assert "합성" in ans.get("sensor_count").note and any("합성" in b for b in ans.basis)


def test_identifiability_follows_sensor_layout_and_noise():
    far = replace(S, sensors=(0.05, 0.1))
    assert ih.relative_uncertainty(S) < S.weak_relative < ih.relative_uncertainty(far) < S.none_relative
    assert ih.relative_uncertainty(replace(far, noise_sigma=0.05)) > S.none_relative
    levels = {}
    for name, setup in (("near", S), ("far", far), ("noisy", replace(far, noise_sigma=0.05))):
        levels[name] = ih.answer(ih.train(setup, load_profile("smoke"))).get("bi_pinn").identifiability
    assert levels == {"near": IDENT_OK, "far": IDENT_WEAK, "noisy": IDENT_NONE}


def test_estimates_carry_evidence_and_flags():
    a = ih.answer(ih.train(S, load_profile("smoke")))
    assert a.validation == VALIDATION_COMPARED and a.evidence_level == "E0"
    for k in ("bi_pinn", "bi_teacher_fit"):
        q = a.get(k)
        assert q.status == STATUS_ESTIMATED and q.evidence == ("sensor_count", "noise_sigma") and q.identifiability_basis
    assert len(a.evidence_lines()) == 2 and any("판정 없음" in b for b in a.basis)
    assert a.get("deviation_to_true").value == pytest.approx(a.get("bi_pinn").value - S.bi_true)


def test_same_seed_gives_same_estimate():
    c = load_profile("smoke")
    assert ih.train(S, c).bi == ih.train(S, c).bi


def test_benchmark_estimate_is_near_truth_but_deviation_is_only_reported():
    fit = ih.train(S, load_profile("inverse_train"))
    a = ih.answer(fit)
    q = {x.key: x.value for x in a.quantities}
    assert abs(q["deviation_to_true"]) / S.bi_true < 0.3           # 건전성 한계
    assert abs(ih.least_squares_bi(S, fit.data) - S.bi_true) / S.bi_true < 0.2
    assert abs(q["deviation_to_teacher_fit"]) / S.bi_true < 0.3
    assert fit.record.loss_history[-1] < fit.record.loss_history[0]


def test_invalid_setup_is_rejected():
    for bad in ({"alpha": 0.0}, {"sensors": ()}, {"sensors": (1.5,)}, {"weak_relative": 2.0}, {"noise_sigma": -1.0}):
        with pytest.raises(ValueError):
            replace(S, **bad)
