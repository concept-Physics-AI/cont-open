"""1차원 열전도 PINN 벤치마크 시험. 한계값은 건전성 확인용이며 제품 허용 오차가 아니다 (CLAUDE.md 규칙 6)."""
import pytest

torch = pytest.importorskip("torch")

from cont.answer import EVIDENCE_NONE, STATUS_INPUT, STATUS_SIMULATED, VALIDATION_COMPARED  # noqa: E402
from cont.learn import TrainConfig, load_profile  # noqa: E402
from cont.learn import heat1d  # noqa: E402

P = heat1d.Heat1DProblem()


def test_same_seed_gives_same_result_in_process():
    c = load_profile("smoke")
    a, b = heat1d.train(P, c), heat1d.train(P, c)
    assert a.record.fingerprint() == b.record.fingerprint()
    assert a.record.final_losses == b.record.final_losses
    c2 = TrainConfig.from_dict({**c.to_dict(), "seed": 1})
    assert heat1d.train(P, c2).record.fingerprint() != a.record.fingerprint()


def test_short_training_reports_deviation_and_runs_end_to_end():
    t = heat1d.train(P, load_profile("smoke"))
    a = heat1d.answer(t, nx=21, n_times=5)
    assert a.method.startswith("PINN") and a.status == STATUS_SIMULATED
    assert a.validation == VALIDATION_COMPARED and a.evidence_level == EVIDENCE_NONE     # 일치 판정 기준이 없으므로 E0
    assert a.status_of("alpha") == STATUS_INPUT and a.status_of("deviation_analytic_rms") == STATUS_SIMULATED
    q = {x.key: x.value for x in a.quantities}
    assert all(v == v for v in q.values())            # NaN 없음
    assert q["deviation_analytic_rms"] > 0.0          # 30 에포크로는 수렴하지 않는다. 그 편차를 숨기지 않는다
    assert any("측정 데이터를 쓰지 않는다" in b for b in a.basis) and any("판정 없음" in b for b in a.basis)
    assert a.inputs["config"]["seed"] == 0 and t.record.fingerprint() in " ".join(a.basis)
    assert a.residuals[0].key == "pde_residual"


def test_benchmark_profile_deviation_is_small_but_not_judged():
    t = heat1d.train(P, load_profile("heat1d_bench"))
    q = {x.key: x.value for x in heat1d.answer(t).quantities}
    assert q["deviation_analytic_rms"] < 0.05       # 최고 온도 약 0.37 대비 건전성 한계
    assert abs(q["deviation_analytic_rms"] - q["deviation_teacher_rms"]) < 0.01     # 해석해와 물리 선생이 서로 가깝다
    assert t.record.loss_history[-1] < t.record.loss_history[0]


def test_invalid_problem_is_rejected():
    with pytest.raises(ValueError):
        heat1d.Heat1DProblem(alpha=0.0)
