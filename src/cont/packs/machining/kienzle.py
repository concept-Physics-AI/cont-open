"""절삭력 해석식: 키엔츨레(Kienzle) 식과 선삭의 기본 관계식.

이 모듈은 식만 담는다. 판정(합격·불합격)은 하지 않는다.

    칩 두께 h = f sin(kappa),  칩 폭 b = a_p / sin(kappa)
    비절삭저항 k_c = k_c1.1 * h^(-m_c)
    주절삭력 F_c = k_c * b * h
    절삭 동력 P_c = F_c * v_c / 60000 (kW),  주축 회전수 n = 1000 v_c / (pi D)
    이론 표면 거칠기 R_t = f^2 / (8 r_e)  (공구 코가 남기는 골의 높이)

슬라이스 1에 넣지 않은 것: 경사각·절삭 속도·공구 마모에 따른 보정 계수, 이송 분력과 배분력, 열, 채터(떨림), 공구 수명.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from cont.packs.machining.cut import TurningCut

TABLES = Path(__file__).parent / "tables"


@lru_cache(maxsize=1)
def _materials() -> dict[str, dict]:
    with open(TABLES / "materials.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["materials"]


def material_names() -> list[str]:
    return list(_materials())


@dataclass(frozen=True)
class Material:
    name: str
    label: str
    specific_cutting_force: float
    exponent: float
    verified: bool
    given: bool                       # 사용자가 값을 직접 주었는가


def material(cut: TurningCut) -> Material:
    if cut.specific_cutting_force is not None:
        return Material(cut.material, cut.material, cut.specific_cutting_force, float(cut.exponent), False, True)
    try:
        m = _materials()[cut.material]
    except KeyError:
        raise ValueError(f"'{cut.material}'은(는) 재료 표에 없습니다. 쓸 수 있는 재료: {', '.join(material_names())}. "
                         "또는 specific_cutting_force와 exponent를 직접 주세요") from None
    return Material(cut.material, m["label"], float(m["specific_cutting_force"]), float(m["exponent"]), bool(m["verified"]), False)


@dataclass(frozen=True)
class Result:
    material: Material
    chip_thickness: float             # h (mm)
    chip_width: float                 # b (mm)
    chip_area: float                  # A = a_p * f (mm^2)
    specific_force: float             # k_c (N/mm^2)
    cutting_force: float              # F_c (N)
    spindle_speed: float              # n (rev/min)
    torque: float                     # 주축 토크 (N·m)
    cutting_power: float              # P_c (kW)
    motor_power: float | None         # P_c / 효율 (kW)
    removal_rate: float               # Q (cm^3/min)
    roughness_rt: float | None        # 이론 최대 높이 R_t (um)
    time: float | None                # 가공 시간 (s)


def calculate(cut: TurningCut) -> Result:
    m = material(cut)
    sin_k = math.sin(math.radians(cut.edge_angle))
    h = cut.feed * sin_k
    b = cut.depth / sin_k
    k_c = m.specific_cutting_force * h ** (-m.exponent)
    force = k_c * b * h
    n = 1000.0 * cut.cutting_speed / (math.pi * cut.diameter)
    power = force * cut.cutting_speed / 60000.0
    return Result(
        material=m, chip_thickness=h, chip_width=b, chip_area=cut.depth * cut.feed, specific_force=k_c, cutting_force=force,
        spindle_speed=n, torque=force * cut.diameter / 2000.0, cutting_power=power,
        motor_power=None if cut.machine_efficiency is None else power / cut.machine_efficiency,
        removal_rate=cut.depth * cut.feed * cut.cutting_speed,
        roughness_rt=None if cut.nose_radius is None else cut.feed**2 / (8 * cut.nose_radius) * 1000.0,
        time=None if cut.length is None else cut.length / (cut.feed * n) * 60.0,
    )
