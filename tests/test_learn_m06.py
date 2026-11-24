"""Y5: 체결력 = 물리 기준 + 보정 (합성 자료). 정답 축력이 입력에 들어가지 않는다."""
from __future__ import annotations

import copy

import numpy as np

from cont.learn import m06
from cont.learn.m06 import Correction, config, evaluate, features, joint_of, reference_force, run_experiment, synthesize
from cont.packs.fastening import vdi2230
from cont.packs.fastening.joint import LoadCase


def _quiet(cfg):
    cfg = copy.deepcopy(cfg)
    s = cfg["synthetic"]
    s.update(lot_friction_spread=0.0, tool_error=0.0, torque_meas_noise_nm=0.0, angle_noise_deg=0.0, embedding_angle_deg=0.0)
    return cfg


def test_reference_is_the_fastening_pack_formula():
    cfg = config(); j = joint_of(cfg)
    row = {"torque_nm": 50.0, "angle_deg": 0.0, "force_n": 0.0, "lot": "x"}
    nom = cfg["nominal"]
    assert reference_force(row, cfg, j) == vdi2230.calculate(j, LoadCase(50.0, nom["friction_thread"], nom["friction_head"])).preload


def test_reference_error_vanishes_when_the_world_matches_the_reference():
    cfg = _quiet(config())
    rows = synthesize(cfg)
    ref = np.array([reference_force(r, cfg, joint_of(cfg)) for r in rows]); truth = np.array([r["force_n"] for r in rows])
    assert np.allclose(ref, truth, rtol=1e-9)                         # 기준이 틀리지 않는 세계에서는 기준이 정답이다


def test_features_and_prediction_never_read_the_load_cell_value():
    cfg = config(); rows = synthesize(cfg)
    model = Correction(cfg).fit(rows[:60])
    r = dict(rows[70]); r2 = dict(r, force_n=r["force_n"] * 3.0); r3 = {k: v for k, v in r.items() if k != "force_n"}
    assert np.array_equal(features(r, cfg, model.joint), features(r2, cfg, model.joint))
    assert model.predict(r) == model.predict(r2) == model.predict(r3)       # force_n이 없어도 예측한다
    assert "force_n" not in m06.FEATURES and not any("force" in f for f in cfg["correction"]["features"])


def test_test_labels_do_not_change_the_fit():
    """시험 행의 정답을 바꿔도 훈련 결과(가중치)는 그대로다."""
    cfg = config(); rows = synthesize(cfg)
    a = Correction(cfg).fit(rows[:72]).w
    changed = [dict(r, force_n=r["force_n"] * 2) if i >= 72 else r for i, r in enumerate(rows)]
    b = Correction(cfg).fit(changed[:72]).w
    assert np.array_equal(a, b)


def test_experiment_is_split_by_lot_reproducible_and_labeled():
    out = run_experiment()
    assert out == run_experiment()
    assert out["data"] == "synthetic" and "합성" in out["note"] and "판정하지 않는다" in out["note"]
    cfg = config()
    assert out["test_rows"] == len(out["split"]["test_lots"]) * cfg["synthetic"]["runs_per_lot"]
    for k in ("rmse_n", "mape", "bias", "worst_rel"):
        assert k in out["reference"] and k in out["corrected"]


def test_correction_reduces_error_on_this_synthetic_fixture():
    """기본 합성 자료에서 보정이 평균 오차를 줄인다. 실제 자료에서의 보장이 아니다 (이 고정 자료의 회귀 시험)."""
    out = run_experiment()
    assert out["corrected"]["mape"] < out["reference"]["mape"]
    assert out["corrected"]["rmse_n"] < out["reference"]["rmse_n"]


def test_real_measurement_rows_use_the_same_entry_point():
    """실측 행(같은 열 이름)이 들어올 자리: 합성 여부와 상관없이 evaluate가 돈다."""
    cfg = config(); rows = [{k: r[k] for k in ("torque_nm", "angle_deg", "force_n")} for r in synthesize(cfg)]
    out = evaluate(rows[:72], rows[72:], cfg)
    assert out["train_rows"] == 72 and out["test_rows"] == len(rows) - 72
