"""절삭가공 물리 팩: 입력(dict) → 키엔츨레 식 → PhysicsAnswer."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from cont.answer import STATUS_INPUT, STATUS_SIMULATED, Confidence, PhysicsAnswer, Quantity
from cont.packs.machining import kienzle
from cont.packs.machining.cut import TurningCut

SCOPE = "바깥지름 선삭, 한 번 깎기, 일정한 절삭 조건. 날카로운 새 공구"
FAILS = ("공구가 닳았을 때 (절삭력이 커진다)", "칩 두께가 아주 얇을 때 (식이 맞는 범위 밖)", "떨림(채터)이 생길 때", "단속 절삭",
         "이론 표면 거칠기: 이송이 코 반지름에 비해 클 때와 구성인선이 생길 때")


class MachiningPack:
    name = "machining"

    def solve(self, inputs: Mapping[str, Any], question: str = "") -> PhysicsAnswer:
        """inputs = {"cut": {...}} (TurningCut의 필드)."""
        cut = inputs["cut"] if isinstance(inputs["cut"], TurningCut) else TurningCut.from_dict(inputs["cut"])
        return answer(cut, question)


def answer(cut: TurningCut, question: str = "") -> PhysicsAnswer:
    r = kienzle.calculate(cut)
    m = r.material

    def q(key: str, label: str, value: float | None, unit: str, note: str | None = None, status: str | None = None) -> Quantity:
        return Quantity(key, label, value, unit, None, note, status)

    quantities = (
        q("specific_cutting_force_unit", "재료의 비절삭저항 k_c1.1", m.specific_cutting_force, "N/mm^2",
          "직접 준 값" if m.given else (None if m.verified else "재료 표의 값. 원문과 대조하지 않았다"), STATUS_INPUT),
        q("chip_thickness", "칩 두께 h", r.chip_thickness, "mm"),
        q("chip_width", "칩 폭 b", r.chip_width, "mm"),
        q("specific_cutting_force", "비절삭저항 k_c (이 칩 두께에서)", r.specific_force, "N/mm^2"),
        q("cutting_force", "주절삭력 F_c", r.cutting_force, "N"),
        q("spindle_speed", "주축 회전수 n", r.spindle_speed, "rev/min"),
        q("spindle_torque", "주축 토크", r.torque, "N·m"),
        q("cutting_power", "절삭 동력 P_c", r.cutting_power, "kW"),
        q("motor_power", "전동기 동력", r.motor_power, "kW", None if r.motor_power is not None else "주축 구동 효율(machine_efficiency)을 주면 계산한다"),
        q("removal_rate", "재료 제거율 Q", r.removal_rate, "cm^3/min"),
        q("roughness_rt", "이론 표면 거칠기 R_t (최대 높이)", r.roughness_rt, "um",
          "공구 코가 남기는 골의 높이. 실제 거칠기는 이보다 크다" if r.roughness_rt is not None else "공구 코 반지름(nose_radius)을 주면 계산한다"),
        q("cutting_time", "가공 시간", r.time, "s", None if r.time is not None else "깎는 길이(length)를 주면 계산한다"),
    )
    data = ("사용자가 직접 준 비절삭저항" if m.given else
            f"재료 표 packs/machining/tables/materials.yaml의 {m.label}" + ("" if m.verified else " (원문과 대조하지 않은 값)"))
    return PhysicsAnswer(
        status=STATUS_SIMULATED, question=question, quantities=quantities,
        method="해석식 (키엔츨레 절삭력 식)",
        basis=(
            "주절삭력 F_c = k_c1.1 * h^(-m_c) * b * h,  h = f sin(kappa),  b = a_p / sin(kappa)",
            f"재료 {m.label}: k_c1.1 = {m.specific_cutting_force:g} N/mm^2, m_c = {m.exponent:g}. {data}",
            f"조건: 지름 {cut.diameter:g} mm, 절삭 속도 {cut.cutting_speed:g} m/min, 이송 {cut.feed:g} mm/rev, 절입 {cut.depth:g} mm, 절입각 {cut.edge_angle:g} 도",
            "가정: 경사각·절삭 속도·공구 마모에 따른 보정 계수를 넣지 않는다 (모두 1로 본다)",
            "가정: 이론 표면 거칠기는 공구 코의 모양만으로 정해진다",
            "판정 없음: 힘과 동력은 값만 보고한다. 기계의 동력으로 깎을 수 있는지는 기준이 정해진 환경에서만 판정한다",
        ),
        confidence=Confidence("low" if not m.verified else "medium",
                              "식은 구현했고 내부 일관성 테스트는 통과했지만, 재료 값을 원문과 맞추지 않았고 실측 절삭력과 대조하지 않았다"),
        source=f"사람이 넣은 절삭 조건. {data}",
        uncertainty="",                 # 비절삭저항의 산포를 아직 다루지 않는다 → 보고하지 않음
        scope=SCOPE, failure_conditions=FAILS,
        presentation=("table:quantities",),
        inputs={"cut": asdict(cut)},
    )
