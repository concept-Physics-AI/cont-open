"""적층 1D 열응답 기준 (Y6, M07-A): 층별 물성과 계면 열저항이 있는 평판 적층의 비정상 열전도.

유한체적 + 크랭크-니콜슨(시작 두 걸음은 후진 오일러로 진동을 막는다). 단위는 SI.
왼쪽은 온도를 정하고, 오른쪽은 온도를 정하거나 대류(h, T_inf)를 준다. 초기 온도는 균일하다.
지원 범위는 config/physics/heat_stack.yaml과 docs/heat_stack.md에 있다. 범위 밖 입력은 `OutOfScope`로 멈춘다 (계산하지 않는다).
이 풀이기는 판정하지 않는다. 실측과 비교할 때도 편차만 보고한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import yaml

_CFG = Path(__file__).resolve().parents[4] / "config" / "physics" / "heat_stack.yaml"


class OutOfScope(ValueError):
    """지원 범위 밖의 입력. 계산하지 않는다."""


def scope() -> dict[str, Any]:
    return yaml.safe_load(_CFG.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Layer:
    name: str
    thickness: float                 # m
    conductivity: float              # W/(m K)
    density: float                   # kg/m^3
    specific_heat: float             # J/(kg K)
    interface_resistance: float = 0.0   # 이 층 왼쪽 계면의 접촉 열저항 (m^2 K / W). 첫 층에서는 0이어야 한다


@dataclass(frozen=True)
class Stack:
    layers: tuple[Layer, ...]
    t_left: float                    # K, 왼쪽 면 온도
    t_initial: float                 # K, 균일 초기 온도
    duration: float                  # s
    t_right: float | None = None     # K, 오른쪽 면 온도 (대류가 아닐 때)
    h_conv: float | None = None      # W/(m^2 K)
    t_inf: float | None = None       # K


def _in(name: str, value: float, key: str, b: dict[str, Any]) -> None:
    lo, hi = b[key]
    if not (isinstance(value, (int, float)) and math.isfinite(value)):
        raise OutOfScope(f"{name}이(가) 유한한 숫자가 아닙니다 ({value!r}). 계산하지 않습니다.")
    if not lo <= value <= hi:
        hint = " 온도는 켈빈(K)으로 넣어야 합니다 (섭씨가 아닙니다)." if key == "temperature_k" else (
            " 길이는 미터(m)입니다 (mm가 아닙니다)." if key == "thickness_m" else "")
        raise OutOfScope(f"{name}={value:g}이(가) 지원 범위 [{lo:g}, {hi:g}] 밖입니다.{hint} 계산하지 않습니다.")


def check_scope(s: Stack) -> None:
    cfg = scope(); b = cfg["bounds"]
    if not 1 <= len(s.layers) <= cfg["max_layers"]:
        raise OutOfScope(f"층 수 {len(s.layers)}이(가) 지원 범위 [1, {cfg['max_layers']}] 밖입니다. 계산하지 않습니다.")
    for i, ly in enumerate(s.layers):
        tag = f"{i + 1}번 층({ly.name}) "
        _in(tag + "두께", ly.thickness, "thickness_m", b)
        _in(tag + "열전도율", ly.conductivity, "conductivity_w_mk", b)
        _in(tag + "밀도", ly.density, "density_kg_m3", b)
        _in(tag + "비열", ly.specific_heat, "specific_heat_j_kgk", b)
        _in(tag + "계면 열저항", ly.interface_resistance, "interface_resistance_m2k_w", b)
    if s.layers[0].interface_resistance != 0.0:
        raise OutOfScope("첫 층 왼쪽은 온도를 정한 면이라 계면 열저항을 둘 수 없습니다. 계산하지 않습니다.")
    for name, v in (("왼쪽 면 온도", s.t_left), ("초기 온도", s.t_initial)):
        _in(name, v, "temperature_k", b)
    _in("지속 시간", s.duration, "duration_s", b)
    if s.t_right is None:
        if s.h_conv is None or s.t_inf is None:
            raise OutOfScope("오른쪽 경계는 온도(t_right) 또는 대류(h_conv, t_inf) 중 하나를 줘야 합니다. 계산하지 않습니다.")
        _in("대류 계수", s.h_conv, "h_conv_w_m2k", b); _in("주변 온도", s.t_inf, "temperature_k", b)
    else:
        if s.h_conv is not None or s.t_inf is not None:
            raise OutOfScope("오른쪽 경계는 온도와 대류를 함께 줄 수 없습니다. 계산하지 않습니다.")
        _in("오른쪽 면 온도", s.t_right, "temperature_k", b)


@dataclass(frozen=True)
class StackSolution:
    z: np.ndarray                    # 셀 중심 위치 (m)
    t: np.ndarray                    # 시각 (s), 길이 steps+1
    temperature: np.ndarray          # (steps+1, cells) K
    interface_z: tuple[float, ...]   # 층 경계 위치 (m)
    energy_residual: float           # 저장 에너지 변화와 경계 열유속 적분의 차이 / 저장 에너지 변화 크기 (J/m^2 기준 상대값)
    flux_left_w_m2: np.ndarray       # 각 걸음의 왼쪽 면 열유속 (W/m^2, 오른쪽으로 들어가는 방향이 +)

    def probe(self, z: float) -> np.ndarray:
        """위치 z에서 시간에 따른 온도 (셀 중심 사이를 선형 보간). 첫·마지막 셀 중심 밖이면 외삽하지 않고 멈춘다."""
        if not self.z[0] <= z <= self.z[-1]:
            raise OutOfScope(f"측정 위치 {z:g} m가 계산 격자 중심 범위 [{self.z[0]:g}, {self.z[-1]:g}] 밖입니다. 외삽하지 않습니다.")
        return np.array([np.interp(z, self.z, row) for row in self.temperature])


def _cells(layers: Sequence[Layer], total: int, min_per: int) -> list[int]:
    thick = np.array([ly.thickness for ly in layers])
    n = np.maximum(min_per, np.round(total * thick / thick.sum()).astype(int))
    return [int(v) for v in n]


def _thomas_factor(a: np.ndarray, b: np.ndarray, c: np.ndarray):
    n = len(b)
    cp, bp = np.zeros(n - 1), np.zeros(n)
    bp[0] = b[0]
    for i in range(1, n):
        w = a[i - 1] / bp[i - 1]
        bp[i] = b[i] - w * c[i - 1]
        cp[i - 1] = w
    return cp, bp


def _thomas_solve(f, c: np.ndarray, d: np.ndarray) -> np.ndarray:
    w, bp = f
    n = len(bp)
    y = d.copy()
    for i in range(1, n):
        y[i] -= w[i - 1] * y[i - 1]
    x = np.zeros(n)
    x[-1] = y[-1] / bp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = (y[i] - c[i] * x[i + 1]) / bp[i]
    return x


def solve_stack(s: Stack, cells: int | None = None, steps: int | None = None) -> StackSolution:
    check_scope(s)
    cfg = scope(); g = cfg["grid"]
    cells = g["cells_total_default"] if cells is None else cells
    steps = g["steps_default"] if steps is None else steps
    if not (len(s.layers) * g["cells_per_layer_min"] <= cells <= g["cells_total_max"]):
        raise OutOfScope(f"격자 수 {cells}이(가) 지원 범위 [{len(s.layers) * g['cells_per_layer_min']}, {g['cells_total_max']}] 밖입니다.")
    if not 4 <= steps <= g["steps_max"]:
        raise OutOfScope(f"시간 걸음 수 {steps}이(가) 지원 범위 [4, {g['steps_max']}] 밖입니다.")
    per = _cells(s.layers, cells, g["cells_per_layer_min"])
    dz, k, cap, edges, layer_of = [], [], [], [0.0], []
    for li, (ly, n) in enumerate(zip(s.layers, per)):
        for _ in range(n):
            dz.append(ly.thickness / n); k.append(ly.conductivity); cap.append(ly.density * ly.specific_heat * ly.thickness / n)
            layer_of.append(li)
        edges.append(edges[-1] + ly.thickness)
    dz, k, cap = np.array(dz), np.array(k), np.array(cap)
    n = len(dz)
    z = np.cumsum(dz) - dz / 2
    g_in = np.zeros(n - 1)                                   # 이웃 셀 중심 사이 전도도 (W/m^2K)
    for i in range(n - 1):
        r = dz[i] / (2 * k[i]) + dz[i + 1] / (2 * k[i + 1])
        if layer_of[i + 1] != layer_of[i]:
            r += s.layers[layer_of[i + 1]].interface_resistance
        g_in[i] = 1.0 / r
    g_left = 1.0 / (dz[0] / (2 * k[0]))
    last = s.layers[-1]
    r_right = dz[-1] / (2 * k[-1]) + (0.0 if s.t_right is not None else 1.0 / s.h_conv)
    g_right, t_right = 1.0 / r_right, (s.t_right if s.t_right is not None else s.t_inf)
    # 반이산: C dT/dt = -L T + b   (L은 대칭 삼중대각)
    diag = np.zeros(n); diag[0] += g_left; diag[-1] += g_right
    diag[:-1] += g_in; diag[1:] += g_in
    off = -g_in
    b = np.zeros(n); b[0] = g_left * s.t_left; b[-1] = g_right * t_right

    def apply_l(T: np.ndarray) -> np.ndarray:
        out = diag * T
        out[:-1] += off * T[1:]; out[1:] += off * T[:-1]
        return out

    dt = s.duration / steps
    T = np.full(n, s.t_initial)
    history = [T.copy()]; flux = []
    e_in = 0.0
    factors: dict[float, Any] = {}

    def step(T: np.ndarray, h: float, theta: float) -> np.ndarray:
        key = (round(h, 18), theta)
        if key not in factors:
            lo = theta * h * off / cap[1:]; up = theta * h * off / cap[:-1]
            main = 1.0 + theta * h * diag / cap
            factors[key] = (_thomas_factor(lo, main, up), up)
        f, up = factors[key]
        rhs = T + (1 - theta) * h * (-apply_l(T) + b) / cap + theta * h * b / cap
        return _thomas_solve(f, up, rhs)

    def left_flux(Tc: np.ndarray) -> float:
        return g_left * (s.t_left - Tc[0])

    def right_flux(Tc: np.ndarray) -> float:
        return g_right * (Tc[-1] - t_right)

    for i in range(steps):
        if i < 2:                                            # 시작: 후진 오일러 반걸음 두 번
            for _ in range(2):
                Tn = step(T, dt / 2, 1.0)
                e_in += dt / 2 * (left_flux(Tn) - right_flux(Tn))
                T = Tn
        else:
            Tn = step(T, dt, 0.5)
            e_in += dt * 0.5 * ((left_flux(T) - right_flux(T)) + (left_flux(Tn) - right_flux(Tn)))
            T = Tn
        flux.append(left_flux(T)); history.append(T.copy())
    stored = float((cap * (T - s.t_initial)).sum())
    resid = abs(stored - e_in) / max(abs(stored), abs(e_in), 1e-300)
    return StackSolution(z, np.linspace(0.0, s.duration, steps + 1), np.array(history), tuple(edges), float(resid), np.array(flux))


def steady_state(s: Stack) -> dict[str, float]:
    """직렬 열저항 해석해: 오른쪽이 대류일 때 정상 열유속과 각 계면 온도 (층 경계 왼쪽 면 기준)."""
    check_scope(s)
    r_layers = [ly.thickness / ly.conductivity for ly in s.layers]
    r_if = [ly.interface_resistance for ly in s.layers]
    r_end = 0.0 if s.t_right is not None else 1.0 / s.h_conv
    t_end = s.t_right if s.t_right is not None else s.t_inf
    q = (s.t_left - t_end) / (sum(r_layers) + sum(r_if) + r_end)
    temps, t = {}, s.t_left
    for i, ly in enumerate(s.layers):
        t -= q * r_if[i]; temps[f"before_{ly.name}"] = t
        t -= q * r_layers[i]
    return {"flux_w_m2": q, **temps, "right_face_k": t}


def compare_response(sim_t: np.ndarray, sim_temp: np.ndarray, meas_t: Sequence[float], meas_temp: Sequence[float]) -> dict[str, Any]:
    """실측 응답과 계산 응답의 편차를 보고한다 (판정하지 않는다). 계산한 시간 범위 밖의 실측 점은 쓰지 않고 센다."""
    b = scope()["bounds"]["temperature_k"]
    mt, mv = np.asarray(meas_t, float), np.asarray(meas_temp, float)
    if mt.shape != mv.shape or mt.size == 0:
        raise OutOfScope("실측 시간과 온도의 길이가 다르거나 비어 있습니다. 비교하지 않습니다.")
    if not np.all(np.isfinite(mt)) or not np.all(np.isfinite(mv)):
        raise OutOfScope("실측에 유한하지 않은 값이 있습니다. 비교하지 않습니다.")
    if mv.min() < b[0] or mv.max() > b[1]:
        raise OutOfScope(f"실측 온도 [{mv.min():g}, {mv.max():g}]이(가) 켈빈 범위 [{b[0]:g}, {b[1]:g}] 밖입니다. 섭씨를 켈빈으로 바꿨는지 확인하세요. 비교하지 않습니다.")
    inside = (mt >= sim_t[0]) & (mt <= sim_t[-1])
    if not inside.any():
        raise OutOfScope("실측 시각이 모두 계산한 시간 범위 밖입니다. 비교하지 않습니다.")
    d = np.interp(mt[inside], sim_t, sim_temp) - mv[inside]
    return {"points": int(inside.sum()), "points_outside_time_range": int((~inside).sum()), "rmse_k": float(np.sqrt((d ** 2).mean())),
            "max_abs_k": float(np.abs(d).max()), "bias_k": float(d.mean()), "judged": False}


def convergence(s: Stack, probe_z: float, cells: int | None = None, steps: int | None = None) -> dict[str, float]:
    """격자와 시간 걸음을 함께 2배, 4배로 줄여 같은 위치의 마지막 온도 차이로 관측 차수를 구한다."""
    cfg = scope()["grid"]
    c = cfg["cells_total_default"] if cells is None else cells
    n = cfg["steps_default"] if steps is None else steps
    v = [solve_stack(s, c * m, n * m).probe(probe_z)[-1] for m in (1, 2, 4)]
    e1, e2 = abs(v[0] - v[1]), abs(v[1] - v[2])
    return {"diff_coarse_mid_k": float(e1), "diff_mid_fine_k": float(e2), "observed_order": float(math.log2(e1 / e2)) if e2 > 0 and e1 > 0 else float("nan")}
