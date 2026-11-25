"""공통 대상 명세: 같은 대상을 이미지·3D·4D·그래프가 같은 부품 ID로 가리키게 하는 한 장의 명세.

- 구조(ObjectSpec): 부품 ID·이름·위치·치수와 공정 단계. 내용의 해시가 version이다. 치수가 바뀌면 version이 바뀐다.
- 보기 상태(ViewState): 카메라와 단계별 재생 속도. 구조가 아니므로 바뀌어도 version은 그대로다.
- 부품 형상은 기존 `cont.shape.Part`를 그대로 쓴다. 3D 메시와 CAD 내보내기는 `to_assembly()`로 이어진다.
- 설명용 단계 4D의 시간은 공정 단계 순서이며 물리 시간이 아니다. 치수는 `dimension_status`로 출처를 밝힌다.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from cont.shape import Assembly, Part

ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
DIMENSION_STATUS = ("illustrative", "user_input", "measured", "from_data")
TIME_AXES = ("process_stage",)          # 실제 시간 축은 계산·측정 결과가 연결될 때 더한다


class ObjectSpecError(ValueError):
    pass


def _check_id(kind: str, value: str) -> str:
    if not isinstance(value, str) or not ID_RE.match(value):
        raise ObjectSpecError(f"{kind} ID '{value}': 영문 소문자로 시작하고 소문자·숫자·밑줄, 점으로 나눈 이름이어야 합니다")
    return value


@dataclass(frozen=True)
class ObjPart:
    id: str
    part: Part                   # 이름·역할·z 범위·지름 (기존 형상 명세)
    layer: str = ""              # 같은 층 묶음 이름 (예: die_top)

    def __post_init__(self) -> None:
        _check_id("부품", self.id)
        if self.layer:
            _check_id("층", self.layer)


@dataclass(frozen=True)
class Pose:
    dz: float = 0.0              # 위로 이동 (mm)
    dx: float = 0.0              # 옆으로 이동 (mm)


@dataclass(frozen=True)
class Stage:
    id: str
    name: str
    poses: tuple[tuple[str, Pose], ...] = ()      # (부품 ID, 이 단계가 끝났을 때의 자세). 적지 않은 부품은 원래 자리

    def __post_init__(self) -> None:
        _check_id("단계", self.id)
        if not self.name.strip():
            raise ObjectSpecError(f"단계 {self.id}: 이름이 비어 있습니다")

    def pose_of(self, part_id: str) -> Pose:
        return dict(self.poses).get(part_id, Pose())


@dataclass(frozen=True)
class ObjectSpec:
    name: str
    parts: tuple[ObjPart, ...]
    stages: tuple[Stage, ...] = ()
    start: tuple[tuple[str, Pose], ...] = ()      # 첫 단계 전의 자세 (적지 않은 부품은 원래 자리)
    dimension_status: str = "illustrative"
    time_axis: str = "process_stage"
    parent_version: str = ""     # 이 명세를 고쳐 만든 이전 version (해시에는 넣지 않는다)

    def __post_init__(self) -> None:
        if not self.parts:
            raise ObjectSpecError("부품이 하나도 없습니다")
        ids = [p.id for p in self.parts]
        if len(set(ids)) != len(ids):
            raise ObjectSpecError(f"부품 ID가 겹칩니다: {sorted({i for i in ids if ids.count(i) > 1})}")
        sids = [s.id for s in self.stages]
        if len(set(sids)) != len(sids):
            raise ObjectSpecError("단계 ID가 겹칩니다")
        for pid, _ in self.start:
            if pid not in ids:
                raise ObjectSpecError(f"시작 자세가 없는 부품 '{pid}'를 가리킵니다")
        for s in self.stages:
            for pid, _ in s.poses:
                if pid not in ids:
                    raise ObjectSpecError(f"단계 {s.id}가 없는 부품 '{pid}'를 가리킵니다")
        if self.dimension_status not in DIMENSION_STATUS:
            raise ObjectSpecError(f"dimension_status는 {DIMENSION_STATUS} 중 하나여야 합니다")
        if self.time_axis not in TIME_AXES:
            raise ObjectSpecError(f"time_axis는 {TIME_AXES} 중 하나여야 합니다")

    # --- 읽기 ---
    def stage(self, ref: "int | str") -> Stage:
        """단계를 번호(1부터), 단계 ID, 이름으로 찾는다. "두 번째 단계"는 2, "정렬"은 이름이다. 모호하면 거절한다."""
        if isinstance(ref, bool):
            raise ObjectSpecError(f"단계를 가리키는 값이 잘못됐습니다: {ref!r}")
        if isinstance(ref, int):
            if not 1 <= ref <= len(self.stages):
                raise ObjectSpecError(f"{ref}번째 단계가 없습니다 (단계는 {len(self.stages)}개)")
            return self.stages[ref - 1]
        hits = [s for s in self.stages if ref in (s.id, s.name)]
        if len(hits) != 1:
            raise ObjectSpecError(f"단계 '{ref}'를 찾지 못했거나 둘 이상입니다 (있는 것: {[(s.id, s.name) for s in self.stages]})")
        return hits[0]

    def part(self, part_id: str) -> ObjPart:
        for p in self.parts:
            if p.id == part_id:
                return p
        raise ObjectSpecError(f"없는 부품 ID '{part_id}' (있는 것: {[p.id for p in self.parts]})")

    @property
    def part_ids(self) -> tuple[str, ...]:
        return tuple(p.id for p in self.parts)

    def to_dict(self) -> dict[str, Any]:
        """구조만 (parent_version 제외). version의 근거다."""
        return {
            "name": self.name, "dimension_status": self.dimension_status, "time_axis": self.time_axis,
            "parts": [{"id": p.id, "layer": p.layer, "name": p.part.name, "role": p.part.role, "z0": p.part.z0,
                       "z1": p.part.z1, "outer": p.part.outer, "inner": p.part.inner, "profile": p.part.profile,
                       "sweep": p.part.sweep} for p in self.parts],
            "start": [{"part": pid, "dz": ps.dz, "dx": ps.dx} for pid, ps in self.start],
            "stages": [{"id": s.id, "name": s.name,
                        "poses": [{"part": pid, "dz": ps.dz, "dx": ps.dx} for pid, ps in s.poses]} for s in self.stages],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], parent_version: str = "") -> "ObjectSpec":
        """to_dict()의 역. 저장한 명세를 다시 읽을 때 쓴다. 빠지거나 잘못된 항목은 ObjectSpecError로 거절한다."""
        try:
            parts = tuple(ObjPart(p["id"], Part(p["name"], p["role"], p["z0"], p["z1"], p["outer"], p.get("inner", 0.0),
                                                p.get("profile", "circle"), p.get("sweep", 360.0)), p.get("layer", "")) for p in d["parts"])
            start = tuple((x["part"], Pose(x["dz"], x["dx"])) for x in d.get("start", []))
            stages = tuple(Stage(s["id"], s["name"], tuple((x["part"], Pose(x["dz"], x["dx"])) for x in s["poses"])) for s in d.get("stages", []))
            return cls(d["name"], parts, stages, start, d.get("dimension_status", "illustrative"),
                       d.get("time_axis", "process_stage"), parent_version)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            if isinstance(e, ObjectSpecError):
                raise
            raise ObjectSpecError(f"명세를 읽을 수 없습니다: {type(e).__name__}: {e}") from None

    @property
    def version(self) -> str:
        body = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def to_assembly(self) -> Assembly:
        return Assembly(self.name, tuple(p.part for p in self.parts))

    # --- 고치기: 원본은 그대로 두고 새 명세를 만든다 ---
    def edit_part(self, part_id: str, **changes: Any) -> "ObjectSpec":
        old = self.part(part_id)
        allowed = {"name", "z0", "z1", "outer", "inner"}
        bad = set(changes) - allowed
        if bad:
            raise ObjectSpecError(f"고칠 수 없는 항목: {sorted(bad)} (고칠 수 있는 것: {sorted(allowed)})")
        new = replace(old, part=replace(old.part, **changes))
        parts = tuple(new if p.id == part_id else p for p in self.parts)
        return replace(self, parts=parts, parent_version=self.version, dimension_status="user_input")

    def edit_stage_pose(self, stage: "int | str", part_id: str, **changes: float) -> "ObjectSpec":
        """한 단계에서 한 부품의 끝 자세(dz, dx)만 고친다. 부품 모양과 다른 단계는 그대로다."""
        st = self.stage(stage)
        self.part(part_id)
        bad = set(changes) - {"dz", "dx"}
        if bad or not changes:
            raise ObjectSpecError(f"고칠 수 있는 자세 항목은 dz, dx뿐입니다: {sorted(bad) or '없음'}")
        poses = dict(st.poses)
        poses[part_id] = replace(poses.get(part_id, Pose()), **changes)
        new = replace(st, poses=tuple(sorted(poses.items())))
        stages = tuple(new if x.id == st.id else x for x in self.stages)
        return replace(self, stages=stages, parent_version=self.version, dimension_status="user_input")

    def changed_parts(self, other: "ObjectSpec") -> tuple[str, ...]:
        """self → other에서 달라진 부품 ID (없어졌거나 새로 생긴 것 포함)."""
        a, b = {p.id: p for p in self.parts}, {p.id: p for p in other.parts}
        return tuple(sorted(i for i in set(a) | set(b) if a.get(i) != b.get(i)))


@dataclass(frozen=True)
class ViewState:
    """카메라와 재생 속도. 구조가 아니므로 ObjectSpec.version과 무관하다."""
    azimuth: float = 35.0
    elevation: float = 25.0
    distance: float = 1.0
    stage_speed: tuple[tuple[str, float], ...] = ()    # (단계 ID, 배속). 적지 않은 단계는 1.0

    def __post_init__(self) -> None:
        if not -360 <= self.azimuth <= 360 or not -90 <= self.elevation <= 90:
            raise ObjectSpecError("카메라 각도가 범위를 벗어났습니다 (방위 ±360, 고도 ±90)")
        if self.distance <= 0:
            raise ObjectSpecError("카메라 거리는 0보다 커야 합니다")
        for sid, f in self.stage_speed:
            if not (isinstance(f, (int, float)) and 0.05 <= f <= 20):
                raise ObjectSpecError(f"단계 {sid}의 배속 {f}: 0.05~20 사이여야 합니다")

    def to_dict(self) -> dict[str, Any]:
        return {"azimuth": self.azimuth, "elevation": self.elevation, "distance": self.distance,
                "stage_speed": [[sid, f] for sid, f in self.stage_speed]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ViewState":
        try:
            return cls(float(d["azimuth"]), float(d["elevation"]), float(d["distance"]),
                       tuple((str(s), float(f)) for s, f in d.get("stage_speed", [])))
        except (KeyError, TypeError, ValueError) as e:
            raise ObjectSpecError(f"보기 상태를 읽을 수 없습니다: {e}") from None

    def speed_of(self, stage_id: str) -> float:
        return dict(self.stage_speed).get(stage_id, 1.0)

    def with_speed(self, spec: ObjectSpec, stage: "int | str", factor: float) -> "ViewState":
        """한 단계의 재생 속도만 바꾼다. stage는 번호(1부터)·ID·이름. 다른 단계와 구조는 그대로다."""
        stage_id = spec.stage(stage).id
        d = dict(self.stage_speed)
        d[stage_id] = factor
        return replace(self, stage_speed=tuple(sorted(d.items())))

    def with_camera(self, **kw: float) -> "ViewState":
        return replace(self, **kw)
