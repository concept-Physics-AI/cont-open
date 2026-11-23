"""체결된 판 안의 응력 분포: 축대칭 수치해석 (C3) → PhysicsAnswer (물리장 포함).

VDI 2230 식은 판이 눌리는 정도를 원뿔 모형의 값 하나(컴플라이언스)로 낸다. 여기서는 같은 판을 유한요소로 풀어
판 안에서 압축이 어떻게 퍼지는지를 분포로 낸다. 두 방법의 판 컴플라이언스 차이도 함께 보고한다 (판정은 하지 않는다).

모형: 구멍 뚫린 원통(안지름 = 구멍, 바깥지름 = D_A, 높이 = 체결 길이)에 머리와 너트의 좌면 넓이만큼 고른 압력을 위아래에서 건다.
가정: 볼트는 풀지 않고 좌면 압력으로 바꾼다 / 좌면 압력은 고르다 / 두 판은 붙어 있다 (떨어짐·미끄럼 없음) / 선형 탄성.
"""
from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np
import yaml

from cont.answer import STATUS_INPUT, STATUS_SIMULATED, Confidence, Field, PhysicsAnswer, Quantity, Residual
from cont.fem import axisym
from cont.packs.fastening import vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.tolerance import CONFIG_DIR

SCOPE = "동심 체결, 관통 볼트, 판 2장, 와셔 없음. 조립 직후의 체결력만 건 상태 (운전 하중 없음)"
FAILS = ("판 사이가 벌어지는 곳이 있을 때 (붙어 있다고 가정했으므로 그 바깥의 값은 맞지 않는다)", "판이 항복할 때", "편심 하중", "좌면 압력이 고르지 않을 때 (머리가 얇거나 좌면이 기울 때)")


def settings() -> dict[str, float]:
    with open(CONFIG_DIR / "fastening" / "default.yaml", encoding="utf-8") as f:
        s = (yaml.safe_load(f) or {})["field"]
    return {"poisson_ratio": float(s["poisson_ratio"]), "radial_cells_under_head": int(s["radial_cells_under_head"]),
            "radial_cells_outside": int(s["radial_cells_outside"]), "axial_cells": int(s["axial_cells"])}


def _grid(joint: BoltedJoint, s: dict[str, float]) -> tuple[np.ndarray, np.ndarray, int, float]:
    """절점 좌표 (r, z), 두 판이 만나는 높이의 절점 번호, 압력이 걸리는 바깥 반지름. z = 0이 너트 쪽 바닥이다."""
    r_h, r_o = joint.hole / 2, joint.outer_diameter / 2
    r_w = min(joint.bearing_diameter / 2, r_o)
    r = np.linspace(r_h, r_w, int(s["radial_cells_under_head"]) + 1)
    if r_o > r_w:
        r = np.concatenate([r, np.linspace(r_w, r_o, int(s["radial_cells_outside"]) + 1)[1:]])
    t_nut, t_head = joint.plate_nut.thickness, joint.plate_head.thickness
    n_nut = max(2, round(int(s["axial_cells"]) * t_nut / (t_nut + t_head)))
    n_head = max(2, int(s["axial_cells"]) - n_nut)
    z = np.concatenate([np.linspace(0.0, t_nut, n_nut + 1), np.linspace(t_nut, t_nut + t_head, n_head + 1)[1:]])
    return r, z, n_nut, r_w


def solve(joint: BoltedJoint, preload: float) -> tuple[axisym.Solution, dict[str, float]]:
    """체결력 하나에 대한 풀이와 거기서 뽑은 값들."""
    s = settings()
    r, z, j_if, r_w = _grid(joint, s)
    nr, nz = len(r), len(z)
    youngs = np.empty((nz - 1, nr - 1))
    youngs[:j_if] = joint.plate_nut.youngs_modulus
    youngs[j_if:] = joint.plate_head.youngs_modulus
    area = math.pi * (r_w**2 - r[0] ** 2)
    edge = axisym.edge_pressure(r, preload / area, r[0], r_w)
    f_z = np.zeros((nz, nr))
    f_z[0] += edge                                           # 너트 좌면: 위로 민다
    f_z[-1] -= edge                                          # 머리 좌면: 아래로 민다
    sol = axisym.solve(r, z, youngs, s["poisson_ratio"], np.zeros((nz, nr)), f_z, fixed_z=((j_if, nr - 1),))
    total = edge.sum()
    shortening = float((edge * sol.u_z[0]).sum() / total - (edge * sol.u_z[-1]).sum() / total)   # 좌면 사이가 줄어든 길이 (힘으로 가중)
    widths = np.diff(r)
    level_force = 2 * math.pi * (sol.stress[..., 1] * sol.r_mid * widths).sum(axis=1)             # 높이마다 단면이 받는 축력 (압축 -)
    compression = -sol.stress[..., 1]
    at_if = (compression[j_if - 1] + compression[j_if]) / 2                                      # 판 사이 면의 압축 응력
    open_from = next((float(sol.r[i]) for i in range(nr - 1) if at_if[i] <= 0), None)             # 여기부터는 눌리지 않는다
    return sol, {"shortening": shortening, "resilience": shortening / preload, "balance": float(np.abs(level_force + preload).max()),
                 "peak": float(compression.max()), "interface_peak": float(at_if.max()), "interface_mean": float((at_if * sol.r_mid * widths).sum() / (sol.r_mid * widths).sum()),
                 "pressed_radius": open_from if open_from is not None else float(sol.r[-1]), "pressed_everywhere": open_from is None,
                 "interface_index": float(j_if), "load_radius": float(r_w)}


def stress_field(joint: BoltedJoint, load: LoadCase, question: str = "") -> PhysicsAnswer:
    """판 안의 압축 응력 분포와, 수치해석과 VDI 2230 식의 판 컴플라이언스 대조."""
    r = vdi2230.calculate(joint, load)
    sol, v = solve(joint, r.preload)
    comp = -sol.stress[..., 1]
    mises = sol.von_mises()

    def grid(a: np.ndarray) -> tuple[tuple[float, ...], ...]:
        return tuple(tuple(round(float(x), 3) for x in row) for row in a)

    x = tuple(round(float(c), 4) for c in sol.r_mid)
    y = tuple(round(float(c), 4) for c in sol.z_mid)
    axes = ("반지름 r", "높이 z (0 = 너트 쪽 바닥)")
    fields = (
        Field("plate_axial_compression", "판의 축 방향 압축 응력", "MPa", axes, "mm", x, y, grid(comp),
              note="양수가 압축이다. 음수(당겨짐)가 나오는 곳은 실제로는 판이 벌어지는 곳이다"),
        Field("plate_von_mises", "판의 등가응력 (von Mises)", "MPa", axes, "mm", x, y, grid(mises)),
    )
    deviation = (v["resilience"] - r.delta_p) / r.delta_p * 100.0
    cone_radius = min(joint.bearing_diameter / 2 + vdi2230.cone_angle_tan(joint.clamp_length, joint.bearing_diameter, joint.outer_diameter)
                      * joint.clamp_length / 2, joint.outer_diameter / 2)
    quantities = (
        Quantity("preload", "건 체결력 F_M (대표 마찰)", r.preload, "N", status=STATUS_INPUT, note="VDI 2230 식으로 토크에서 구한 값을 하중으로 넣었다"),
        Quantity("peak_compression", "판의 최대 압축 응력", v["peak"], "MPa"),
        Quantity("interface_peak_pressure", "판 사이 면의 최대 압력", v["interface_peak"], "MPa"),
        Quantity("interface_mean_pressure", "판 사이 면의 평균 압력", v["interface_mean"], "MPa"),
        Quantity("pressed_radius", "판 사이가 눌리는 반지름", v["pressed_radius"], "mm",
                 note="체결부 바깥까지 모두 눌린다" if v["pressed_everywhere"] else "이 반지름 바깥은 눌리지 않는다 (실제로는 벌어진다)"),
        Quantity("pressed_radius_vdi_cone", "VDI 2230 변형 원뿔이 판 사이 면에서 닿는 반지름", cone_radius, "mm", note="비교용. 원뿔은 계산 모형의 모양이다"),
        Quantity("plate_resilience_fem", "판 컴플라이언스 (수치해석)", v["resilience"], "mm/N"),
        Quantity("plate_resilience_vdi", "판 컴플라이언스 (VDI 2230 식)", r.delta_p, "mm/N"),
        Quantity("plate_resilience_deviation", "두 방법의 차이 (수치해석 - 식) / 식", deviation, "%", note="판정 없음. 값만 보고한다"),
    )
    s = settings()
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=quantities, fields=fields,
        method="수치해석 (축대칭 유한요소, 선형 탄성)",
        basis=(
            f"격자: 반지름 방향 {len(x)}칸 x 두께 방향 {len(y)}칸, 네 절점 사각형 요소",
            f"판 재료: 머리 쪽 E = {joint.plate_head.youngs_modulus:,.0f} MPa, 너트 쪽 E = {joint.plate_nut.youngs_modulus:,.0f} MPa, 푸아송비 {s['poisson_ratio']:g}",
            "가정: 볼트는 풀지 않고 머리와 너트의 좌면 넓이에 고른 압력으로 바꿔 건다",
            "가정: 두 판은 붙어 있다 (떨어짐과 미끄럼을 풀지 않는다)",
            "가정: 선형 탄성, 운전 하중과 열 하중 없음",
            "판정 없음: 응력과 차이는 값만 보고한다",
        ),
        confidence=Confidence("low", "풀이기는 닫힌 해가 있는 문제(고른 압축, 두꺼운 원통)로 확인했지만, 이 체결 모형은 실측이나 다른 해석 프로그램과 대조하지 않았다"),
        source="체결 계산의 입력(치수, 판 재료)과 그 계산이 낸 조립 체결력",
        uncertainty="반영하지 않음. 대표 마찰의 체결력 하나로만 풀었다. 응력은 체결력에 비례하므로 마찰 범위의 체결력으로 바꿔 읽을 수 있다",
        residuals=(Residual("axial_balance", "축 방향 힘의 평형 (높이마다 단면이 받는 힘 + 체결력, 가장 큰 어긋남)", v["balance"], "N",
                            "격자가 성긴 만큼 생기는 오차다. 모형이 실제와 맞는지를 말해 주지는 않음"),),
        scope=SCOPE, failure_conditions=FAILS,
        presentation=("image:plate_axial_compression",),
        inputs={"joint": asdict(joint), "load": asdict(load)},
    )
