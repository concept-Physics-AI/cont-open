"""형상 명세: 한 축(z)을 공유하는 회전체·각기둥 부품의 모음.

볼트 조인트처럼 축 하나에 늘어선 부품을 나타내는 데 충분한 가장 작은 표현이다. 단위 mm.
축이 여러 개인 형상, 모따기·나사산 같은 세부는 아직 없다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Part:
    name: str                   # 화면에 보이는 이름 (한국어)
    role: str                   # bolt | nut | plate_head | plate_nut ... (색과 CAD 내보내기에서 구분에 쓴다)
    z0: float                   # 아래 면
    z1: float                   # 위 면
    outer: float                # 원: 바깥지름 / 육각: 맞변 거리
    inner: float = 0.0          # 구멍 지름 (0이면 속이 찬 부품)
    profile: str = "circle"     # circle | hexagon (바깥 윤곽)
    sweep: float = 360.0        # 축 둘레로 채운 각도. 360보다 작으면 잘라 낸 단면이 보인다 (화면용)

    def __post_init__(self) -> None:
        if self.z1 <= self.z0:
            raise ValueError(f"{self.name}: z1 must be above z0")
        if self.outer <= 0 or self.inner < 0:
            raise ValueError(f"{self.name}: diameters must be positive")
        if self.profile not in ("circle", "hexagon"):
            raise ValueError(f"{self.name}: unknown profile '{self.profile}'")
        if self.inner >= self.outer:                     # 육각은 맞변 거리가 가장 좁은 폭이다
            raise ValueError(f"{self.name}: the hole must be smaller than the outer size")
        if not 0 < self.sweep <= 360:
            raise ValueError(f"{self.name}: sweep must be in (0, 360]")
        if self.profile == "hexagon" and self.sweep != 360:
            raise ValueError(f"{self.name}: a hexagon part cannot be cut open")

    @property
    def height(self) -> float:
        return self.z1 - self.z0

    @property
    def exact_volume(self) -> float:
        """수식으로 구한 부피 (mm^3)."""
        a_out = math.pi / 4 * self.outer ** 2 if self.profile == "circle" else math.sqrt(3) / 2 * self.outer ** 2
        return (a_out - math.pi / 4 * self.inner ** 2) * self.height * self.sweep / 360.0


@dataclass(frozen=True)
class Assembly:
    name: str
    parts: tuple[Part, ...]

    @property
    def z_range(self) -> tuple[float, float]:
        return min(p.z0 for p in self.parts), max(p.z1 for p in self.parts)

    @property
    def max_radius(self) -> float:
        return max((p.outer / 2 if p.profile == "circle" else p.outer / math.sqrt(3)) for p in self.parts)

    def part(self, role: str) -> Part:
        for p in self.parts:
            if p.role == role:
                return p
        raise KeyError(role)

    def opened(self, roles: tuple[str, ...], sweep: float = 270.0) -> "Assembly":
        """roles의 부품을 sweep 각도만 남기고 잘라 낸 새 조립체 (안쪽이 보이는 화면용)."""
        from dataclasses import replace
        return Assembly(self.name, tuple(replace(p, sweep=sweep) if p.role in roles else p for p in self.parts))
