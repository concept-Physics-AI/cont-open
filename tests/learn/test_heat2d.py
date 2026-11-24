"""2차원 열전도 PINN 벤치마크 시험. 한계값은 건전성 확인용이며 제품 허용 오차가 아니다 (CLAUDE.md 규칙 6)."""
import pytest

torch = pytest.importorskip("torch")

from cont.answer import EVIDENCE_NONE, STATUS_SIMULATED, VALIDATION_COMPARED  # noqa: E402
from cont.learn import TrainConfig, heat2d, load_profile  # noqa: E402

P = heat2d.Heat2DProblem()


def test_same_seed_gives_same_result_in_process():
    c = load_profile("smoke")
    a, b = heat2d.train(P, c), heat2d.train(P, c)
    assert a.record.fingerprint() == b.record.fingerprint() and a.record.final_losses == b.record.final_losses
    assert heat2d.train(P, TrainConfig.from_dict({**c.to_dict(), "seed": 1})).record.fingerprint() != a.record.fingerprint()


def test_short_training_reports_deviation_field_and_flags():
    a = heat2d.answer(heat2d.train(P, load_profile("smoke")), n=11)
    assert a.method.startswith("PINN") and a.status == STATUS_SIMULATED
    assert a.validation == VALIDATION_COMPARED and a.evidence_level == EVIDENCE_NONE
    q = {x.key: x.value for x in a.quantities}
    assert all(v == v for v in q.values()) and q["deviation_analytic_rms"] > 0.0
    (f,) = a.fields
    assert f.key == "pinn_minus_teacher" and len(f.x) == 11 and len(f.y) == 11
    assert any("판정 없음" in b for b in a.basis) and a.residuals[0].key == "pde_residual"


def test_benchmark_profile_deviation_is_small_but_not_judged():
    t = heat2d.train(P, load_profile("heat2d_bench"))
    q = {x.key: x.value for x in heat2d.answer(t).quantities}
    assert q["deviation_analytic_rms"] < 0.05           # 마지막 시각 최고 온도 약 0.37 대비 건전성 한계
    assert abs(q["deviation_analytic_rms"] - q["deviation_teacher_rms"]) < 0.01
    assert t.record.loss_history[-1] < t.record.loss_history[0]


def test_invalid_problem_is_rejected():
    with pytest.raises(ValueError):
        heat2d.Heat2DProblem(horizon=0.0)
