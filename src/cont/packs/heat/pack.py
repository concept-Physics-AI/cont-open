"""열 물리 팩: 비정상 열전도 기준 문제 → 유한차분 풀이 → 해석해와 편차 → PhysicsAnswer.

기준 문제는 해석해가 있는 것만 둔다 (sine_1d, step_1d, sine_2d). 해석해와의 편차는 보고만 하고 판정하지 않는다.
증거 수준은 E1(기준 계산과 불변식)이다. E2는 판정 기준을 정할 때까지 붙이지 않는다.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from cont.answer import (EVIDENCE_REFERENCE, STATUS_INPUT, STATUS_SIMULATED, VALIDATION_COMPARED, Confidence, Field,
                         PhysicsAnswer, Quantity, Residual)
from cont.packs.heat import analytic, fd

CASES = ("sine_1d", "step_1d", "sine_2d")
SCOPE = "상수 물성의 비정상 열전도. 1차원 판(양 끝 온도 고정)과 2차원 직사각형(네 변 온도 고정). 내부 열원과 상변화 없음"
FAILS = ("물성이 온도에 따라 크게 변할 때", "내부 발열이나 상변화가 있을 때", "경계가 대류나 복사일 때 (이 기준 문제에는 없음)",
         "3차원 효과가 큰 형상")
DEFAULTS = {"length": 0.1, "ly": 0.05, "diffusivity": 1.0e-4, "t_wall": 300.0, "amplitude": 50.0, "t_initial": 400.0,
            "duration": 20.0, "nx": 81, "steps": 160}


def _p(inputs: Mapping[str, Any]) -> dict[str, Any]:
    p = {**DEFAULTS, **{k: v for k, v in inputs.items() if k != "case"}}
    case = inputs.get("case", "sine_1d")
    if case not in CASES:
        raise ValueError(f"unknown heat case '{case}' (available: {list(CASES)})")
    p["case"] = case
    if p["case"] == "sine_2d" and "nx" not in inputs:
        p["nx"], p["steps"] = 31, 60
    if p["case"] == "sine_2d" and "duration" not in inputs:
        p["duration"] = 2.0
    return p


def _run(p: dict[str, Any], nx: int, steps: int):
    """(해석해와의 RMS 편차, 최대 편차, 풀이 결과, 같은 시각의 해석해)."""
    a, tw = p["diffusivity"], p["t_wall"]
    if p["case"] == "sine_2d":
        lx, ly, amp = p["length"], p["ly"], p["amplitude"]
        sol = fd.solve_2d(fd.Plate2D(lx, ly, a, tw, lambda X, Y: analytic.sine_2d(X, Y, 0.0, lx, ly, a, tw, amp), p["duration"]),
                          nx, nx, steps)
        gx, gy = np.meshgrid(sol.x, sol.y)
        ref = analytic.sine_2d(gx, gy, p["duration"], lx, ly, a, tw, amp)
    else:
        length = p["length"]
        if p["case"] == "sine_1d":
            amp = p["amplitude"]
            init = lambda x: analytic.sine_1d(x, 0.0, length, a, tw, amp)
            exact = lambda x, t: analytic.sine_1d(x, t, length, a, tw, amp)
        else:
            t0 = p["t_initial"]
            init = lambda x: np.where((x > 0) & (x < length), t0, tw)
            exact = lambda x, t: analytic.step_1d(x, t, length, a, tw, t0)
        sol = fd.solve_1d(fd.Slab1D(length, a, tw, init, p["duration"], t_right=tw), nx, steps)
        ref = exact(sol.x, p["duration"])
    err = sol.temperature[-1] - ref
    return float(np.sqrt(np.mean(err ** 2))), float(np.max(np.abs(err))), sol, ref


class HeatPack:
    name = "heat"

    def solve(self, inputs: Mapping[str, Any], question: str = "") -> PhysicsAnswer:
        """inputs = {"case": "sine_1d" | "step_1d" | "sine_2d", length, diffusivity, t_wall, amplitude 또는 t_initial, duration, nx, steps}."""
        return answer(_p(inputs), question)


def answer(p: dict[str, Any], question: str = "") -> PhysicsAnswer:
    nx, steps = int(p["nx"]), int(p["steps"])
    rms, mx, sol, ref = _run(p, nx, steps)
    rms_c, _, _, _ = _run(p, (nx - 1) // 2 + 1, max(1, steps // 2))   # 격자를 반으로 줄인 풀이
    order = math.log2(rms_c / rms) if rms > 0 and rms_c > 0 else None
    final = sol.temperature[-1]
    two_d = p["case"] == "sine_2d"
    peak = float(final.max())
    quantities = [
        Quantity("diffusivity", "열확산계수 α", p["diffusivity"], "m^2/s", None, None, STATUS_INPUT),
        Quantity("t_wall", "경계 온도", p["t_wall"], "K", None, None, STATUS_INPUT),
        Quantity("duration", "계산 시간", p["duration"], "s", None, None, STATUS_INPUT),
        Quantity("peak_temperature", "마지막 시각의 최고 온도", peak, "K"),
        Quantity("reference_peak_temperature", "같은 시각 해석해의 최고 온도", float(ref.max()), "K"),
        Quantity("deviation_rms", "해석해와의 편차 (RMS)", rms, "K", None, "그 편차가 허용되는지는 판정하지 않는다"),
        Quantity("deviation_max", "해석해와의 편차 (최대)", mx, "K"),
        Quantity("grid_order", "격자 수렴 차수 (격자를 반으로 줄인 풀이와 비교)", order, "-",
                 "2에 가까우면 2차 정확도 방법과 맞는다" if order is not None else None),
    ]
    fields: tuple[Field, ...] = ()
    if two_d:
        fields = (Field("temperature", "마지막 시각의 온도", "K", ("x", "y"), "m", tuple(float(v) for v in sol.x),
                        tuple(float(v) for v in sol.y), tuple(tuple(float(v) for v in row) for row in final)),)
    basis = (
        "열확산 방정식 T_t = α (T_xx" + (" + T_yy" if two_d else "") + "), 공간은 중심차분, 시간은 크랭크-니콜슨(2차)",
        f"기준 문제 {p['case']}: 해석해와 비교한다 (정답을 알고 만든 문제)",
        f"격자 {nx}" + (f" x {nx}" if two_d else "") + f" 절점, 시간 {steps} 단계",
        "가정: 물성은 상수, 내부 열원 없음",
        "판정 없음: 해석해와의 편차는 값만 보고한다. 일치 기준은 정해지지 않았다",
    )
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=tuple(quantities), method="유한차분 (크랭크-니콜슨)", basis=basis,
        confidence=Confidence("medium", "해석해와 대조하고 격자 수렴을 확인한 기준 계산이다. 실측과는 대조하지 않았다"),
        source="사람이 넣은 기준 문제 조건 (해석해가 있는 합성 문제)", uncertainty="",
        residuals=(Residual("analytic_deviation", "해석해와의 RMS 편차", rms, "K", "기준 문제에서만 잰다. 실제 부품의 오차가 아니다"),),
        scope=SCOPE, failure_conditions=FAILS, fields=fields,
        validation=VALIDATION_COMPARED, evidence_level=EVIDENCE_REFERENCE,
        presentation=("table:quantities",) + (("field:temperature",) if two_d else ()),
        inputs={k: v for k, v in p.items()},
    )
