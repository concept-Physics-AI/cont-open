"""설명용 본딩 층 구조 (첫 인수 대상). 치수는 설명용 값이며 실측이 아니다."""
from __future__ import annotations

from cont.shape import Part

from .spec import ObjectSpec, ObjPart, Pose, Stage


def hybrid_bonding_stack(gap: float = 2.0, offset: float = 1.0) -> ObjectSpec:
    """아래 웨이퍼 + 아래 유전층 / 위 유전층 + 위 다이를 z로 쌓은 구조.

    gap: 접근 전 두 면 사이 간격(mm), offset: 정렬 전 옆으로 어긋난 거리(mm). 둘 다 설명 그림의 값이다.
    """
    if gap <= 0:
        raise ValueError("gap must be positive")
    parts = (
        ObjPart("wafer.si", Part("아래 웨이퍼(실리콘)", "substrate", 0.0, 1.0, 20.0), "wafer"),
        ObjPart("wafer.dielectric", Part("아래 유전층", "dielectric", 1.0, 1.2, 20.0), "wafer"),
        ObjPart("die.dielectric", Part("위 유전층", "dielectric", 1.2, 1.4, 14.0), "die"),
        ObjPart("die.si", Part("위 다이(실리콘)", "substrate", 1.4, 2.0, 14.0), "die"),
    )
    top = ("die.dielectric", "die.si")
    start = tuple((i, Pose(dz=gap * 2.0, dx=offset)) for i in top)
    stages = (
        Stage("approach", "접근", tuple((i, Pose(dz=gap, dx=offset)) for i in top)),
        Stage("align", "정렬", tuple((i, Pose(dz=gap, dx=0.0)) for i in top)),
        Stage("contact", "접촉", tuple((i, Pose(dz=0.0, dx=0.0)) for i in top)),
    )
    return ObjectSpec("하이브리드 본딩 층 구조", parts, stages, start=start, dimension_status="illustrative")
