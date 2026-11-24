"""1차원 비정상 열전도 PINN 벤치마크 (해석해가 있는 문제).

u_t = alpha u_xx,  x in [0,1],  t in [0,T],  u(0,t) = u(1,t) = 0,  u(x,0) = sin(pi x)
해석해 u = exp(-alpha pi^2 t) sin(pi x). 무차원 문제이며 측정 데이터를 쓰지 않는다 (방정식·경계·초기 조건의 잔차로만 학습).

결과는 해석해와 유한차분(물리 선생)에 대한 편차만 보고한다. 일치 판정 기준은 없다 (증거 수준 E0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from cont.answer import (EVIDENCE_NONE, STATUS_INPUT, STATUS_SIMULATED, VALIDATION_COMPARED, Confidence, PhysicsAnswer,
                         Quantity, Residual)
from cont.learn import require_torch
from cont.learn.config import TrainConfig
from cont.learn.net import build_mlp, count_parameters, set_seed
from cont.learn.record import TrainingRecord

PROBLEM = "heat_1d_sine"


@dataclass(frozen=True)
class Heat1DProblem:
    alpha: float = 0.1          # 무차원 열확산계수
    horizon: float = 1.0        # T

    def __post_init__(self) -> None:
        if self.alpha <= 0 or self.horizon <= 0:
            raise ValueError("alpha and horizon must be positive")

    def exact(self, x, t):
        return np.exp(-self.alpha * math.pi ** 2 * np.asarray(t)) * np.sin(math.pi * np.asarray(x))


@dataclass
class Trained:
    net: Any
    record: TrainingRecord
    problem: Heat1DProblem


def _losses(net, problem: Heat1DProblem, x, t, xb, tb, xi, torch):
    xt = torch.stack([x, t], dim=1).requires_grad_(True)
    u = net(xt)
    g = torch.autograd.grad(u.sum(), xt, create_graph=True)[0]
    u_x, u_t = g[:, 0], g[:, 1]
    u_xx = torch.autograd.grad(u_x.sum(), xt, create_graph=True)[0][:, 0]
    pde = ((u_t - problem.alpha * u_xx) ** 2).mean()
    ub = net(torch.stack([xb, tb], dim=1))
    boundary = (ub ** 2).mean()
    ui = net(torch.stack([xi, torch.zeros_like(xi)], dim=1)).squeeze(-1)
    initial = ((ui - torch.sin(math.pi * xi)) ** 2).mean()
    return pde, boundary, initial


def train(problem: Heat1DProblem, config: TrainConfig, record_every: int = 10) -> Trained:
    """설정과 시드가 같으면 같은 프로세스·같은 환경에서 같은 결과가 나온다."""
    torch = require_torch()
    net = build_mlp(2, config)                 # 입력 (x, t)
    set_seed(config.seed)
    dt = getattr(torch, config.dtype)
    gen = torch.Generator().manual_seed(config.seed)
    opt = torch.optim.Adam(net.parameters(), lr=config.learning_rate)
    w = config.weights
    history: list[float] = []
    last: dict[str, float] = {}
    for epoch in range(config.epochs):
        x = torch.rand(config.n_interior, generator=gen, dtype=dt)
        t = torch.rand(config.n_interior, generator=gen, dtype=dt) * problem.horizon
        tb = torch.rand(config.n_boundary, generator=gen, dtype=dt) * problem.horizon
        xb = (torch.rand(config.n_boundary, generator=gen, dtype=dt) > 0.5).to(dt)     # 0 또는 1
        xi = torch.rand(config.n_initial, generator=gen, dtype=dt)
        pde, boundary, initial = _losses(net, problem, x, t, xb, tb, xi, torch)
        loss = w["pde"] * pde + w["boundary"] * boundary + w["initial"] * initial
        opt.zero_grad()
        loss.backward()
        opt.step()
        if epoch % record_every == 0 or epoch == config.epochs - 1:
            history.append(float(loss.detach()))
        last = {"pde": float(pde.detach()), "boundary": float(boundary.detach()), "initial": float(initial.detach())}
    rec = TrainingRecord(PROBLEM, config, tuple(history), record_every, last, torch.__version__, "cpu", count_parameters(net))
    return Trained(net, rec, problem)


def predict(trained: Trained, x: np.ndarray, t: np.ndarray) -> np.ndarray:
    """(x, t) 같은 모양의 배열에서의 PINN 예측."""
    torch = require_torch()
    dt = getattr(torch, trained.record.config.dtype)
    xt = torch.stack([torch.as_tensor(np.ravel(x), dtype=dt), torch.as_tensor(np.ravel(t), dtype=dt)], dim=1)
    with torch.no_grad():
        return trained.net(xt).squeeze(-1).numpy().reshape(np.shape(x))


def pde_residual_rms(trained: Trained, n: int = 2000, seed: int = 12345) -> float:
    """학습에 쓰지 않은 점에서 방정식 잔차(u_t - alpha u_xx)의 RMS."""
    torch = require_torch()
    dt = getattr(torch, trained.record.config.dtype)
    gen = torch.Generator().manual_seed(seed)
    x = torch.rand(n, generator=gen, dtype=dt)
    t = torch.rand(n, generator=gen, dtype=dt) * trained.problem.horizon
    xt = torch.stack([x, t], dim=1).requires_grad_(True)
    u = trained.net(xt)
    g = torch.autograd.grad(u.sum(), xt, create_graph=True)[0]
    u_xx = torch.autograd.grad(g[:, 0].sum(), xt)[0][:, 0]
    return float(((g[:, 1] - trained.problem.alpha * u_xx) ** 2).mean().sqrt().detach())


def teacher_field(problem: Heat1DProblem, xs: np.ndarray, times: np.ndarray, nx: int = 201, steps: int = 400) -> np.ndarray:
    """유한차분 물리 선생의 같은 격자 온도 (len(times), len(xs))."""
    from cont.packs.heat import fd
    sol = fd.solve_1d(fd.Slab1D(1.0, problem.alpha, 0.0, lambda x: np.sin(math.pi * x), problem.horizon, t_right=0.0), nx, steps)
    idx = [int(round(t / problem.horizon * steps)) for t in times]
    return np.array([np.interp(xs, sol.x, sol.temperature[i]) for i in idx])


def answer(trained: Trained, question: str = "", nx: int = 101, n_times: int = 11) -> PhysicsAnswer:
    p, cfg, rec = trained.problem, trained.record.config, trained.record
    xs = np.linspace(0.0, 1.0, nx)
    times = np.linspace(0.0, p.horizon, n_times)
    gx, gt = np.meshgrid(xs, times)
    pred = predict(trained, gx, gt)
    ref = p.exact(gx, gt)
    teacher = teacher_field(p, xs, times)
    d_an, d_te = pred - ref, pred - teacher
    rms = lambda a: float(np.sqrt(np.mean(a ** 2)))
    pde_res = pde_residual_rms(trained)
    q = [
        Quantity("alpha", "열확산계수 α (무차원)", p.alpha, "-", None, None, STATUS_INPUT),
        Quantity("horizon", "계산 시간 T (무차원)", p.horizon, "-", None, None, STATUS_INPUT),
        Quantity("pinn_peak_final", "마지막 시각의 최고 온도 (PINN)", float(pred[-1].max()), "-"),
        Quantity("reference_peak_final", "같은 시각 해석해의 최고 온도", float(ref[-1].max()), "-"),
        Quantity("deviation_analytic_rms", "해석해와의 편차 (RMS)", rms(d_an), "-", "그 편차가 허용되는지는 판정하지 않는다"),
        Quantity("deviation_analytic_max", "해석해와의 편차 (최대)", float(np.abs(d_an).max()), "-"),
        Quantity("deviation_teacher_rms", "유한차분(물리 선생)과의 편차 (RMS)", rms(d_te), "-"),
        Quantity("deviation_teacher_max", "유한차분(물리 선생)과의 편차 (최대)", float(np.abs(d_te).max()), "-"),
    ]
    nan = float("nan")
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=tuple(q), method="PINN (물리 정보 신경망)",
        basis=(
            "방정식 잔차 u_t - α u_xx, 경계 조건 u(0,t)=u(1,t)=0, 초기 조건 u(x,0)=sin(πx)의 손실로 학습한다. 측정 데이터를 쓰지 않는다",
            f"학습 설정: 시드 {cfg.seed}, 은닉층 {list(cfg.hidden)} ({cfg.activation}), 에포크 {cfg.epochs}, 학습률 {cfg.learning_rate:g}, "
            f"내부점 {cfg.n_interior}/경계점 {cfg.n_boundary}/초기점 {cfg.n_initial}, 손실 가중 {cfg.weights}, {cfg.dtype}",
            f"마지막 손실: 방정식 {rec.final_losses.get('pde', nan):.3e}, 경계 {rec.final_losses.get('boundary', nan):.3e}, "
            f"초기 {rec.final_losses.get('initial', nan):.3e}. 학습 지문 {rec.fingerprint()}",
            f"비교 격자: x {nx}점, t {n_times}개 시각. 물리 선생은 크랭크-니콜슨 유한차분",
            "가정: 무차원 문제, 상수 물성. 합성 문제이며 실측과 대조하지 않았다",
            "판정 없음: 해석해·물리 선생과의 편차는 값만 보고한다. 일치 기준은 정해지지 않았다",
        ),
        confidence=Confidence("low", "학습한 대리모델이다. 해석해가 있는 합성 문제에서 편차만 확인했고 학습 범위 밖과 실측은 확인하지 않았다"),
        source="사람이 정한 기준 문제 조건 (해석해가 있는 합성 문제). 학습 데이터는 방정식에서 뽑은 배치점뿐",
        uncertainty="", residuals=(Residual("pde_residual", "방정식 잔차 u_t - α u_xx (학습에 쓰지 않은 점의 RMS)", pde_res, "-",
                                           "방정식을 얼마나 만족하는지만 말해 준다. 해와 얼마나 가까운지는 편차를 본다"),),
        scope="무차원 1차원 열전도, x와 t가 학습 범위 안, 양 끝 온도 고정",
        failure_conditions=("x나 t가 학습 범위(0~1, 0~T) 밖일 때", "α나 경계 조건이 학습한 것과 다를 때", "학습이 수렴하지 않았을 때 (손실을 본다)"),
        validation=VALIDATION_COMPARED, evidence_level=EVIDENCE_NONE,
        presentation=("table:quantities",),
        inputs={"problem": PROBLEM, "alpha": p.alpha, "horizon": p.horizon, "config": cfg.to_dict()},
    )
