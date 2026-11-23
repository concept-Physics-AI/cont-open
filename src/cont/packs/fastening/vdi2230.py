"""VDI 2230 Part 1 해석식 (동심 체결·동심 하중, 관통 볼트 DSV).

이 모듈은 식만 담는다. 입력은 치수와 하중, 출력은 숫자다. 판정(합격·불합격)은 하지 않는다.
단위: mm, N, MPa, N·mm.

슬라이스 1에 넣지 않은 것: 편심 체결·편심 하중, 열 하중, 탭 구멍 체결(ESV), 와셔,
필요 물림 길이(나사산 전단) 계산, 조임 방법별 조임 계수 표, 표면 거칠기별 함몰량 표.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.standards import vdi_constant


# ---------------------------------------------------------------- 나사 형상
@dataclass(frozen=True)
class ThreadGeometry:
    d: float       # 호칭 지름
    p: float       # 피치
    d2: float      # 유효 지름
    d3: float      # 골 지름
    d_s: float     # 응력 단면 지름 (d2 + d3) / 2
    a_s: float     # 응력 단면적 A_S
    a_d3: float    # 골 단면적 A_d3
    a_n: float     # 호칭 단면적 A_N


def thread_geometry(d: float, p: float) -> ThreadGeometry:
    """ISO 미터 나사 기본 치수 (ISO 724)와 응력 단면적 (ISO 898-1)."""
    d2 = d - 0.649519 * p
    d3 = d - 1.226869 * p
    d_s = (d2 + d3) / 2
    return ThreadGeometry(d, p, d2, d3, d_s, math.pi / 4 * d_s**2, math.pi / 4 * d3**2, math.pi / 4 * d**2)


# ---------------------------------------------------------------- 토크 ↔ 체결력
def thread_torque_arm(p: float, d2: float, mu_g: float) -> float:
    """나사부 토크 팔 길이: M_G = F_M * (0.16 P + 0.58 d2 mu_G)."""
    return 0.16 * p + 0.58 * d2 * mu_g


def head_torque_arm(d_w: float, d_ha: float, mu_k: float) -> float:
    """좌면 토크 팔 길이: M_K = F_M * (D_Km / 2) * mu_K, D_Km = (d_W + d_ha) / 2."""
    return (d_w + d_ha) / 4 * mu_k


def preload_from_torque(torque: float, p: float, d2: float, d_w: float, d_ha: float, mu_g: float, mu_k: float) -> float:
    """조임 토크 M_A (N·mm) → 조립 체결력 F_M (N)."""
    return torque / (thread_torque_arm(p, d2, mu_g) + head_torque_arm(d_w, d_ha, mu_k))


def torque_from_preload(preload: float, p: float, d2: float, d_w: float, d_ha: float, mu_g: float, mu_k: float) -> float:
    return preload * (thread_torque_arm(p, d2, mu_g) + head_torque_arm(d_w, d_ha, mu_k))


# ---------------------------------------------------------------- 볼트 탄성 컴플라이언스
def bolt_resilience(joint: BoltedJoint) -> float:
    """delta_S (mm/N): 머리 + 축부 + 물리지 않은 나사부 + 물린 나사부 + 너트."""
    g = thread_geometry(joint.d, joint.p)
    e_s = vdi_constant("youngs_modulus_bolt")
    e_m = joint.nut_youngs_modulus or e_s
    d = joint.d
    head = vdi_constant("head_length_factor_hex") * d / (e_s * g.a_n)
    shank = joint.shank_length / (e_s * g.a_n)
    free_thread = (joint.clamp_length - joint.shank_length) / (e_s * g.a_d3)
    engaged = vdi_constant("engaged_thread_length_factor") * d / (e_s * g.a_d3)
    nut = vdi_constant("nut_length_factor_through") * d / (e_m * g.a_n)
    return head + shank + free_thread + engaged + nut


# ---------------------------------------------------------------- 판 탄성 컴플라이언스
def cone_angle_tan(clamp_length: float, d_w: float, outer_diameter: float) -> float:
    """변형 원뿔 각 tan(phi_D), 관통 볼트 체결(DSV)."""
    beta_l = clamp_length / d_w
    y = outer_diameter / d_w
    return 0.362 + 0.032 * math.log(beta_l / 2) + 0.153 * math.log(y)


def _cone(d_a: float, d_b: float, d_h: float, e: float, tan_phi: float) -> float:
    """지름이 d_a → d_b로 커지는 원뿔 구간의 컴플라이언스."""
    return math.log((d_b - d_h) * (d_a + d_h) / ((d_b + d_h) * (d_a - d_h))) / (e * math.pi * d_h * tan_phi)


def _sleeve(length: float, d_out: float, d_h: float, e: float) -> float:
    return 4 * length / (e * math.pi * (d_out**2 - d_h**2))


def _half_resilience(joint: BoltedJoint, own_thickness: float, own_e: float, other_e: float, tan_phi: float) -> float:
    """좌면에서 체결 길이 중앙까지 반쪽의 컴플라이언스. 재료 경계와 원뿔→슬리브 전환점에서 구간을 나눈다."""
    d_w, d_h, d_out = joint.bearing_diameter, joint.hole, joint.outer_diameter
    half = joint.clamp_length / 2
    if d_out <= d_w:  # 원뿔이 생기지 않고 전체가 슬리브
        z_cone_end = 0.0
    else:
        z_cone_end = min(half, (d_out - d_w) / (2 * tan_phi))
    cuts = sorted({0.0, half, min(own_thickness, half), z_cone_end})
    total = 0.0
    for z0, z1 in zip(cuts, cuts[1:]):
        if z1 <= z0:
            continue
        e = own_e if (z0 + z1) / 2 < own_thickness else other_e
        if z1 <= z_cone_end:
            total += _cone(d_w + 2 * z0 * tan_phi, d_w + 2 * z1 * tan_phi, d_h, e, tan_phi)
        else:
            total += _sleeve(z1 - z0, d_out, d_h, e)
    return total


def plate_resilience(joint: BoltedJoint) -> float:
    """delta_P (mm/N): 머리 쪽과 너트 쪽에서 시작하는 대칭 변형 원뿔(+슬리브). 두 판의 E가 달라도 된다."""
    tan_phi = cone_angle_tan(joint.clamp_length, joint.bearing_diameter, joint.outer_diameter)
    if joint.outer_diameter > joint.bearing_diameter and tan_phi <= 0:
        raise ValueError("deformation cone angle is not positive for this geometry (clamp length too short)")
    ph, pn = joint.plate_head, joint.plate_nut
    return (
        _half_resilience(joint, ph.thickness, ph.youngs_modulus, pn.youngs_modulus, tan_phi)
        + _half_resilience(joint, pn.thickness, pn.youngs_modulus, ph.youngs_modulus, tan_phi)
    )


# ---------------------------------------------------------------- 전체 계산
@dataclass(frozen=True)
class Result:
    geometry: ThreadGeometry
    delta_s: float
    delta_p: float
    load_factor: float                 # Phi_n = n * delta_P / (delta_S + delta_P)
    preload: float                     # F_M (대표 마찰)
    preload_min: float                 # F_M,min (마찰 최대)
    preload_max: float                 # F_M,max (마찰 최소)
    preload_loss_embedding: float      # F_Z
    bolt_extra_load_max: float         # F_SA,max
    plate_relief_max: float            # F_PA,max
    bolt_load_max: float               # F_S,max = F_M,max + F_SA,max
    residual_clamp_min: float          # F_KR,min = F_M,min - F_Z - F_PA,max
    stress_assembly: float             # sigma_red,M (F_M,max 기준)
    stress_working: float              # sigma_red,B
    yield_strength: float
    safety_yield: float                # S_F = Rp0.2 / sigma_red,B
    opening_load: float                # 판이 벌어지기 시작하는 축 하중 F_A,ab
    safety_opening: float | None       # F_A,ab / F_A,max
    safety_slip: float | None          # S_G = F_KR,min * mu_T / F_Q
    bearing_area: float
    pressure_max: float                # p_max = F_S,max / A_p
    safety_pressure_head: float | None
    safety_pressure_nut: float | None
    stress_amplitude: float            # sigma_a
    fatigue_limit: float               # sigma_ASV (열처리 전 전조)
    safety_fatigue: float | None       # S_D = sigma_ASV / sigma_a


def calculate(joint: BoltedJoint, load: LoadCase) -> Result:
    g = thread_geometry(joint.d, joint.p)
    d_w, d_h = joint.bearing_diameter, joint.hole
    torque = load.tightening_torque * 1000.0  # N·m → N·mm

    def f_m(mu_g: float, mu_k: float) -> float:
        return preload_from_torque(torque, g.p, g.d2, d_w, d_h, mu_g, mu_k)

    preload = f_m(load.friction_thread, load.friction_head)
    if load.friction_range is None:
        preload_min = preload_max = preload
        mu_g_at_max = load.friction_thread
    else:
        mu_lo, mu_hi = load.friction_range
        preload_max, preload_min = f_m(mu_lo, mu_lo), f_m(mu_hi, mu_hi)
        mu_g_at_max = mu_lo

    delta_s = bolt_resilience(joint)
    delta_p = plate_resilience(joint)
    phi = load.load_introduction_factor * delta_p / (delta_s + delta_p)
    f_z = load.embedding / (delta_s + delta_p)

    f_sa_max = phi * load.axial_load_max
    f_sa_min = phi * load.axial_load_min
    f_pa_max = (1 - phi) * load.axial_load_max
    f_s_max = preload_max + f_sa_max
    f_kr_min = preload_min - f_z - f_pa_max

    # 볼트 응력: 인장 + 나사부 비틀림 (최소 단면은 응력 단면)
    w_p = math.pi * g.d_s**3 / 16
    tau = preload_max * thread_torque_arm(g.p, g.d2, mu_g_at_max) / w_p
    sigma_m = preload_max / g.a_s
    stress_assembly = math.sqrt(sigma_m**2 + 3 * tau**2)
    k_tau = vdi_constant("torsion_residual_factor")
    stress_working = math.sqrt((f_s_max / g.a_s) ** 2 + 3 * (k_tau * tau) ** 2)
    rp = joint.yield_strength

    opening_load = (preload_min - f_z) / (1 - phi)
    safety_opening = opening_load / load.axial_load_max if load.axial_load_max > 0 else None
    safety_slip = None
    if load.transverse_load > 0 and load.friction_interface is not None:
        safety_slip = f_kr_min * load.friction_interface / load.transverse_load

    bearing_area = math.pi / 4 * (d_w**2 - d_h**2)
    pressure = f_s_max / bearing_area

    def s_p(limit: float | None) -> float | None:
        return None if limit is None else limit / pressure

    stress_amplitude = (f_sa_max - f_sa_min) / (2 * g.a_s)
    fatigue_limit = 0.85 * (150 / g.d + 45)
    safety_fatigue = fatigue_limit / stress_amplitude if stress_amplitude > 0 else None

    return Result(
        geometry=g, delta_s=delta_s, delta_p=delta_p, load_factor=phi,
        preload=preload, preload_min=preload_min, preload_max=preload_max, preload_loss_embedding=f_z,
        bolt_extra_load_max=f_sa_max, plate_relief_max=f_pa_max, bolt_load_max=f_s_max, residual_clamp_min=f_kr_min,
        stress_assembly=stress_assembly, stress_working=stress_working, yield_strength=rp,
        safety_yield=rp / stress_working,
        opening_load=opening_load, safety_opening=safety_opening, safety_slip=safety_slip,
        bearing_area=bearing_area, pressure_max=pressure,
        safety_pressure_head=s_p(joint.plate_head.limit_pressure),
        safety_pressure_nut=s_p(joint.plate_nut.limit_pressure),
        stress_amplitude=stress_amplitude, fatigue_limit=fatigue_limit, safety_fatigue=safety_fatigue,
    )
