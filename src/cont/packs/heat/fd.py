"""열전도 유한차분 풀이기: 열 영역의 물리 선생.

공간은 중심차분, 시간은 크랭크-니콜슨(2차)이다. 조밀 행렬을 한 번 만들고 역행렬을 시간 단계마다 곱한다.
작은 격자(1차원 수백 칸, 2차원 수천 점)를 위한 것이며 큰 문제용이 아니다. 단위는 m, s, K.

1차원: 왼쪽 끝은 온도를 정하고, 오른쪽 끝은 온도를 정하거나 대류(-k T_x = h (T - T_inf))를 준다.
2차원: 직사각형 네 변의 온도가 모두 같다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class Slab1D:
    length: float                       # m
    diffusivity: float                  # alpha, m^2/s
    t_left: float                       # K, 왼쪽 끝 온도
    initial: Callable[[np.ndarray], np.ndarray]   # x(m) -> T(K)
    duration: float                     # s
    t_right: float | None = None        # K. None이면 오른쪽 끝은 대류 (conductivity, h_conv, t_inf 필요)
    conductivity: float | None = None   # k, W/(m K)  (대류일 때만)
    h_conv: float | None = None         # W/(m^2 K)
    t_inf: float | None = None          # K

    def __post_init__(self) -> None:
        if min(self.length, self.diffusivity, self.duration) <= 0:
            raise ValueError("length, diffusivity and duration must be positive")
        if self.t_right is None and None in (self.conductivity, self.h_conv, self.t_inf):
            raise ValueError("a convective right end needs conductivity, h_conv and t_inf")
        if self.t_right is not None and any(v is not None for v in (self.h_conv, self.t_inf)):
            raise ValueError("give either t_right (fixed temperature) or h_conv and t_inf (convection), not both")


@dataclass(frozen=True)
class Solution1D:
    x: np.ndarray            # 절점 좌표 (m), 양 끝 포함
    times: np.ndarray        # 저장한 시각 (s), 0부터 duration까지
    temperature: np.ndarray  # (len(times), len(x)) K
    nx: int
    steps: int


def solve_1d(p: Slab1D, nx: int = 101, steps: int = 200) -> Solution1D:
    """nx개 절점(양 끝 포함), steps개 시간 단계. 모든 단계의 온도를 돌려준다."""
    if nx < 5 or steps < 1:
        raise ValueError("nx must be at least 5 and steps at least 1")
    h = p.length / (nx - 1)
    dt = p.duration / steps
    x = np.linspace(0.0, p.length, nx)
    n = nx - 1 if p.t_right is None else nx - 2        # 미지수: 왼쪽 끝은 고정, 오른쪽 끝은 대류일 때 미지수
    a = p.diffusivity / h ** 2
    # 미지수는 절점 1 .. 1+n-1. 내부 절점은 중심차분
    lap = np.zeros((n, n))
    src = np.zeros(n)
    for i in range(n):
        lap[i, i] = -2.0 * a
        if i > 0:
            lap[i, i - 1] = a
        if i < n - 1:
            lap[i, i + 1] = a
    src[0] = a * p.t_left
    if p.t_right is not None:
        src[-1] += a * p.t_right
    else:
        # 오른쪽 끝 절점(마지막 미지수)의 가상 절점: T_{N+1} = T_{N-1} - 2 h (h_conv/k)(T_N - T_inf)
        beta = 2.0 * h * p.h_conv / p.conductivity
        lap[-1, -1] += -a * beta
        lap[-1, -2] = 2.0 * a
        src[-1] = a * beta * p.t_inf
    eye = np.eye(n)
    lhs = np.linalg.inv(eye - 0.5 * dt * lap)
    rhs = eye + 0.5 * dt * lap
    u = p.initial(x)[1:1 + n].astype(float)
    out = np.empty((steps + 1, nx))

    def full(vec: np.ndarray) -> np.ndarray:
        row = np.empty(nx)
        row[0] = p.t_left
        row[1:1 + n] = vec
        if p.t_right is not None:
            row[-1] = p.t_right
        return row

    out[0] = full(u)
    for k in range(steps):
        u = lhs @ (rhs @ u + dt * src)
        out[k + 1] = full(u)
    return Solution1D(x, np.linspace(0.0, p.duration, steps + 1), out, nx, steps)


@dataclass(frozen=True)
class Plate2D:
    lx: float                  # m
    ly: float                  # m
    diffusivity: float         # m^2/s
    t_wall: float              # K, 네 변의 온도
    initial: Callable[[np.ndarray, np.ndarray], np.ndarray]   # (x, y) 격자 -> T(K)
    duration: float            # s

    def __post_init__(self) -> None:
        if min(self.lx, self.ly, self.diffusivity, self.duration) <= 0:
            raise ValueError("lx, ly, diffusivity and duration must be positive")


@dataclass(frozen=True)
class Solution2D:
    x: np.ndarray              # (nx,)
    y: np.ndarray              # (ny,)
    times: np.ndarray
    temperature: np.ndarray    # (len(times), ny, nx) K
    nx: int
    ny: int
    steps: int


def _lap_1d(n_nodes: int, h: float, alpha: float) -> np.ndarray:
    """양 끝이 고정된 1차원 내부 절점의 alpha * 2차 중심차분 행렬."""
    n = n_nodes - 2
    m = np.zeros((n, n))
    a = alpha / h ** 2
    for i in range(n):
        m[i, i] = -2.0 * a
        if i > 0:
            m[i, i - 1] = a
        if i < n - 1:
            m[i, i + 1] = a
    return m


def solve_2d(p: Plate2D, nx: int = 31, ny: int = 31, steps: int = 100) -> Solution2D:
    """nx x ny 절점(변 포함), steps개 시간 단계. 모든 단계의 온도를 돌려준다."""
    if min(nx, ny) < 5 or steps < 1:
        raise ValueError("nx and ny must be at least 5 and steps at least 1")
    hx, hy = p.lx / (nx - 1), p.ly / (ny - 1)
    dt = p.duration / steps
    x = np.linspace(0.0, p.lx, nx)
    y = np.linspace(0.0, p.ly, ny)
    lx_m = _lap_1d(nx, hx, p.diffusivity)
    ly_m = _lap_1d(ny, hy, p.diffusivity)
    mx, my = lx_m.shape[0], ly_m.shape[0]
    # 미지수는 내부 절점을 행(y) 우선으로 펼친 벡터. 네 변이 모두 t_wall이라 원천 항은 변 쪽 절점에만 있다.
    lap = np.kron(np.eye(my), lx_m) + np.kron(ly_m, np.eye(mx))
    src = np.zeros((my, mx))
    ax, ay = p.diffusivity / hx ** 2, p.diffusivity / hy ** 2
    src[:, 0] += ax * p.t_wall
    src[:, -1] += ax * p.t_wall
    src[0, :] += ay * p.t_wall
    src[-1, :] += ay * p.t_wall
    src = src.ravel()
    eye = np.eye(mx * my)
    lhs = np.linalg.inv(eye - 0.5 * dt * lap)
    rhs = eye + 0.5 * dt * lap
    gx, gy = np.meshgrid(x, y)
    t0 = p.initial(gx, gy).astype(float)
    u = t0[1:-1, 1:-1].ravel()
    out = np.empty((steps + 1, ny, nx))

    def full(vec: np.ndarray) -> np.ndarray:
        field = np.full((ny, nx), p.t_wall)
        field[1:-1, 1:-1] = vec.reshape(my, mx)
        return field

    out[0] = full(u)
    for k in range(steps):
        u = lhs @ (rhs @ u + dt * src)
        out[k + 1] = full(u)
    return Solution2D(x, y, np.linspace(0.0, p.duration, steps + 1), out, nx, ny, steps)
