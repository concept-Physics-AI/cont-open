"""파라메트릭 볼트 조인트: 볼트·너트와 피체결판 2장 (v0.1 범위).

형상은 치수(매개변수)로만 표현한다. 규격을 바꾸면 피치·구멍·좌면 지름이 표준 데이터에서 다시 정해진다.
단위: 길이 mm, 힘 N, 응력 MPa, 토크 N·m (입력) / N·mm (내부).
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

from cont.packs.fastening import standards


@dataclass(frozen=True)
class Plate:
    thickness: float                 # mm
    youngs_modulus: float            # MPa
    limit_pressure: float | None = None  # 한계 면압 p_G (MPa). 없으면 면압 안전율을 내지 않는다.

    def __post_init__(self) -> None:
        if self.thickness <= 0 or self.youngs_modulus <= 0:
            raise ValueError("plate thickness and Young's modulus must be positive")


@dataclass(frozen=True)
class BoltedJoint:
    """관통 볼트 체결(DSV), 동심 하중. 와셔 없음."""

    size: str                        # 예: "M10"
    property_class: str              # 예: "10.9"
    plate_head: Plate                # 볼트 머리 쪽 판
    plate_nut: Plate                 # 너트 쪽 판
    outer_diameter: float            # 체결부 대체 바깥지름 D_A (mm)
    pitch: float | None = None       # None이면 보통나사 피치
    hole_diameter: float | None = None   # None이면 ISO 273 중간급
    shank_length: float = 0.0        # 나사 없는 축부 길이 (0이면 전체 나사 볼트)
    nut_youngs_modulus: float | None = None  # None이면 볼트와 같음

    def __post_init__(self) -> None:
        t = standards.thread_size(self.size)
        if self.outer_diameter <= self.hole:
            raise ValueError("outer_diameter must be larger than the hole diameter")
        if not 0.0 <= self.shank_length <= self.clamp_length:
            raise ValueError("shank_length must be between 0 and the clamp length")
        if self.hole <= t.d:
            raise ValueError("hole_diameter must be larger than the bolt diameter")
        if self.hole >= t.head_bearing_dw:
            raise ValueError("hole_diameter must be smaller than the head bearing diameter")
        standards.yield_strength(self.property_class, t.d)  # 등급이 데이터에 있는지 확인

    # --- 표준 데이터에서 정해지는 치수 ---
    @property
    def thread(self) -> standards.ThreadSize:
        return standards.thread_size(self.size)

    @property
    def d(self) -> float:
        return self.thread.d

    @property
    def p(self) -> float:
        return self.pitch if self.pitch is not None else self.thread.pitch_coarse

    @property
    def hole(self) -> float:
        return self.hole_diameter if self.hole_diameter is not None else self.thread.hole_medium

    @property
    def bearing_diameter(self) -> float:
        """머리·너트 좌면 바깥지름 d_W."""
        return self.thread.head_bearing_dw

    @property
    def clamp_length(self) -> float:
        """체결 길이 l_K."""
        return self.plate_head.thickness + self.plate_nut.thickness

    @property
    def yield_strength(self) -> float:
        return standards.yield_strength(self.property_class, self.d)

    # --- 대화로 수정 (슬라이스 3에서 LLM 도구가 이 함수를 부른다) ---
    def modified(self, **changes: Any) -> "BoltedJoint":
        """치수 일부만 바꾼 새 조인트. 규격을 바꾸면 피치·구멍은 표준값으로 돌아간다."""
        if "size" in changes:
            changes.setdefault("pitch", None)
            changes.setdefault("hole_diameter", None)
        for side in ("plate_head", "plate_nut"):
            key = f"{side}_thickness"
            if key in changes:
                changes[side] = replace(getattr(self, side), thickness=changes.pop(key))
        return replace(self, **changes)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BoltedJoint":
        d = dict(data)
        for side in ("plate_head", "plate_nut"):
            if isinstance(d.get(side), Mapping):
                d[side] = Plate(**d[side])
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown joint fields: {sorted(unknown)}")
        return cls(**d)


@dataclass(frozen=True)
class LoadCase:
    """조임 조건과 운전 하중."""

    tightening_torque: float         # 조임 토크 M_A (N·m)
    friction_thread: float           # 나사면 마찰계수 mu_G (대표값)
    friction_head: float             # 좌면 마찰계수 mu_K (대표값)
    friction_range: tuple[float, float] | None = None  # (최소, 최대). 나사면·좌면에 같이 적용해 체결력 범위를 구한다.
    axial_load_max: float = 0.0      # 축방향 운전 하중 F_A 최대 (N, 인장 +)
    axial_load_min: float = 0.0      # 축방향 운전 하중 F_A 최소 (N)
    transverse_load: float = 0.0     # 축직각 하중 F_Q (N)
    friction_interface: float | None = None  # 판 사이 마찰계수 mu_T (미끄럼 안전율에 필요)
    load_introduction_factor: float = 1.0    # 하중 도입 계수 n (0 < n <= 1)
    embedding: float = 0.0           # 함몰량 f_Z (mm)

    def __post_init__(self) -> None:
        if self.tightening_torque <= 0:
            raise ValueError("tightening_torque must be positive")
        for mu in (self.friction_thread, self.friction_head):
            if mu <= 0:
                raise ValueError("friction coefficients must be positive")
        if self.friction_range is not None:
            lo, hi = self.friction_range
            if not 0 < lo <= hi:
                raise ValueError("friction_range must be (min, max) with 0 < min <= max")
        if self.axial_load_min > self.axial_load_max:
            raise ValueError("axial_load_min must not exceed axial_load_max")
        if not 0 < self.load_introduction_factor <= 1:
            raise ValueError("load_introduction_factor must be in (0, 1]")
        if self.embedding < 0 or self.transverse_load < 0:
            raise ValueError("embedding and transverse_load must not be negative")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LoadCase":
        d = dict(data)
        if d.get("friction_range") is not None:
            d["friction_range"] = tuple(d["friction_range"])
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown load fields: {sorted(unknown)}")
        return cls(**d)
