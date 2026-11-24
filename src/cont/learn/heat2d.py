"""2차원 비정상 열전도 PINN 벤치마크 (해석해가 있는 문제).

u_t = alpha (u_xx + u_yy),  (x,y) in [0,1]^2,  t in [0,T],  네 변 u = 0,  u(x,y,0) = sin(pi x) sin(pi y)
해석해 u = exp(-2 alpha pi^2 t) sin(pi x) sin(pi y). 무차원, 측정 데이터 없음.
유한차분 물리 선생(cont.packs.heat.fd.solve_2d)과 해석해에 대한 편차만 보고한다. 일치 판정 기준은 없다 (증거 수준 E0).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from cont.answer import (EVIDENCE_NONE, STATUS_INPUT, STATUS_SIMULATED, VALIDATION_COMPARED, Confidence, Field, PhysicsAnswer,
                         Quantity, Residual)
from cont.learn import require_torch
from cont.learn.config import TrainConfig
from cont.learn.net import build_mlp, count_parameters, set_seed
from cont.learn.record import TrainingRecord

PROBLEM = "heat_2d_sine"


@dataclass(frozen=True)
class Heat2DProblem:
    alpha: float = 0.05
    horizon: float = 1.0

    def __post_init__(self) -> None:
        if self.alpha <= 0 or self.horizon <= 0:
            raise ValueError("alpha and horizon must be positive")

    def exact(self, x, y, t):
        return np.exp(-2.0 * self.alpha * math.pi ** 2 * np.asarray(t)) * np.sin(math.pi * np.asarray(x)) * np.sin(math.pi * np.asarray(y))


@dataclass
class Trained:
    net: Any
    record: TrainingRecord
    problem: Heat2DProblem


def _grads(net, pts, torch):
    pts = pts.requires_grad_(True)
    u = net(pts)
    g = torch.autograd.grad(u.sum(), pts, create_graph=True)[0]
    uxx = torch.autograd.grad(g[:, 0].sum(), pts, create_graph=True)[0][:, 0]
    uyy = torch.autograd.grad(g[:, 1].sum(), pts, create_graph=True)[0][:, 1]
    return g[:, 2], uxx + uyy


def train(problem: Heat2DProblem, config: TrainConfig, record_every: int = 10) -> Trained:
    torch = require_torch()
    net = build_mlp(3, config)                  # 입력 (x, y, t)
    set_seed(config.seed)
    dt = getattr(torch, config.dtype)
    gen = torch.Generator().manual_seed(config.seed)
    opt = torch.optim.Adam(net.parameters(), lr=config.learning_rate)
    w = config.weights
    history: list[float] = []
    last: dict[str, float] = {}
    pi = math.pi
    for epoch in range(config.epochs):
        r = lambda n: torch.rand(n, generator=gen, dtype=dt)
        pts = torch.stack([r(config.n_interior), r(config.n_interior), r(config.n_interior) * problem.horizon], dim=1)
        u_t, lap = _grads(net, pts, torch)
        pde = ((u_t - problem.alpha * lap) ** 2).mean()
        n = config.n_boundary                                       # 네 변에서 번갈아 뽑는다
        s, tb, side = r(n), r(n) * problem.horizon, torch.randint(0, 4, (n,), generator=gen)
        xb = torch.where(side == 0, torch.zeros_like(s), torch.where(side == 1, torch.ones_like(s), s))
        yb = torch.where(side == 2, torch.zeros_like(s), torch.where(side == 3, torch.ones_like(s), s))
        boundary = (net(torch.stack([xb, yb, tb], dim=1)) ** 2).mean()
        xi, yi = r(config.n_initial), r(config.n_initial)
        ui = net(torch.stack([xi, yi, torch.zeros_like(xi)], dim=1)).squeeze(-1)
        initial = ((ui - torch.sin(pi * xi) * torch.sin(pi * yi)) ** 2).mean()
        loss = w["pde"] * pde + w["boundary"] * boundary + w["initial"] * initial
        opt.zero_grad()
        loss.backward()
        opt.step()
        if epoch % record_every == 0 or epoch == config.epochs - 1:
            history.append(float(loss.detach()))
        last = {"pde": float(pde.detach()), "boundary": float(boundary.detach()), "initial": float(initial.detach())}
    rec = TrainingRecord(PROBLEM, config, tuple(history), record_every, last, torch.__version__, "cpu", count_parameters(net))
    return Trained(net, rec, problem)


def predict(trained: Trained, x, y, t) -> np.ndarray:
    torch = require_torch()
    dt = getattr(torch, trained.record.config.dtype)
    pts = torch.stack([torch.as_tensor(np.ravel(a), dtype=dt) for a in (x, y, t)], dim=1)
    with torch.no_grad():
        return trained.net(pts).squeeze(-1).numpy().reshape(np.shape(x))


def pde_residual_rms(trained: Trained, n: int = 2000, seed: int = 12345) -> float:
    torch = require_torch()
    dt = getattr(torch, trained.record.config.dtype)
    gen = torch.Generator().manual_seed(seed)
    pts = torch.stack([torch.rand(n, generator=gen, dtype=dt) for _ in range(3)], dim=1)
    pts[:, 2] *= trained.problem.horizon
    u_t, lap = _grads(trained.net, pts, torch)
    return float(((u_t - trained.problem.alpha * lap) ** 2).mean().sqrt().detach())


def teacher_final(problem: Heat2DProblem, n: int = 41, steps: int = 80):
    """물리 선생(유한차분)의 마지막 시각 온도장 (x, y, 값)."""
    from cont.packs.heat import fd
    sol = fd.solve_2d(fd.Plate2D(1.0, 1.0, problem.alpha, 0.0, lambda X, Y: np.sin(math.pi * X) * np.sin(math.pi * Y), problem.horizon),
                      n, n, steps)
    return sol.x, sol.y, sol.temperature[-1]


def answer(trained: Trained, question: str = "", n: int = 41) -> PhysicsAnswer:
    p, cfg, rec = trained.problem, trained.record.config, trained.record
    tx, ty, tfield = teacher_final(p, n)
    gx, gy = np.meshgrid(tx, ty)
    pred = predict(trained, gx, gy, np.full_like(gx, p.horizon))
    ref = p.exact(gx, gy, p.horizon)
    d_an, d_te = pred - ref, pred - tfield
    rms = lambda a: float(np.sqrt(np.mean(a ** 2)))
    nan = float("nan")
    q = [
        Quantity("alpha", "열확산계수 α (무차원)", p.alpha, "-", None, None, STATUS_INPUT),
        Quantity("horizon", "계산 시간 T (무차원)", p.horizon, "-", None, None, STATUS_INPUT),
        Quantity("pinn_peak_final", "마지막 시각의 최고 온도 (PINN)", float(pred.max()), "-"),
        Quantity("reference_peak_final", "같은 시각 해석해의 최고 온도", float(ref.max()), "-"),
        Quantity("deviation_analytic_rms", "해석해와의 편차 (RMS, 마지막 시각)", rms(d_an), "-", "그 편차가 허용되는지는 판정하지 않는다"),
        Quantity("deviation_analytic_max", "해석해와의 편차 (최대)", float(np.abs(d_an).max()), "-"),
        Quantity("deviation_teacher_rms", "유한차분(물리 선생)과의 편차 (RMS)", rms(d_te), "-"),
        Quantity("deviation_teacher_max", "유한차분(물리 선생)과의 편차 (최대)", float(np.abs(d_te).max()), "-"),
    ]
    field_dev = Field("pinn_minus_teacher", "PINN − 유한차분 (마지막 시각)", "-", ("x", "y"), "-", tuple(float(v) for v in tx),
                      tuple(float(v) for v in ty), tuple(tuple(float(v) for v in row) for row in d_te),
                      note="편차 분포. 어디서 어긋나는지 볼 뿐 판정하지 않는다")
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=tuple(q), method="PINN (물리 정보 신경망)",
        basis=(
            "방정식 잔차 u_t - α (u_xx + u_yy), 네 변 u=0, 초기 조건 sin(πx) sin(πy)의 손실로 학습한다. 측정 데이터를 쓰지 않는다",
            f"학습 설정: 시드 {cfg.seed}, 은닉층 {list(cfg.hidden)} ({cfg.activation}), 에포크 {cfg.epochs}, 학습률 {cfg.learning_rate:g}, "
            f"내부점 {cfg.n_interior}/경계점 {cfg.n_boundary}/초기점 {cfg.n_initial}, 손실 가중 {cfg.weights}, {cfg.dtype}",
            f"마지막 손실: 방정식 {rec.final_losses.get('pde', nan):.3e}, 경계 {rec.final_losses.get('boundary', nan):.3e}, "
            f"초기 {rec.final_losses.get('initial', nan):.3e}. 학습 지문 {rec.fingerprint()}",
            f"비교 격자 {n} x {n}. 물리 선생은 크랭크-니콜슨 유한차분",
            "가정: 무차원 문제, 상수 물성. 합성 문제이며 실측과 대조하지 않았다",
            "판정 없음: 해석해·물리 선생과의 편차는 값만 보고한다. 일치 기준은 정해지지 않았다",
        ),
        confidence=Confidence("low", "학습한 대리모델이다. 해석해가 있는 합성 문제에서 편차만 확인했고 학습 범위 밖과 실측은 확인하지 않았다"),
        source="사람이 정한 기준 문제 조건 (해석해가 있는 합성 문제). 학습 데이터는 방정식에서 뽑은 배치점뿐", uncertainty="",
        residuals=(Residual("pde_residual", "방정식 잔차 (학습에 쓰지 않은 점의 RMS)", pde_residual_rms(trained), "-",
                            "방정식을 얼마나 만족하는지만 말해 준다. 해와 얼마나 가까운지는 편차를 본다"),),
        scope="무차원 2차원 열전도, 정사각형, 네 변 온도 고정, x·y·t가 학습 범위(0~1, 0~T) 안",
        failure_conditions=("x, y, t가 학습 범위 밖일 때", "α나 경계 조건이 학습한 것과 다를 때", "학습이 수렴하지 않았을 때 (손실을 본다)"),
        fields=(field_dev,), validation=VALIDATION_COMPARED, evidence_level=EVIDENCE_NONE,
        presentation=("table:quantities", "field:pinn_minus_teacher"),
        inputs={"problem": PROBLEM, "alpha": p.alpha, "horizon": p.horizon, "config": cfg.to_dict()},
    )
