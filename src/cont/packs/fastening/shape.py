"""볼트 조인트의 형상 명세: 조인트 치수와 표준 데이터에서 볼트·너트·판 두 장을 만든다.

z = 0 은 두 판이 맞닿는 면이다. 머리 쪽이 위(+z). 나사산과 모따기는 그리지 않는다 (볼트 축부는 호칭 지름의 원기둥).
판은 체결부 대체 바깥지름 D_A의 원판으로 그린다. 실제 판의 외형이 아니다.
"""
from __future__ import annotations

from cont.packs.fastening import standards, vdi2230
from cont.packs.fastening.joint import BoltedJoint
from cont.shape import Assembly, Part


def bolt_length(joint: BoltedJoint) -> float:
    """머리 아래 길이: 체결 길이 + 너트 높이 + 너트 밖으로 나오는 나사 길이. 표준 길이 단계로 올리지는 않는다."""
    return joint.clamp_length + joint.thread.nut_height + standards.shape_constant("thread_protrusion_pitches") * joint.p


def joint_shape(joint: BoltedJoint) -> Assembly:
    t = joint.thread
    top, bottom = joint.plate_head.thickness, -joint.plate_nut.thickness
    return Assembly(f"{joint.size} 볼트 조인트", (
        Part("볼트 머리", "bolt_head", top, top + t.head_height, t.across_flats, profile="hexagon"),
        Part("볼트 축", "bolt_shank", top - bolt_length(joint), top, joint.d),
        Part("머리 쪽 판", "plate_head", 0.0, top, joint.outer_diameter, joint.hole),
        Part("너트 쪽 판", "plate_nut", bottom, 0.0, joint.outer_diameter, joint.hole),
        Part("너트", "nut", bottom - t.nut_height, bottom, t.across_flats, joint.d, profile="hexagon"),
    ))


def compression_zone(joint: BoltedJoint) -> list[tuple[float, float]]:
    """판이 눌리는 영역의 단면 (반지름, 높이): VDI 2230의 변형 원뿔과 슬리브. 계산 모형의 모양이며 해석(FEM)으로 얻은 응력 분포가 아니다.

    머리 좌면과 너트 좌면에서 원뿔이 벌어지며 체결 길이의 가운데에서 만난다. 체결부 바깥지름에 닿으면 그 뒤로는 원통(슬리브)이다.
    """
    top, bottom = joint.plate_head.thickness, -joint.plate_nut.thickness
    rw, rh, ra = joint.bearing_diameter / 2, joint.hole / 2, joint.outer_diameter / 2
    half = joint.clamp_length / 2
    if ra <= rw:                                             # 원뿔이 생기지 않고 전체가 슬리브
        return [(rh, top), (ra, top), (ra, bottom), (rh, bottom)]
    tan_phi = vdi2230.cone_angle_tan(joint.clamp_length, joint.bearing_diameter, joint.outer_diameter)
    reach = min(half, (ra - rw) / tan_phi)                   # 원뿔이 이어지는 깊이
    r_end = rw + reach * tan_phi
    pts = [(rh, top), (rw, top), (r_end, top - reach)]
    if reach < half:
        pts.append((r_end, bottom + reach))
    pts += [(rw, bottom), (rh, bottom)]
    return pts
