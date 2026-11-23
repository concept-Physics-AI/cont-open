"""선삭(바깥지름 깎기) 한 번의 조건. 값은 매개변수로만 다룬다.

단위: 길이 mm, 절삭 속도 m/min, 이송 mm/rev, 각 도(deg), 힘 N, 동력 kW.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class TurningCut:
    material: str                        # 재료 표의 이름 (예: "C45"). 표에 없으면 비절삭저항을 직접 준다
    diameter: float                      # 깎기 전 지름 D (mm)
    cutting_speed: float                 # 절삭 속도 v_c (m/min)
    feed: float                          # 이송 f (mm/rev)
    depth: float                         # 절입 깊이 a_p (mm)
    edge_angle: float = 90.0             # 절입각 kappa (deg). 날이 이송 방향과 이루는 각
    nose_radius: float | None = None     # 공구 코 반지름 r_e (mm). 주면 이론 표면 거칠기를 낸다
    length: float | None = None          # 깎는 길이 (mm). 주면 가공 시간을 낸다
    specific_cutting_force: float | None = None   # k_c1.1 (N/mm^2). 주면 재료 표 대신 쓴다
    exponent: float | None = None        # m_c. 위와 함께 준다
    machine_efficiency: float | None = None       # 주축 구동 효율 (0 ~ 1). 주면 전동기 동력을 낸다

    def __post_init__(self) -> None:
        for name in ("diameter", "cutting_speed", "feed", "depth"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not 0 < self.edge_angle < 180:
            raise ValueError("edge_angle must be between 0 and 180 degrees")
        if self.depth * 2 >= self.diameter:
            raise ValueError("depth must be smaller than the radius")
        for name in ("nose_radius", "length", "specific_cutting_force"):
            v = getattr(self, name)
            if v is not None and v <= 0:
                raise ValueError(f"{name} must be positive")
        if (self.specific_cutting_force is None) != (self.exponent is None):
            raise ValueError("give specific_cutting_force and exponent together")
        if self.exponent is not None and not 0 <= self.exponent < 1:
            raise ValueError("exponent must be in [0, 1)")
        if self.machine_efficiency is not None and not 0 < self.machine_efficiency <= 1:
            raise ValueError("machine_efficiency must be in (0, 1]")

    def modified(self, **changes: Any) -> "TurningCut":
        return replace(self, **changes)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TurningCut":
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown cut fields: {sorted(unknown)}")
        return cls(**data)
