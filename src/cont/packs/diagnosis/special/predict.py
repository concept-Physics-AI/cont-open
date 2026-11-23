"""품질 예측: 공정 값(속도, 온도, 압력 등)으로 두께 같은 품질 값을 예측한다.

공통 진단과 달리 정답(실제로 잰 품질 값)이 있는 데이터로 모델을 만들어야 한다. 그래서 특화 진단이다.
모델은 1차식(최소제곱)이다. 예측에는 학습 때의 오차 크기를 불확실도로 붙이고,
학습 때 보지 못한 운전 범위의 표본은 "범위 밖"으로 표시한다. 규격(하한, 상한)은 입력으로 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from cont.answer import Confidence, PhysicsAnswer, Quantity
from cont.answer import STATUS_PREDICTED
from cont.packs.diagnosis.detect import intervals
from cont.packs.diagnosis.pack import SignalResult
from cont.packs.diagnosis.profile import Settings, load_settings


@dataclass(frozen=True)
class QualityModel:
    target: str
    features: tuple[str, ...]
    coef: np.ndarray                    # [절편, 특성별 계수...]
    sigma: float                        # 학습 데이터에서의 예측 오차 크기 (표준편차)
    low: np.ndarray                     # 학습 때 본 특성 범위
    high: np.ndarray
    n: int

    def predict(self, data: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
        """(예측값, 학습 범위 안인지 여부)."""
        x = np.column_stack([np.asarray(data[f], float) for f in self.features])
        inside = np.all((x >= self.low) & (x <= self.high), axis=1)
        return self.coef[0] + x @ self.coef[1:], inside


@dataclass(frozen=True)
class QualityPrediction:
    answer: PhysicsAnswer
    settings: Settings
    model: QualityModel
    time: np.ndarray
    chart: SignalResult                 # 예측값과 규격 범위. 화면용
    predicted: np.ndarray
    inside: np.ndarray


def fit_quality(train: Mapping[str, Any], target: str, features: Sequence[str], profile: str | None = None) -> QualityModel:
    st = load_settings(profile)
    for k in [target, *features]:
        if k not in train:
            raise ValueError(f"training data has no column '{k}'")
    y = np.asarray(train[target], float)
    x = np.column_stack([np.asarray(train[f], float) for f in features])
    if len(y) < st.min_training_samples:
        raise ValueError(f"need at least {st.min_training_samples} labelled samples, got {len(y)}")
    a = np.column_stack([np.ones(len(y)), x])
    coef = np.linalg.lstsq(a, y, rcond=None)[0]
    resid = y - a @ coef
    sigma = float(np.sqrt(np.sum(resid ** 2) / max(len(y) - a.shape[1], 1)))
    return QualityModel(target, tuple(features), coef, sigma, x.min(axis=0), x.max(axis=0), len(y))


def assess_quality(model: QualityModel, current: Mapping[str, Any], spec: tuple[float, float], time: str | None = None,
                   measured: str | None = None, label: str = "두께", unit: str = "", question: str = "",
                   profile: str | None = None) -> QualityPrediction:
    st = load_settings(profile)
    lo, hi = float(spec[0]), float(spec[1])
    if not lo < hi:
        raise ValueError("spec must be (lower, upper) with lower < upper")
    pred, inside = model.predict(current)
    n = len(pred)
    tt = np.asarray(current[time], float) if time else np.arange(n, dtype=float)
    mid, half = (lo + hi) / 2, (hi - lo) / 2
    z = (pred - mid) / half                       # 규격 한계가 ±1
    ivs = tuple(intervals(z, model.target, 1.0, st.min_run, st.merge_gap))
    out = (pred < lo) | (pred > hi)
    first = min((iv.start for iv in ivs), default=None)
    quantities = [
        Quantity("predicted_mean", f"예측 {label} 평균", float(pred.mean()), unit, (lo, hi)),
        Quantity("prediction_uncertainty", "예측 불확실도 (학습 때의 오차 크기)", model.sigma, unit),
        Quantity("out_of_spec_fraction", "규격을 벗어날 것으로 예측된 비율", float(out.mean()), "-"),
        Quantity("out_of_spec_intervals", "규격 이탈 예측 구간 수", float(len(ivs)), "개"),
        Quantity("first_out_of_spec_time", "규격 이탈이 처음 예측된 시각", None if first is None else float(tt[first]), "시간 열의 단위",
                 note=None if first is not None else "규격 이탈 예측 구간이 없다"),
        Quantity("outside_training_range_fraction", "학습 때 보지 못한 운전 범위의 비율", float((~inside).mean()), "-",
                 note="이 표본의 예측은 믿기 어렵다"),
    ]
    terms = " ".join(f"{c:+.4g}×{f}" for f, c in zip(model.features, model.coef[1:]))
    basis = [f"품질 예측 모델: {label}({model.target}) = {model.coef[0]:.4g} {terms}. 정답이 있는 표본 {model.n:,}개로 만든 1차식",
             f"규격 {lo:g}~{hi:g}{unit}. 예측이 규격을 연속 {st.min_run}표본 이상 벗어나면 이탈 예측 구간으로 봄"]
    for iv in ivs:
        seg = pred[iv.start:iv.end + 1]
        limit = f"상한 {hi:g}{unit} 초과" if iv.direction == "up" else f"하한 {lo:g}{unit} 미달"
        basis.append(f"{tt[iv.start]:g}~{tt[iv.end]:g} 구간: 예측 {label} 평균 {seg.mean():.4g}{unit}, 규격 {limit} → {label} 규격 이탈 예측")
    if not ivs:
        basis.append(f"모든 구간에서 예측 {label} 값이 규격 안에 있음")
    if (~inside).any():
        basis.append(f"표본의 {(~inside).mean() * 100:.1f}%는 학습 때 보지 못한 운전 범위라 예측을 믿기 어려움")
    if measured:
        m = np.asarray(current[measured], float)
        err = float(np.mean(np.abs(m - pred)))
        quantities.append(Quantity("mean_absolute_error", "실측과 예측의 평균 차이", err, unit, note=f"실측 열: {measured}"))
        basis.append(f"실측({measured})과 비교한 평균 차이 {err:.3g}{unit}")
    answer = PhysicsAnswer(status=STATUS_PREDICTED, 
        question=question, quantities=tuple(quantities), method="AI 대리모델 (정답 데이터로 만든 1차 회귀)", basis=tuple(basis),
        confidence=Confidence("low", "모델과 계산은 가상 데이터로 확인했지만 현장의 실측 품질 값으로 만들거나 검증한 것이 아니다"),
        presentation=("graph:prediction_vs_spec", "table:quantities", "list:evidence"),
        inputs={"target": model.target, "features": list(model.features), "spec": [lo, hi], "time": time, "measured": measured},
    )
    scale = np.full(n, half)                      # 화면의 범위(중앙 ± z_limit×scale)가 규격이 되도록
    chart = SignalResult(model.target, "quality", f"예측 {label}", unit, pred, np.full(n, mid), scale / st.z_limit, z * st.z_limit, ivs,
                         float(inside.mean()))
    return QualityPrediction(answer, st, model, tt, chart, pred, inside)
