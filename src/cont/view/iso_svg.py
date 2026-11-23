"""3D 형상을 그림(SVG) 한 장으로: 삼각형을 비스듬히 내려다본 모습으로 옮겨 멀리 있는 것부터 칠한다.

화면의 3D 보기(WebGL)와 같은 각도, 같은 밝기 식을 쓴다. 목록의 카드처럼 3D를 여러 장 늘어놓아야 하는 곳에서 쓴다.
볼트의 색은 use(등가응력 ÷ 항복강도)를 주면 회색에서 황동색으로 간다. hidden=True이면 판을 비쳐 보이게 그린다.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

YAW, PITCH = -0.785, 0.36
LIGHT = (0.35, 0.6, 0.72)
COLORS = {"bolt": (174, 182, 191), "plate_head": (74, 84, 95), "plate_nut": (61, 70, 80), "zone": (217, 164, 65)}
RAMP = ((0.0, (168, 178, 188)), (0.5, (184, 153, 92)), (0.8, (217, 164, 65)), (1.0, (245, 204, 112)))
BOLT = ("bolt_head", "bolt_shank", "nut")


def ramp(u: float) -> tuple[int, int, int]:
    u = max(0.0, min(1.0, u))
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if u <= t1:
            k = (u - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
    return RAMP[-1][1]


def iso_svg(viewer: Mapping[str, Any], width: int = 320, height: int = 260, hidden: bool = False, use: float | None = None,
            label: str = "3D 형상", background: str | None = "#14181D") -> str:
    cy, sy, cp, sp = math.cos(YAW), math.sin(YAW), math.cos(PITCH), math.sin(PITCH)
    cx0, cy0, cz0 = viewer["center"]; scale = 1.0 / viewer["radius"]
    ln = math.sqrt(sum(v * v for v in LIGHT)); L = tuple(v / ln for v in LIGHT)

    def rot(x: float, y: float, z: float) -> tuple[float, float, float]:
        return cy * x - sy * y, sp * sy * x + sp * cy * y + cp * z, -cp * sy * x - cp * cy * y + sp * z

    half = min(width, height) / 2 * 0.94
    solid: list[tuple[float, str]] = []; glass: list[tuple[float, str]] = []
    for part in viewer["parts"]:
        role, tri = part["role"], part["tri"]
        plate = role.startswith("plate")
        if role == "zone" and not hidden:
            continue
        base = ramp(use) if (use is not None and role in BOLT) else COLORS.get("bolt" if role in BOLT else role, COLORS["bolt"])
        see_through = hidden and (plate or role == "zone")
        for i in range(0, len(tri), 9):
            p = [rot((tri[i + k] - cx0) * scale, (tri[i + k + 1] - cy0) * scale, (tri[i + k + 2] - cz0) * scale) for k in (0, 3, 6)]
            ux, uy, uz = (p[1][j] - p[0][j] for j in range(3)); vx, vy, vz = (p[2][j] - p[0][j] for j in range(3))
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            n = math.sqrt(nx * nx + ny * ny + nz * nz)
            if n == 0 or (nz <= 0 and not see_through):
                continue                                    # 뒤를 보는 면은 그리지 않는다
            lit = 0.28 + 0.72 * max((nx * L[0] + ny * L[1] + nz * L[2]) / n, 0.0)
            col = "#%02x%02x%02x" % tuple(min(255, round(c * lit)) for c in base)
            d = "M" + "L".join(f"{width / 2 + q[0] * half:.1f},{height / 2 - q[1] * half:.1f}" for q in p) + "Z"
            (glass if see_through else solid).append(((p[0][2] + p[1][2] + p[2][2]) / 3, f'<path d="{d}" fill="{col}"/>'))
    solid.sort(key=lambda t: t[0]); glass.sort(key=lambda t: t[0])
    bg = f'<rect width="{width}" height="{height}" fill="{background}"/>' if background else ""
    over = f'<g opacity="0.2">{"".join(s for _, s in glass)}</g>' if glass else ""
    return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{label}" shape-rendering="crispEdges">{bg}'
            f'{"".join(s for _, s in solid)}{over}</svg>')
