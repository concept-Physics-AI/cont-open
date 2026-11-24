"""열전도의 해석해(기준 문제). 풀이기와 PINN이 맞는지 보는 정답이다.

모두 열확산 방정식 T_t = alpha * (T_xx [+ T_yy]), 단위는 m, s, K.
"""
from __future__ import annotations

import math

import numpy as np


def sine_1d(x: np.ndarray, t: float, length: float, alpha: float, t_wall: float, amplitude: float) -> np.ndarray:
    """양 끝을 t_wall로 두고 초기 T = t_wall + amplitude * sin(pi x / L)."""
    return t_wall + amplitude * math.exp(-alpha * (math.pi / length) ** 2 * t) * np.sin(math.pi * x / length)


def step_1d(x: np.ndarray, t: float, length: float, alpha: float, t_wall: float, t_initial: float, terms: int = 400) -> np.ndarray:
    """양 끝을 t_wall로 두고 초기 T가 t_initial로 고른 판 (푸리에 급수의 홀수 항). t = 0은 초기값을 그대로 돌려준다."""
    x = np.asarray(x, dtype=float)
    if t <= 0.0:
        return np.full_like(x, t_initial)
    total = np.zeros_like(x)
    for n in range(1, 2 * terms, 2):
        total += 4.0 / (n * math.pi) * math.exp(-alpha * (n * math.pi / length) ** 2 * t) * np.sin(n * math.pi * x / length)
    return t_wall + (t_initial - t_wall) * total


def sine_2d(x: np.ndarray, y: np.ndarray, t: float, lx: float, ly: float, alpha: float, t_wall: float, amplitude: float) -> np.ndarray:
    """네 변을 t_wall로 두고 초기 T = t_wall + amplitude * sin(pi x / Lx) sin(pi y / Ly). x, y는 같은 모양의 격자 좌표."""
    decay = math.exp(-alpha * math.pi ** 2 * (1.0 / lx ** 2 + 1.0 / ly ** 2) * t)
    return t_wall + amplitude * decay * np.sin(math.pi * x / lx) * np.sin(math.pi * y / ly)


def convective_steady_1d(x: np.ndarray, length: float, k: float, h: float, t_left: float, t_inf: float) -> np.ndarray:
    """왼쪽 끝 T = t_left, 오른쪽 끝에서 -k T_x = h (T - t_inf)인 정상 상태. 선형 분포."""
    biot = h * length / k
    t_right = (t_left + biot * t_inf) / (1.0 + biot)
    return t_left + (t_right - t_left) * np.asarray(x, dtype=float) / length
