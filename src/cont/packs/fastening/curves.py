"""화면에 그릴 곡선을 계산한다 (그림은 view가 그린다). 식은 vdi2230의 것을 그대로 쓴다."""
from __future__ import annotations

import math
from dataclasses import dataclass

from cont.packs.fastening import vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase


@dataclass(frozen=True)
class TorquePreload:
    """조임 토크와 체결력의 관계 (원점을 지나는 직선). 마찰이 작을수록 같은 토크에서 체결력이 크다."""
    torque: float               # 지금의 조임 토크 (N·m)
    preload: float              # 대표 마찰에서의 체결력 (N)
    slope: float                # 대표 마찰: N per N·m
    slope_min: float            # 마찰 최대일 때 (체결력 최소)
    slope_max: float            # 마찰 최소일 때 (체결력 최대)
    preload_at_yield: float     # 조임 중 등가응력이 Rp0.2에 이르는 체결력 (대표 마찰)


@dataclass(frozen=True)
class JointDiagram:
    """체결 선도: 가로는 변형(mm), 세로는 힘(N). 볼트는 늘어나고 판은 눌린다."""
    bolt_elongation: float      # f_SM = F_M · delta_S
    plate_compression: float    # f_PM = F_M · delta_P
    preload: float              # F_M (대표 마찰)
    axial_load: float           # F_A,max
    bolt_extra: float           # F_SA = Phi · F_A
    plate_relief: float         # F_PA = (1 - Phi) · F_A
    extra_elongation: float     # 운전 하중으로 더 늘어난 양


def torque_preload(joint: BoltedJoint, load: LoadCase) -> TorquePreload:
    g = vdi2230.thread_geometry(joint.d, joint.p)

    def slope(mu_g: float, mu_k: float) -> float:
        return 1000.0 / (vdi2230.thread_torque_arm(g.p, g.d2, mu_g) + vdi2230.head_torque_arm(joint.bearing_diameter, joint.hole, mu_k))

    s = slope(load.friction_thread, load.friction_head)
    lo, hi = load.friction_range or (None, None)
    s_max = slope(lo, lo) if lo else s
    s_min = slope(hi, hi) if hi else s
    w_p = math.pi * g.d_s ** 3 / 16
    per_n = math.sqrt((1 / g.a_s) ** 2 + 3 * (vdi2230.thread_torque_arm(g.p, g.d2, load.friction_thread) / w_p) ** 2)
    return TorquePreload(load.tightening_torque, s * load.tightening_torque, s, s_min, s_max, joint.yield_strength / per_n)


def joint_diagram(joint: BoltedJoint, load: LoadCase) -> JointDiagram:
    r = vdi2230.calculate(joint, load)
    return JointDiagram(r.preload * r.delta_s, r.preload * r.delta_p, r.preload, load.axial_load_max,
                        r.bolt_extra_load_max, r.plate_relief_max, r.bolt_extra_load_max * r.delta_s)
