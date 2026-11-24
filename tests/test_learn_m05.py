"""Y4: M05 기준선 A·B를 합성 신호로 같은 분할·같은 지표에 올린다."""
from __future__ import annotations

import copy

import numpy as np

from cont.learn import m05
from cont.learn.m05 import (BaselineA, BaselineB, Tree, alarm_segments, boundary_errors, config, macro_f1, run_experiment,
                            synthesize)


def test_synthetic_is_deterministic_and_labeled():
    a, b = synthesize(), synthesize()
    assert all(np.array_equal(x.resp, y.resp) for x, y in zip(a, b))
    cfg = config()
    assert len(a) == cfg["synthetic"]["lots"] * cfg["synthetic"]["runs_per_lot"]
    assert sum(1 for r in a if r.events) == cfg["synthetic"]["lots"]          # 로트마다 0번 실행에만 이상
    r = next(r for r in a if r.events)
    s, e = r.events[0]
    assert set(r.stage[s:e]) == {2}                                            # 이상은 유지 구간 안


def test_report_is_labeled_synthetic_and_has_every_metric_for_both_models():
    out = run_experiment()
    assert out["data"] == "synthetic" and "합성" in out["note"] and "판정하지 않는다" in out["note"]
    for m in ("A", "B"):
        for k in ("stage_f1", "boundary_error_s", "normal_response_rmse", "event_recall", "false_alarms_per_hour"):
            assert k in out[m]
    assert "physics_only_rmse" in out["B"]                                     # 트리 보정이 물리 단독보다 나은지 볼 수 있다


def test_split_is_by_lot_and_training_has_only_normal_runs():
    cfg = config()
    runs = synthesize(cfg)
    out = run_experiment(cfg)
    test_lots = set(out["split"]["test_lots"])
    n_train_lots = cfg["synthetic"]["lots"] - len(test_lots)
    assert out["split"]["test_runs"] == len(test_lots) * cfg["synthetic"]["runs_per_lot"]
    assert out["split"]["train_runs"] == n_train_lots * (cfg["synthetic"]["runs_per_lot"] - 1)   # 이상 실행은 훈련에서 뺀다
    assert out["A"]["events"] == len(test_lots) == out["B"]["events"]


def test_experiment_is_reproducible():
    assert run_experiment() == run_experiment()


def test_stage_reading_does_not_use_the_true_stage():
    """정답 단계를 바꿔도 읽은 단계와 이상 신호가 변하지 않는다 (정답이 입력에 새지 않는다)."""
    cfg = config()
    runs = synthesize(cfg)
    train, r = [x for x in runs if not x.events][:12], runs[0]
    for model in (BaselineA().fit(train, cfg), BaselineB().fit(train, cfg)):
        before = model.stages(r), model.deviation(r, model.stages(r))
        r2 = copy.copy(r); r2.stage = np.zeros_like(r.stage)
        after = model.stages(r2), model.deviation(r2, model.stages(r2))
        assert np.array_equal(before[0], after[0]) and np.allclose(before[1], after[1])


def test_b_correction_ignores_the_observed_response():
    """B의 응답 기대값은 지령과 물리 예측만으로 정해진다 (관측 응답을 바꿔도 같다)."""
    cfg = config()
    runs = synthesize(cfg)
    b = BaselineB().fit([x for x in runs if not x.events][:12], cfg)
    r = runs[1]; r2 = copy.copy(r); r2.resp = r.resp + 5.0
    assert np.allclose(b.expected(r), b.expected(r2))


def test_tree_learns_a_threshold_and_respects_depth():
    X = np.linspace(0, 1, 200).reshape(-1, 1)
    y = (X[:, 0] > 0.5).astype(int)
    t = Tree("class", 2, 5, 16).fit(X, y)
    assert (t.predict(X) == y).mean() > 0.97
    reg = Tree("reg", 1, 5, 16).fit(X, np.where(X[:, 0] > 0.5, 2.0, 1.0))
    assert abs(reg.predict(np.array([[0.1]]))[0] - 1.0) < 0.1 and abs(reg.predict(np.array([[0.9]]))[0] - 2.0) < 0.1


def test_metrics_on_known_values():
    assert macro_f1(np.array([0, 0, 1, 1]), np.array([0, 0, 1, 1]), 2) == 1.0
    assert abs(macro_f1(np.array([0, 0, 1, 1]), np.array([0, 1, 1, 1]), 2) - (2 / 3 + 0.8) / 2) < 1e-9
    true = np.array([0] * 10 + [1] * 10 + [2] * 10)
    pred = np.array([0] * 12 + [1] * 8 + [2] * 10)                              # 첫 경계 2칸 늦고 둘째 경계는 같다
    errs, missed, n = boundary_errors(true, pred, reach=5)
    assert errs == [2, 0] and missed == 0 and n == 2
    assert boundary_errors(true, np.zeros(30, int), 5)[1] == 2                  # 경계를 못 찾으면 놓친 것으로 센다
    assert alarm_segments(np.array([0, 5, 5, 0, 5, 0, 5, 5, 5]), 4.0, 2) == [(1, 3), (6, 9)]   # 한 샘플짜리는 경보가 아니다


def test_false_alarms_per_hour_uses_sample_period(monkeypatch):
    cfg = config()
    runs = synthesize(cfg)
    train = [x for x in runs if not x.events][:12]
    test = [runs[1]]                                                            # 이상 없는 실행
    loose = copy.deepcopy(cfg); loose["alarm"]["k_sigma"] = 0.1                 # 감도를 매우 높여 오경보를 만든다
    out = m05.evaluate_model(BaselineB().fit(train, loose), test, loose)
    assert out["false_alarms_per_hour"] > 0
    slow = copy.deepcopy(loose); slow["synthetic"]["sample_period_s"] = 2.0
    out2 = m05.evaluate_model(BaselineB().fit(train, slow), test, slow)
    assert abs(out2["false_alarms_per_hour"] - out["false_alarms_per_hour"] / 2) < 1e-9
