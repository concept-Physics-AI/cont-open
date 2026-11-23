"""축대칭 풀이기: 닫힌 해가 있는 두 문제로 확인한다."""
import math

import numpy as np
import pytest

from cont.fem import axisym


def test_uniform_compression_of_a_hollow_cylinder_matches_the_closed_form():
    r, z = np.linspace(5.0, 20.0, 7), np.linspace(0.0, 30.0, 9)
    p, e, nu = 100.0, 200000.0, 0.3
    edge = axisym.edge_pressure(r, p, 5.0, 20.0)
    assert edge.sum() == pytest.approx(p * (20.0**2 - 5.0**2) / 2)            # 1 rad당 힘 = F / (2 pi)
    f_z = np.zeros((9, 7))
    f_z[0] += edge
    f_z[-1] -= edge
    sol = axisym.solve(r, z, np.full((8, 6), e), nu, np.zeros((9, 7)), f_z, fixed_z=((4, 0),))
    assert np.allclose(sol.stress[..., 1], -p, rtol=1e-8) and np.allclose(sol.stress[..., [0, 2, 3]], 0.0, atol=1e-6)
    assert np.allclose(sol.u_z[0] - sol.u_z[-1], p * 30.0 / e, rtol=1e-8)       # 줄어든 길이 = p L / E
    assert np.allclose(sol.von_mises(), p, rtol=1e-8)


def test_thick_cylinder_under_internal_pressure_matches_lame():
    r_i, r_o, p = 10.0, 30.0, 50.0
    r, z = np.linspace(r_i, r_o, 41), np.linspace(0.0, 10.0, 5)
    f_r = np.zeros((5, 41))
    dz = np.diff(z)
    f_r[:-1, 0] += p * r_i * dz / 2
    f_r[1:, 0] += p * r_i * dz / 2
    sol = axisym.solve(r, z, np.full((4, 40), 200000.0), 0.3, f_r, np.zeros((5, 41)), fixed_z=((0, 0),))
    k = p * r_i**2 / (r_o**2 - r_i**2)
    hoop = k * (1 + r_o**2 / sol.r_mid**2)
    radial = k * (1 - r_o**2 / sol.r_mid**2)
    assert np.allclose(sol.stress[2, :, 2], hoop, rtol=5e-3) and np.allclose(sol.stress[2, :, 0], radial, rtol=5e-3, atol=0.2)
    assert np.abs(sol.stress[..., 1]).max() < 0.01 * p                          # 끝이 자유로우면 축 방향 응력은 없다 (압력의 1% 안)


def test_bad_input_is_refused():
    r, z = np.array([1.0, 2.0]), np.array([0.0, 1.0])
    zero = np.zeros((2, 2))
    with pytest.raises(ValueError):
        axisym.solve(r[::-1], z, np.ones((1, 1)), 0.3, zero, zero, ((0, 0),))
    with pytest.raises(ValueError):
        axisym.solve(r, z, np.ones((1, 1)), 0.3, zero, zero, ())
    with pytest.raises(ValueError):
        axisym.solve(r, z, np.ones((2, 2)), 0.3, zero, zero, ((0, 0),))
    assert axisym.elasticity(1.0, 0.0)[3, 3] == pytest.approx(0.5) and math.isclose(axisym.elasticity(2.0, 0.0)[0, 0], 2.0)
