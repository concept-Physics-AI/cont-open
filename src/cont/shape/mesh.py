"""형상 명세 → 삼각형 메시 (화면용).

부품 하나는 "바깥 윤곽과 안쪽 원 사이를 z0~z1로 세운 고리"다. 속이 찬 부품은 안쪽 원 대신 축 위의 점을 쓴다.
면의 방향은 모두 바깥(재료 밖)을 향한다. 닫힌 메시인지와 부피는 테스트에서 수식과 대조한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cont.shape.spec import Assembly, Part

SEGMENTS = 36      # 한 바퀴를 나누는 수. 육각 꼭짓점이 정확히 잡히려면 12의 배수여야 한다


@dataclass(frozen=True)
class Mesh:
    vertices: np.ndarray        # (N, 3)
    faces: np.ndarray           # (M, 3) 꼭짓점 번호, 바깥에서 볼 때 반시계


def _outer_radius(part: Part, theta: float) -> float:
    if part.profile == "circle":
        return part.outer / 2
    phi = (theta + math.pi / 6) % (math.pi / 3) - math.pi / 6       # 가장 가까운 평면의 법선과의 각 (평면 하나가 theta=0을 향한다)
    return (part.outer / 2) / math.cos(phi)


def part_mesh(part: Part, segments: int = SEGMENTS) -> Mesh:
    if segments % 12:
        raise ValueError("segments must be a multiple of 12")
    full = part.sweep >= 360.0
    steps = segments if full else max(3, round(segments * part.sweep / 360.0))
    cols = steps if full else steps + 1                 # 다 채우면 마지막 열이 첫 열과 같다
    angles = [math.radians(part.sweep) * i / steps for i in range(cols)]
    solid = part.inner == 0
    v: list[tuple[float, float, float]] = []; f: list[tuple[int, int, int]] = []

    def add(x: float, y: float, z: float) -> int:
        v.append((x, y, z)); return len(v) - 1

    ob = [add(_outer_radius(part, a) * math.cos(a), _outer_radius(part, a) * math.sin(a), part.z0) for a in angles]
    ot = [add(_outer_radius(part, a) * math.cos(a), _outer_radius(part, a) * math.sin(a), part.z1) for a in angles]
    if solid:
        cb, ct = add(0, 0, part.z0), add(0, 0, part.z1)
        ib, it = [cb] * cols, [ct] * cols
    else:
        r = part.inner / 2
        ib = [add(r * math.cos(a), r * math.sin(a), part.z0) for a in angles]
        it = [add(r * math.cos(a), r * math.sin(a), part.z1) for a in angles]

    def quad(a: int, b: int, c: int, d: int) -> None:   # a→b→c→d 가 바깥에서 볼 때 반시계. 같은 점이 겹치면 삼각형 하나만 낸다
        for tri in ((a, b, c), (a, c, d)):
            if len(set(tri)) == 3:
                f.append(tri)

    for i in range(steps):
        j = (i + 1) % cols
        quad(ob[i], ob[j], ot[j], ot[i])                # 바깥 벽
        quad(it[i], ot[i], ot[j], it[j])                # 윗면
        quad(ib[i], ib[j], ob[j], ob[i])                # 아랫면
        if not solid:
            quad(ib[j], ib[i], it[i], it[j])            # 구멍 벽 (법선이 축을 향한다)
    if not full:
        quad(ib[0], ob[0], ot[0], it[0])                # 잘라 낸 면 (시작)
        quad(ob[-1], ib[-1], it[-1], ot[-1])            # 잘라 낸 면 (끝)
    return Mesh(np.array(v, float), np.array(f, int))


def volume(mesh: Mesh) -> float:
    """닫힌 메시의 부피 (원점과 각 면이 이루는 사면체의 부호 있는 부피의 합)."""
    a, b, c = (mesh.vertices[mesh.faces[:, k]] for k in range(3))
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def assembly_mesh(assembly: Assembly, segments: int = SEGMENTS) -> list[tuple[Part, Mesh]]:
    return [(p, part_mesh(p, segments)) for p in assembly.parts]


def revolve(profile: list[tuple[float, float]], sweep: float = 360.0, segments: int = SEGMENTS) -> Mesh:
    """(반지름, 높이) 평면의 볼록 다각형을 축 둘레로 돌린 입체. sweep이 360보다 작으면 잘린 두 면을 막는다. 면은 바깥을 향한다."""
    if len(profile) < 3:
        raise ValueError("profile needs at least three points")
    if any(r < 0 for r, _ in profile):
        raise ValueError("radius must not be negative")
    full = sweep >= 360.0
    steps = segments if full else max(3, round(segments * sweep / 360.0))
    cols = steps if full else steps + 1
    angles = [math.radians(min(sweep, 360.0)) * i / steps for i in range(cols)]
    n = len(profile)
    v = [(r * math.cos(a), r * math.sin(a), z) for a in angles for r, z in profile]
    f: list[tuple[int, int, int]] = []
    for i in range(steps):
        j = (i + 1) % cols
        for k in range(n):
            m = (k + 1) % n
            a, b, c, d = i * n + k, i * n + m, j * n + m, j * n + k
            for tri in ((a, b, c), (a, c, d)):
                if len({v[t] for t in tri}) == 3:
                    f.append(tri)
    if not full:
        last = (cols - 1) * n
        for k in range(1, n - 1):
            f.append((0, k + 1, k)); f.append((last, last + k, last + k + 1))
    mesh = Mesh(np.array(v, float), np.array(f, int))
    return mesh if volume(mesh) >= 0 else Mesh(mesh.vertices, mesh.faces[:, ::-1].copy())
