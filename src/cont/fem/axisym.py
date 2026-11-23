"""축대칭 선형 탄성 유한요소 풀이기 (C3 물리 계산).

축(z)을 중심으로 돌린 모양을 반지름-높이(r, z) 단면의 직사각형 격자로 푼다. 요소는 네 절점 사각형이다.
이 모듈은 격자, 재료, 절점 힘, 고정 조건을 받아 변위와 응력을 낼 뿐이고, 무엇을 푸는지는 모른다 (그것은 팩이 정한다).
힘과 강성은 모두 "각도 1 rad당"으로 다룬다. 전체 힘 F를 주려면 절점 힘의 합이 F / (2 pi)가 되게 넣는다.
단위는 부르는 쪽이 맞춘다 (체결 팩: mm, N, MPa).

담지 않은 것: 접촉(떨어짐·미끄럼), 소성, 큰 변형, 축대칭이 아닌 하중.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_GAUSS = 1.0 / np.sqrt(3.0)
_CORNERS = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))     # 요소 안의 절점 순서 (xi, eta)


@dataclass(frozen=True)
class Solution:
    r: np.ndarray                 # 절점 반지름 (nr,)
    z: np.ndarray                 # 절점 높이 (nz,)
    u_r: np.ndarray               # 절점 반지름 방향 변위 (nz, nr)
    u_z: np.ndarray               # 절점 축 방향 변위 (nz, nr)
    stress: np.ndarray            # 요소 중심 응력 (nz-1, nr-1, 4): sigma_r, sigma_z, sigma_theta, tau_rz

    @property
    def r_mid(self) -> np.ndarray:
        return (self.r[:-1] + self.r[1:]) / 2

    @property
    def z_mid(self) -> np.ndarray:
        return (self.z[:-1] + self.z[1:]) / 2

    def von_mises(self) -> np.ndarray:
        s_r, s_z, s_t, t = (self.stress[..., k] for k in range(4))
        return np.sqrt(((s_r - s_z) ** 2 + (s_z - s_t) ** 2 + (s_t - s_r) ** 2) / 2 + 3 * t**2)


def elasticity(youngs: float, poisson: float) -> np.ndarray:
    """등방 탄성 행렬. 변형률 순서는 (e_r, e_z, e_theta, gamma_rz)."""
    c = youngs / ((1 + poisson) * (1 - 2 * poisson))
    d = np.full((4, 4), 0.0)
    d[:3, :3] = c * poisson
    d[0, 0] = d[1, 1] = d[2, 2] = c * (1 - poisson)
    d[3, 3] = c * (1 - 2 * poisson) / 2
    return d


def _b_matrix(xi: float, eta: float, r_c: float, a: float, b: float) -> tuple[np.ndarray, float]:
    """변형률-변위 행렬 (4 x 8)과 그 점의 반지름. a, b는 요소의 반 폭과 반 높이."""
    bm = np.zeros((4, 8))
    r = r_c + a * xi
    for k, (xk, ek) in enumerate(_CORNERS):
        n = (1 + xi * xk) * (1 + eta * ek) / 4
        dn_dr = xk * (1 + eta * ek) / (4 * a)
        dn_dz = ek * (1 + xi * xk) / (4 * b)
        bm[0, 2 * k] = dn_dr
        bm[1, 2 * k + 1] = dn_dz
        bm[2, 2 * k] = n / r
        bm[3, 2 * k] = dn_dz
        bm[3, 2 * k + 1] = dn_dr
    return bm, r


def solve(r: np.ndarray, z: np.ndarray, youngs: np.ndarray, poisson: float, force_r: np.ndarray, force_z: np.ndarray,
          fixed_z: tuple[tuple[int, int], ...]) -> Solution:
    """r, z: 절점 좌표 (오름차순). youngs: 요소마다의 탄성계수 (nz-1, nr-1). force_*: 절점 힘 (nz, nr), 1 rad당.

    fixed_z: 축 방향 변위를 0으로 잡는 절점 (j, i)들. 축대칭에서는 축 방향 강체 이동 하나만 남으므로 한 점이면 된다.
    """
    r = np.asarray(r, dtype=float)
    z = np.asarray(z, dtype=float)
    nr, nz = len(r), len(z)
    if nr < 2 or nz < 2 or np.any(np.diff(r) <= 0) or np.any(np.diff(z) <= 0) or r[0] < 0:
        raise ValueError("r and z must be increasing with at least two nodes each, and r must not be negative")
    youngs = np.asarray(youngs, dtype=float)
    if youngs.shape != (nz - 1, nr - 1) or force_r.shape != (nz, nr) or force_z.shape != (nz, nr):
        raise ValueError("youngs must be (nz-1, nr-1) and forces (nz, nr)")
    if not fixed_z:
        raise ValueError("fix the axial displacement of at least one node")

    def nodes(j: int, i: int) -> tuple[int, int, int, int]:
        return (j * nr + i, j * nr + i + 1, (j + 1) * nr + i + 1, (j + 1) * nr + i)

    ndof = 2 * nr * nz
    k = np.zeros((ndof, ndof))
    for j in range(nz - 1):
        b = (z[j + 1] - z[j]) / 2
        for i in range(nr - 1):
            a = (r[i + 1] - r[i]) / 2
            r_c = (r[i] + r[i + 1]) / 2
            d = elasticity(float(youngs[j, i]), poisson)
            ke = np.zeros((8, 8))
            for xi in (-_GAUSS, _GAUSS):
                for eta in (-_GAUSS, _GAUSS):
                    bm, rr = _b_matrix(xi, eta, r_c, a, b)
                    ke += bm.T @ d @ bm * (rr * a * b)
            dofs = np.array([[2 * n, 2 * n + 1] for n in nodes(j, i)]).reshape(-1)
            k[np.ix_(dofs, dofs)] += ke
    f = np.zeros(ndof)
    f[0::2] = force_r.reshape(-1)
    f[1::2] = force_z.reshape(-1)
    fixed = sorted({2 * (j * nr + i) + 1 for j, i in fixed_z})
    free = np.setdiff1d(np.arange(ndof), fixed)
    u = np.zeros(ndof)
    u[free] = np.linalg.solve(k[np.ix_(free, free)], f[free])
    stress = np.zeros((nz - 1, nr - 1, 4))
    for j in range(nz - 1):
        b = (z[j + 1] - z[j]) / 2
        for i in range(nr - 1):
            a = (r[i + 1] - r[i]) / 2
            bm, _ = _b_matrix(0.0, 0.0, (r[i] + r[i + 1]) / 2, a, b)
            dofs = np.array([[2 * n, 2 * n + 1] for n in nodes(j, i)]).reshape(-1)
            stress[j, i] = elasticity(float(youngs[j, i]), poisson) @ bm @ u[dofs]
    return Solution(r, z, u[0::2].reshape(nz, nr), u[1::2].reshape(nz, nr), stress)


def edge_pressure(r: np.ndarray, pressure: float, r_from: float, r_to: float) -> np.ndarray:
    """z가 일정한 면에서 r_from ~ r_to에 고른 압력이 걸릴 때의 절점 힘 크기 (nr,), 1 rad당. 두 끝은 격자의 절점이어야 한다."""
    f = np.zeros(len(r))
    for i in range(len(r) - 1):
        r1, r2 = r[i], r[i + 1]
        if r1 >= r_from - 1e-9 and r2 <= r_to + 1e-9:
            f[i] += pressure * (r2 - r1) * (2 * r1 + r2) / 6
            f[i + 1] += pressure * (r2 - r1) * (r1 + 2 * r2) / 6
    return f
