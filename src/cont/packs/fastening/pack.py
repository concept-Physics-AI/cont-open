"""체결 물리 팩: 입력(dict) → VDI 2230 계산 → PhysicsAnswer."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from cont.answer import STATUS_INPUT, STATUS_SIMULATED, Confidence, PhysicsAnswer, Quantity, Residual
from cont.packs.fastening import vdi2230
from cont.packs.fastening.joint import BoltedJoint, LoadCase


SCOPE = "동심 체결과 동심 하중, 관통 볼트, 판 2장, 와셔 없음, 열 하중 없음"
FAILS = ("편심 하중", "열 하중", "탭 구멍 체결", "와셔가 있는 체결", "판이 벌어진 뒤 (벌어짐 안전율 1 미만)")


class FasteningPack:
    name = "fastening"

    def solve(self, inputs: Mapping[str, Any], question: str = "") -> PhysicsAnswer:
        """inputs = {"joint": {...}, "load": {...}} (BoltedJoint, LoadCase의 필드)."""
        joint = inputs["joint"] if isinstance(inputs["joint"], BoltedJoint) else BoltedJoint.from_dict(inputs["joint"])
        load = inputs["load"] if isinstance(inputs["load"], LoadCase) else LoadCase.from_dict(inputs["load"])
        return answer(joint, load, question)


def answer(joint: BoltedJoint, load: LoadCase, question: str = "") -> PhysicsAnswer:
    r = vdi2230.calculate(joint, load)
    g = r.geometry

    def q(key: str, label: str, value: float | None, unit: str, rng: tuple[float, float] | None = None,
          note: str | None = None, status: str | None = None) -> Quantity:
        return Quantity(key, label, value, unit, rng, note, status)

    need_fq = "축직각 하중과 판 사이 마찰계수를 주면 계산한다"
    need_fa = "축방향 운전 하중을 주면 계산한다"
    need_pg = "판의 한계 면압(limit_pressure)을 주면 계산한다"
    quantities = (
        q("stress_area", "응력 단면적 A_S", g.a_s, "mm^2", status=STATUS_INPUT),
        q("clamp_length", "체결 길이 l_K", joint.clamp_length, "mm", status=STATUS_INPUT),
        q("preload", "조립 체결력 F_M", r.preload, "N", (r.preload_min, r.preload_max),
          None if load.friction_range else "마찰 범위(friction_range)를 주지 않아 범위가 한 값이다"),
        q("bolt_resilience", "볼트 컴플라이언스 delta_S", r.delta_s, "mm/N"),
        q("plate_resilience", "판 컴플라이언스 delta_P", r.delta_p, "mm/N"),
        q("load_factor", "하중 분담계수 Phi_n", r.load_factor, "-"),
        q("preload_loss_embedding", "함몰에 의한 체결력 손실 F_Z", r.preload_loss_embedding, "N"),
        q("bolt_load_max", "볼트 최대 하중 F_S,max", r.bolt_load_max, "N"),
        q("residual_clamp_min", "최소 잔류 체결력 F_KR,min", r.residual_clamp_min, "N"),
        q("bolt_equivalent_stress_assembly", "조임 시 볼트 등가응력", r.stress_assembly, "MPa"),
        q("bolt_equivalent_stress_working", "운전 시 볼트 등가응력", r.stress_working, "MPa"),
        q("safety_yield", "항복 안전율 S_F", r.safety_yield, "-"),
        q("opening_load", "벌어짐 시작 하중 F_A,ab", r.opening_load, "N"),
        q("safety_opening", "벌어짐 안전율", r.safety_opening, "-", note=None if r.safety_opening is not None else need_fa),
        q("safety_slip", "미끄럼 안전율 S_G", r.safety_slip, "-", note=None if r.safety_slip is not None else need_fq),
        q("surface_pressure", "좌면 최대 압력 p_max", r.pressure_max, "MPa"),
        q("safety_pressure_head", "면압 안전율 (머리 쪽 판)", r.safety_pressure_head, "-",
          note=None if r.safety_pressure_head is not None else need_pg),
        q("safety_pressure_nut", "면압 안전율 (너트 쪽 판)", r.safety_pressure_nut, "-",
          note=None if r.safety_pressure_nut is not None else need_pg),
        q("stress_amplitude", "볼트 응력 진폭 sigma_a", r.stress_amplitude, "MPa"),
        q("safety_fatigue", "피로 안전율 S_D", r.safety_fatigue, "-",
          note=None if r.safety_fatigue is not None else "변동하는 축방향 하중이 없어 계산하지 않는다"),
        q("thread_shear_margin", "나사산 전단 여유", None, "-", note="슬라이스 1 범위 밖 (필요 물림 길이 계산 미구현)"),
    )
    basis = (
        "VDI 2230 Part 1 해석식: 동심 체결·동심 하중, 관통 볼트 체결(DSV), 볼트·너트와 판 2장, 와셔 없음",
        "나사 치수 ISO 724, 응력 단면적 ISO 898-1, 표준 데이터 packs/fastening/tables/iso_metric.yaml",
        f"볼트 {joint.size} x 피치 {g.p} mm, 강도 등급 {joint.property_class} (Rp0.2 = {r.yield_strength:.0f} MPa)",
        f"가정: 하중 도입 계수 n = {load.load_introduction_factor}, 함몰량 f_Z = {load.embedding} mm, 열 하중 없음",
        "가정: 머리와 너트의 좌면 지름이 같고, 좌면 안지름은 구멍 지름과 같다",
        "피로 한도는 열처리 전 전조 나사(SV) 기준, 반복 수 2x10^6 이상",
        "판정 없음: 안전율과 응력은 값만 보고한다. 합격·불합격은 허용 오차·기준 프로파일이 정해진 환경에서만 한다",
    )
    balance = abs(r.bolt_extra_load_max + r.plate_relief_max - load.axial_load_max)
    return PhysicsAnswer(
        status=STATUS_SIMULATED,
        source="사람이 넣은 입력: 치수, 강도 등급, 조임 토크, 마찰계수, 운전 하중. 표준 데이터는 packs/fastening/tables/iso_metric.yaml",
        uncertainty=(f"마찰 산포만 반영함 (마찰계수 {load.friction_range[0]:g} ~ {load.friction_range[1]:g}). "
                     "체결력은 범위로, 남는 체결력·응력·안전율은 불리한 쪽 끝으로 계산함" if load.friction_range
                     else "마찰 범위를 주지 않아 반영하지 않음. 모든 값이 한 값으로만 나옴"),
        residuals=(Residual("force_balance", "힘의 평형 (볼트가 더 받는 힘 + 판에서 줄어드는 힘 − 운전 하중)", balance, "N",
                            "닫힌 식이라 0이며, 모형이 실제와 맞는지를 말해 주지는 않음"),),
        scope=SCOPE,
        failure_conditions=FAILS,
        question=question,
        quantities=quantities,
        method="해석식 (VDI 2230 Part 1)",
        basis=basis,
        confidence=Confidence(
            "medium",
            "표준 계산식을 구현했고 내부 일관성 테스트는 통과했지만, 표준 예제·FEM 기준값과의 대조(슬라이스 2)는 아직 하지 않았다",
        ),
        presentation=("table:quantities", "graph:torque_vs_preload"),
        inputs={"joint": asdict(joint), "load": asdict(load)},
    )
