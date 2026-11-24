"""열전달 역문제 PINN (가상 센서): 센서 값에서 오른쪽 끝의 대류 열전달(비오 수 Bi)을 추정한다.

u_t = alpha u_xx, x in [0,1], u(0,t) = 1, u(x,0) = 1 - x, 오른쪽 끝 -u_x = Bi u (대류).
센서 값은 유한차분 물리 선생이 정답 Bi로 만든 값에 잡음을 더한 **합성 값**이다. 실측이 아니다.
결과는 추정값과 식별 가능성(민감도로 계산한 상대 불확도), 정답·물리 선생 최소제곱 추정과의 편차만 보고한다 (증거 수준 E0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import yaml

from cont.answer import (EVIDENCE_NONE, IDENT_NONE, IDENT_OK, IDENT_WEAK, STATUS_ESTIMATED, STATUS_INPUT, STATUS_SIMULATED,
                         VALIDATION_COMPARED, Confidence, PhysicsAnswer, Quantity, Residual)
from cont.learn import require_torch
from cont.learn.config import PROFILES, TrainConfig
from cont.learn.net import build_mlp, count_parameters, set_seed
from cont.learn.record import TrainingRecord

PROBLEM = "heat_1d_inverse_bi"


@dataclass(frozen=True)
class InverseSetup:
    alpha: float = 0.5
    horizon: float = 1.0
    bi_true: float = 2.0
    sensors: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8, 1.0)
    n_times: int = 11
    noise_sigma: float = 0.01
    noise_seed: int = 0
    data_weight: float = 100.0
    bi_initial: float = 1.0
    weak_relative: float = 0.2
    none_relative: float = 1.0

    def __post_init__(self) -> None:
        if min(self.alpha, self.horizon, self.bi_true, self.bi_initial) <= 0 or self.noise_sigma < 0 or self.n_times < 2:
            raise ValueError("alpha, horizon, bi_true, bi_initial must be positive, noise_sigma non-negative, n_times >= 2")
        if not self.sensors or any(not 0.0 <= x <= 1.0 for x in self.sensors):
            raise ValueError("sensors must be positions in [0, 1]")
        if not 0 < self.weak_relative <= self.none_relative:
            raise ValueError("identifiability thresholds must satisfy 0 < weak <= none")

    @classmethod
    def load(cls, name: str = "inverse_heat") -> "InverseSetup":
        d = yaml.safe_load((PROFILES / f"{name}.yaml").read_text(encoding="utf-8"))
        ident = d.pop("identifiability")
        d["sensors"] = tuple(d["sensors"])
        return cls(**d, weak_relative=ident["weak_relative"], none_relative=ident["none_relative"])

    def times(self) -> np.ndarray:
        return np.linspace(0.0, self.horizon, self.n_times)


def teacher_at(setup: InverseSetup, bi: float, points: tuple[float, ...] | None = None) -> np.ndarray:
    """물리 선생(유한차분)의 센서 위치 온도 (n_times, n_sensors)."""
    from cont.packs.heat import fd
    xs = np.asarray(points if points is not None else setup.sensors)
    p = fd.Slab1D(1.0, setup.alpha, 1.0, lambda x: 1.0 - x, setup.horizon, conductivity=1.0, h_conv=bi, t_inf=0.0)
    steps = 200
    sol = fd.solve_1d(p, 101, steps)
    idx = [int(round(t / setup.horizon * steps)) for t in setup.times()]
    return np.array([np.interp(xs, sol.x, sol.temperature[i]) for i in idx])


def synthetic_observations(setup: InverseSetup) -> np.ndarray:
    """합성 센서 값 = 정답 Bi의 물리 선생 값 + 잡음. 실측이 아니다."""
    rng = np.random.default_rng(setup.noise_seed)
    clean = teacher_at(setup, setup.bi_true)
    return clean + rng.normal(0.0, setup.noise_sigma, clean.shape)


def relative_uncertainty(setup: InverseSetup) -> float:
    """센서 배치로 Bi를 가려낼 수 있는 정도: 민감도(du/dBi)로 계산한 상대 표준 불확도 sigma / (|S| Bi). 센서가 둔감하면 크다."""
    h = 1.0e-3 * setup.bi_true
    s = (teacher_at(setup, setup.bi_true + h) - teacher_at(setup, setup.bi_true - h)) / (2 * h)
    norm = float(np.sqrt(np.sum(s ** 2)))
    return math.inf if norm == 0.0 else (setup.noise_sigma / norm) / setup.bi_true


def least_squares_bi(setup: InverseSetup, data: np.ndarray, lo: float = 0.05, hi: float = 50.0) -> float:
    """물리 선생으로 센서 값에 가장 맞는 Bi (로그 공간 황금분할 탐색). PINN 추정의 비교 기준."""
    f = lambda lb: float(np.sum((teacher_at(setup, math.exp(lb)) - data) ** 2))
    a, b, g = math.log(lo), math.log(hi), (math.sqrt(5) - 1) / 2
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd_ = f(c), f(d)
    for _ in range(40):
        if fc < fd_:
            b, d, fd_ = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd_
            d = a + g * (b - a)
            fd_ = f(d)
    return math.exp((a + b) / 2)


@dataclass
class Fitted:
    net: Any
    log_bi: Any
    record: TrainingRecord
    setup: InverseSetup
    data: np.ndarray

    @property
    def bi(self) -> float:
        return float(self.log_bi.detach().exp())


def train(setup: InverseSetup, config: TrainConfig, data: np.ndarray | None = None, record_every: int = 10) -> Fitted:
    torch = require_torch()
    data = synthetic_observations(setup) if data is None else data
    net = build_mlp(2, config)
    set_seed(config.seed)
    dt = getattr(torch, config.dtype)
    log_bi = torch.tensor(math.log(setup.bi_initial), dtype=dt, requires_grad=True)
    gen = torch.Generator().manual_seed(config.seed)
    opt = torch.optim.Adam([{"params": net.parameters(), "lr": config.learning_rate}, {"params": [log_bi], "lr": config.learning_rate * 3}])
    sens_t = torch.as_tensor(np.repeat(setup.times(), len(setup.sensors)), dtype=dt)
    sens_x = torch.as_tensor(np.tile(np.asarray(setup.sensors), setup.n_times), dtype=dt)
    sens_u = torch.as_tensor(data.reshape(-1), dtype=dt)
    w, history, last = config.weights, [], {}
    for epoch in range(config.epochs):
        r = lambda n: torch.rand(n, generator=gen, dtype=dt)
        xt = torch.stack([r(config.n_interior), r(config.n_interior) * setup.horizon], dim=1).requires_grad_(True)
        u = net(xt)
        g = torch.autograd.grad(u.sum(), xt, create_graph=True)[0]
        u_xx = torch.autograd.grad(g[:, 0].sum(), xt, create_graph=True)[0][:, 0]
        pde = ((g[:, 1] - setup.alpha * u_xx) ** 2).mean()
        tb = r(config.n_boundary) * setup.horizon
        left = ((net(torch.stack([torch.zeros_like(tb), tb], dim=1)).squeeze(-1) - 1.0) ** 2).mean()
        rt = torch.stack([torch.ones_like(tb), tb], dim=1).requires_grad_(True)
        ur = net(rt).squeeze(-1)
        ur_x = torch.autograd.grad(ur.sum(), rt, create_graph=True)[0][:, 0]
        robin = ((ur_x + log_bi.exp() * ur) ** 2).mean()           # -u_x = Bi u
        boundary = left + robin
        xi = r(config.n_initial)
        initial = ((net(torch.stack([xi, torch.zeros_like(xi)], dim=1)).squeeze(-1) - (1.0 - xi)) ** 2).mean()
        datal = ((net(torch.stack([sens_x, sens_t], dim=1)).squeeze(-1) - sens_u) ** 2).mean()
        loss = w["pde"] * pde + w["boundary"] * boundary + w["initial"] * initial + setup.data_weight * datal
        opt.zero_grad()
        loss.backward()
        opt.step()
        if epoch % record_every == 0 or epoch == config.epochs - 1:
            history.append(float(loss.detach()))
        last = {"pde": float(pde.detach()), "boundary": float(boundary.detach()), "initial": float(initial.detach()), "data": float(datal.detach())}
    rec = TrainingRecord(PROBLEM, config, tuple(history), record_every, last, torch.__version__, "cpu", count_parameters(net) + 1)
    return Fitted(net, log_bi, rec, setup, data)


def answer(fit: Fitted, question: str = "") -> PhysicsAnswer:
    s, cfg, rec = fit.setup, fit.record.config, fit.record
    rel = relative_uncertainty(s)
    level = IDENT_NONE if rel > s.none_relative else IDENT_WEAK if rel > s.weak_relative else IDENT_OK
    basis_ident = f"센서 배치의 민감도로 계산한 상대 표준 불확도 {rel * 100:.1f}%" if math.isfinite(rel) else "센서가 Bi에 반응하지 않음"
    bi_fd = least_squares_bi(s, fit.data)
    resid = float(np.sqrt(np.mean((teacher_at(s, fit.bi) - fit.data) ** 2)))
    nan = float("nan")
    ev = ("sensor_count", "noise_sigma")
    q = [
        Quantity("alpha", "열확산계수 α (무차원, 알려진 값)", s.alpha, "-", None, None, STATUS_INPUT),
        Quantity("sensor_count", "가상 센서 수", float(len(s.sensors)), "개", None, "합성 센서: 정답 Bi로 만든 물리 선생 값 + 잡음. 실측이 아님", STATUS_INPUT),
        Quantity("noise_sigma", "센서 잡음 표준편차 (합성)", s.noise_sigma, "-", None, None, STATUS_INPUT),
        Quantity("bi_true", "합성 정답 Bi (센서 값을 만든 값)", s.bi_true, "-", None, "추정 결과를 비교하려고 아는 값이며 실제 부품의 값이 아님", STATUS_INPUT),
        Quantity("bi_pinn", "추정한 Bi (PINN)", fit.bi, "-", None, "센서 값과 방정식으로 복원한 숨은 값", STATUS_ESTIMATED, ev, level, basis_ident),
        Quantity("bi_teacher_fit", "추정한 Bi (물리 선생 최소제곱, 비교 기준)", bi_fd, "-", None, None, STATUS_ESTIMATED, ev, level, basis_ident),
        Quantity("deviation_to_true", "추정 Bi − 합성 정답", fit.bi - s.bi_true, "-"),
        Quantity("deviation_to_teacher_fit", "PINN 추정 Bi − 물리 선생 최소제곱 Bi", fit.bi - bi_fd, "-"),
        Quantity("relative_uncertainty", "Bi의 상대 표준 불확도 (센서 민감도 기준)", rel if math.isfinite(rel) else None, "-"),
        Quantity("sensor_residual_rms", "추정 Bi로 물리 선생을 돌린 값과 센서 값의 차이 (RMS)", resid, "-"),
    ]
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=tuple(q), method="PINN 역문제 (가상 센서)",
        basis=(
            "방정식 u_t = α u_xx, 왼쪽 u=1, 초기 u=1-x, 오른쪽 -u_x = Bi u. Bi를 학습 변수로 두고 센서 값과의 차이를 손실에 더해 추정한다",
            f"센서 {len(s.sensors)}개 x={list(s.sensors)}, 시각 {s.n_times}개, 잡음 {s.noise_sigma:g}. 센서 값은 합성이며 실측과 대조하지 않았다",
            f"학습 설정: 시드 {cfg.seed}, 은닉층 {list(cfg.hidden)}, 에포크 {cfg.epochs}, 학습률 {cfg.learning_rate:g}, 자료 손실 가중 {s.data_weight:g}, 시작값 Bi={s.bi_initial:g}",
            f"마지막 손실: 방정식 {rec.final_losses.get('pde', nan):.3e}, 경계 {rec.final_losses.get('boundary', nan):.3e}, 초기 {rec.final_losses.get('initial', nan):.3e}, "
            f"자료 {rec.final_losses.get('data', nan):.3e}. 학습 지문 {rec.fingerprint()}",
            f"식별 가능성: {basis_ident}. 기준 {s.weak_relative * 100:g}% 초과는 약함, {s.none_relative * 100:g}% 초과는 가려낼 수 없음 (설정값, 제품 기준 아님)",
            "판정 없음: 추정값과 정답·물리 선생과의 편차는 값만 보고한다",
        ),
        confidence=Confidence("low", "합성 센서 값에서 복원했다. 잡음 한 번의 결과이며 반복 분포와 실측 대조는 하지 않았다"),
        source="사람이 정한 가상 센서 조건 (합성). 학습 데이터는 합성 센서 값과 방정식에서 뽑은 배치점", uncertainty="센서 민감도로 계산한 상대 표준 불확도를 식별 가능성에 적었다. 잡음 반복 분포는 보고하지 않음",
        residuals=(Residual("sensor_fit", "센서 값과의 차이 (RMS)", resid, "-", "잡음 크기와 비슷하면 자료에 맞는다는 뜻일 뿐 Bi가 맞다는 뜻은 아니다"),),
        scope="무차원 1차원 열전도, 왼쪽 온도 고정과 오른쪽 대류, 상수 물성, 합성 센서",
        failure_conditions=("센서가 오른쪽 끝에서 멀어 Bi에 둔감할 때 (식별 가능성이 약함)", "잡음이 크거나 센서가 적을 때", "방정식이나 경계 조건이 실제와 다를 때"),
        validation=VALIDATION_COMPARED, evidence_level=EVIDENCE_NONE, presentation=("table:quantities",),
        inputs={"problem": PROBLEM, "setup": {k: (list(v) if isinstance(v, tuple) else v) for k, v in s.__dict__.items()}, "config": cfg.to_dict()},
    )
