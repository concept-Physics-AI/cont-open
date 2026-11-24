"""M06 체결력 = 물리 기준 + 보정 구조 (Y5). 합성 자료만 쓴다. torch가 필요 없다.

물리 기준: 측정한 조임 토크와 대표 마찰로 VDI 2230 식에서 체결력을 구한다 (cont.packs.fastening).
보정: 현장에서 잴 수 있는 신호(조임 각도의 기준 대비 편차, 토크)로 기준의 상대 오차를 예측하는 작은 선형 모형.
정답 축력(로드셀)은 훈련의 목표값으로만 쓰고, 입력 특징에는 들어가지 않는다.
실측 자료는 같은 행 형식(torque_nm, angle_deg, force_n, lot)으로 `evaluate`에 넣는다. 판정은 하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from cont.learn.split import assert_no_leakage, group_split
from cont.packs.fastening import vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase, Plate

_CFG = Path(__file__).resolve().parents[3] / "config" / "learn" / "m06.yaml"


def config() -> dict[str, Any]:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8"))


def joint_of(cfg: dict[str, Any]) -> BoltedJoint:
    j = cfg["joint"]
    plate = Plate(j["plate_thickness_mm"], j["plate_e_mpa"], 700.0)
    return BoltedJoint(j["size"], j["property_class"], plate, plate, outer_diameter=j["outer_diameter_mm"])


def preload(joint: BoltedJoint, torque_nm: float, mu_g: float, mu_k: float) -> float:
    return vdi2230.calculate(joint, LoadCase(torque_nm, mu_g, mu_k)).preload


def compliance_mm_per_n(joint: BoltedJoint) -> float:
    return vdi2230.bolt_resilience(joint) + vdi2230.plate_resilience(joint)


def reference_angle_deg(joint: BoltedJoint, force_n: float) -> float:
    """체결력이 이만큼일 때 탄성으로 돌아가는 각도: 늘어남 / 피치 × 360."""
    return force_n * compliance_mm_per_n(joint) / joint.p * 360.0


def synthesize(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """행: lot, run, torque_nm(측정), angle_deg(측정), force_n(로드셀 정답). 실제 계측 행도 같은 형식이다."""
    cfg = cfg or config()
    s, nom, joint = cfg["synthetic"], cfg["nominal"], joint_of(cfg)
    rng = np.random.default_rng(s["seed"])
    rows: list[dict[str, Any]] = []
    for lot in range(s["lots"]):
        mu_g = nom["friction_thread"] * (1 + rng.uniform(-s["lot_friction_spread"], s["lot_friction_spread"]))
        mu_k = nom["friction_head"] * (1 + rng.uniform(-s["lot_friction_spread"], s["lot_friction_spread"]))
        for k in range(s["runs_per_lot"]):
            setpoint = float(rng.choice(s["torque_setpoints_nm"]))
            actual = setpoint * (1 + rng.normal(0.0, s["tool_error"]))
            force = preload(joint, actual, mu_g, mu_k)
            angle = reference_angle_deg(joint, force) + s["embedding_angle_deg"] + rng.normal(0.0, s["angle_noise_deg"])
            rows.append({"lot": f"L{lot}", "run": k, "torque_nm": actual + rng.normal(0.0, s["torque_meas_noise_nm"]),
                         "angle_deg": float(angle), "force_n": float(force)})
    return rows


def reference_force(row: Mapping[str, Any], cfg: dict[str, Any], joint: BoltedJoint) -> float:
    nom = cfg["nominal"]
    return preload(joint, float(row["torque_nm"]), nom["friction_thread"], nom["friction_head"])


FEATURES = ("angle_dev", "torque_rel")


def features(row: Mapping[str, Any], cfg: dict[str, Any], joint: BoltedJoint) -> np.ndarray:
    """보정의 입력. 측정한 토크와 각도만 받는다 (row의 force_n은 읽지 않는다)."""
    f_ref = reference_force(row, cfg, joint)
    angle_ref = reference_angle_deg(joint, f_ref)
    table = {"angle_dev": float(row["angle_deg"]) / angle_ref - 1.0,
             "torque_rel": float(row["torque_nm"]) / cfg["correction"]["reference_torque_nm"] - 1.0}
    return np.array([table[k] for k in cfg["correction"]["features"]])


class Correction:
    """기준 대비 상대 오차 r = F_정답 / F_기준 − 1 을 예측하는 능형(ridge) 선형 모형."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg, self.joint = cfg, joint_of(cfg)

    def fit(self, rows: Sequence[Mapping[str, Any]]) -> "Correction":
        X = np.array([features(r, self.cfg, self.joint) for r in rows])
        y = np.array([r["force_n"] / reference_force(r, self.cfg, self.joint) - 1.0 for r in rows])   # 정답은 목표값으로만 쓴다
        A = np.column_stack([np.ones(len(X)), X])
        lam = np.eye(A.shape[1]) * self.cfg["correction"]["ridge"]
        lam[0, 0] = 0.0
        self.w = np.linalg.solve(A.T @ A + lam, A.T @ y)
        return self

    def predict(self, row: Mapping[str, Any]) -> float:
        """보정한 체결력 (N). row에 force_n이 있어도 읽지 않는다."""
        x = features(row, self.cfg, self.joint)
        return reference_force(row, self.cfg, self.joint) * (1.0 + self.w[0] + float(x @ self.w[1:]))


def errors(pred: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    rel = (pred - truth) / truth
    return {"rmse_n": float(np.sqrt(((pred - truth) ** 2).mean())), "mape": float(np.abs(rel).mean()),
            "bias": float(rel.mean()), "worst_rel": float(np.abs(rel).max())}


def evaluate(train: Sequence[Mapping[str, Any]], test: Sequence[Mapping[str, Any]], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """훈련 행으로 보정을 맞추고, 시험 행에서 기준과 보정의 오차를 같은 지표로 잰다."""
    cfg = cfg or config()
    model = Correction(cfg).fit(train)
    truth = np.array([r["force_n"] for r in test])
    ref = np.array([reference_force(r, cfg, model.joint) for r in test])
    cor = np.array([model.predict(r) for r in test])
    return {"reference": errors(ref, truth), "corrected": errors(cor, truth), "test_rows": len(test), "train_rows": len(train),
            "features": list(cfg["correction"]["features"])}


def run_experiment(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or config()
    rows = synthesize(cfg)
    sp = group_split(rows, ["lot"], cfg["split"]["test_fraction"], cfg["split"]["seed"])
    assert_no_leakage(rows, sp)
    out = evaluate([rows[i] for i in sp.train], [rows[i] for i in sp.test], cfg)
    out.update({"data": "synthetic", "split": {"fingerprint": sp.fingerprint, "test_lots": sorted({rows[i]["lot"] for i in sp.test})},
                "note": ("합성 자료의 결과이며 실제 체결 성능이 아니다. 판정하지 않는다. 각도는 체결력에서 계산해 만들었으므로 "
                         "보정이 잘 맞는 것은 구조적이다. 실제 계측에서는 각도 센서의 오차와 토크-각도 동기가 따로 확인돼야 한다.")})
    return out
