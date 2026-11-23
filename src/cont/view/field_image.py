"""물리 이미지 (C4 표현): 물리장(Field)을 그린 그림.

그림은 답변 묶음의 물리장에서만 나온다. 그릴 물리장이 없으면 그리지 않는다 (docs/generation.md).
값의 지위와 계산 방법을 그림 안에 적는다. 축대칭 단면은 축을 가운데 두고 좌우로 펼쳐 그린다.
"""
from __future__ import annotations

import html
from typing import Sequence

from cont.answer import STATUS_LABELS, VALIDATION_LABELS, Field, PhysicsAnswer

# 0(낮음) → 1(높음). 어두운 바탕에서 읽히도록 어두운 남색에서 밝은 노랑으로 간다.
# 한 가지 색 계열: 어두운 청회색 → 황동색 → 밝은 황동색. 값이 클수록 밝다
RAMP = ((0.0, (46, 54, 64)), (0.25, (98, 88, 68)), (0.5, (138, 106, 52)), (0.75, (217, 164, 65)), (1.0, (250, 232, 170)))
BELOW = (78, 106, 134)       # 0보다 작은 값 (당겨지는 곳). 띠와 다른 색(청회색)으로 따로 보인다
NO_IMAGE = '<p class="nofield">보일 물리장이 없습니다. 분포를 계산하지 않은 결과입니다.</p>'


def _edges(centres: Sequence[float]) -> list[float]:
    c = list(centres)
    if len(c) == 1:
        return [c[0] - 0.5, c[0] + 0.5]
    mid = [(a + b) / 2 for a, b in zip(c, c[1:])]
    return [c[0] - (mid[0] - c[0])] + mid + [c[-1] + (c[-1] - mid[-1])]


def colour(t: float) -> str:
    t = min(1.0, max(0.0, t))
    for (t0, c0), (t1, c1) in zip(RAMP, RAMP[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return "#%02x%02x%02x" % tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
    return "#%02x%02x%02x" % RAMP[-1][1]


def field_image(answer: PhysicsAnswer, key: str, *, mirrored: bool = True, lines: Sequence[tuple[float, str]] = (),
                marks: Sequence[tuple[float, float, float, str]] = (), width: int = 640, height: int = 430) -> str:
    """물리장 하나를 그린 SVG. lines: (높이, 이름) 가로 점선. marks: (r0, r1, 높이, 이름) 굵은 선 (예: 좌면).

    색 띠는 0에서 최댓값까지다. 0보다 작은 칸은 따로 정한 색으로 칠하고 범례에 적는다.
    """
    try:
        f: Field = answer.field(key)
    except KeyError:
        return NO_IMAGE
    rng = f.range()
    if rng is None:
        return NO_IMAGE
    top = max(rng[1], 0.0) or 1.0
    xe, ye = _edges(f.x), _edges(f.y)
    half = xe[-1]
    x_min = -half if mirrored else xe[0]
    pad_l, pad_r, pad_t, pad_b = 46, 16, 34, 74
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    scale = min(w / (half - x_min), h / (ye[-1] - ye[0]))
    ox = pad_l + (w - scale * (half - x_min)) / 2
    oy = pad_t + (h - scale * (ye[-1] - ye[0])) / 2

    def px(x: float) -> float:
        return ox + (x - x_min) * scale

    def py(y: float) -> float:
        return oy + (ye[-1] - y) * scale

    e = html.escape
    cells, below = [], False
    for j, row in enumerate(f.values):
        y0, hh = py(ye[j + 1]), (ye[j + 1] - ye[j]) * scale + 0.6
        for i, v in enumerate(row):
            if v is None:
                continue
            if v < 0:
                below = True
            fill = "#%02x%02x%02x" % BELOW if v < 0 else colour(v / top)
            ww = (xe[i + 1] - xe[i]) * scale + 0.6
            cells.append(f'<rect x="{px(xe[i]):.1f}" y="{y0:.1f}" width="{ww:.1f}" height="{hh:.1f}" fill="{fill}"/>')
            if mirrored:
                cells.append(f'<rect x="{px(-xe[i + 1]):.1f}" y="{y0:.1f}" width="{ww:.1f}" height="{hh:.1f}" fill="{fill}"/>')
    out = [f'<svg class="fieldimg" viewBox="0 0 {width} {height}" role="img" aria-label="{e(f.label)} 분포. 최대 {rng[1]:,.0f} {e(f.unit)}">',
           f'<text x="{pad_l}" y="18" class="ft">{e(f.label)} <tspan class="fu">({e(f.unit)})</tspan></text>', *cells]
    if mirrored and xe[0] > 0:                              # 가운데 빈 곳: 계산에 넣지 않은 볼트 자리
        out.append(f'<rect x="{px(-xe[0]):.1f}" y="{py(ye[-1]):.1f}" width="{2 * xe[0] * scale:.1f}" height="{(ye[-1] - ye[0]) * scale:.1f}" class="fhole"/>')
        out.append(f'<line x1="{px(0):.1f}" y1="{py(ye[-1]) - 8:.1f}" x2="{px(0):.1f}" y2="{py(ye[0]) + 8:.1f}" class="faxis"/>')
        out.append(f'<text x="{px(0):.1f}" y="{py((ye[0] + ye[-1]) / 2):.1f}" class="fn" text-anchor="middle" transform="rotate(-90 {px(0):.1f} {py((ye[0] + ye[-1]) / 2):.1f})" dy="4">볼트 자리 (계산에 넣지 않음)</text>')
    for y, name in lines:
        out.append(f'<line x1="{px(x_min):.1f}" y1="{py(y):.1f}" x2="{px(half):.1f}" y2="{py(y):.1f}" class="fline"/>')
        out.append(f'<text x="{px(half) - 4:.1f}" y="{py(y) - 5:.1f}" class="fn" text-anchor="end">{e(name)}</text>')
    for r0, r1, y, name in marks:
        for sign in ((1, -1) if mirrored else (1,)):
            out.append(f'<line x1="{px(sign * r0):.1f}" y1="{py(y):.1f}" x2="{px(sign * r1):.1f}" y2="{py(y):.1f}" class="fmark"/>')
        above = y >= (ye[0] + ye[-1]) / 2
        out.append(f'<text x="{px(r1) + 6:.1f}" y="{py(y) + (-7 if above else 15):.1f}" class="fn">{e(name)}</text>')
    out.append(f'<text x="{px(x_min) - 6:.1f}" y="{py(ye[-1]) + 4:.1f}" class="fn" text-anchor="end">{round(ye[-1], 2):g}</text>')
    out.append(f'<text x="{px(x_min) - 6:.1f}" y="{py(ye[0]) + 4:.1f}" class="fn" text-anchor="end">{round(ye[0], 2):g}</text>')
    out.append(f'<text x="{px(x_min) - 6:.1f}" y="{py((ye[0] + ye[-1]) / 2) + 4:.1f}" class="fn" text-anchor="end">z {e(f.axis_unit)}</text>')
    by = height - pad_b + 26
    bw = 220
    steps = 44
    for s in range(steps):
        out.append(f'<rect x="{pad_l + bw * s / steps:.1f}" y="{by}" width="{bw / steps + 0.6:.1f}" height="9" fill="{colour((s + 0.5) / steps)}"/>')
    out.append(f'<text x="{pad_l}" y="{by + 24}" class="fn">0</text><text x="{pad_l + bw}" y="{by + 24}" class="fn" text-anchor="end">{top:,.0f} {e(f.unit)}</text>')
    if below:
        out.append(f'<rect x="{pad_l + bw + 22}" y="{by}" width="14" height="9" fill="#%02x%02x%02x"/>' % BELOW)
        out.append(f'<text x="{pad_l + bw + 42}" y="{by + 9}" class="fn">0보다 작은 곳 (가장 작은 값 {rng[0]:,.0f} {e(f.unit)})</text>')
    status = STATUS_LABELS[answer.field_status(key)]
    out.append(f'<text x="{pad_l}" y="{height - 8}" class="fs">{e(status)} · {e(answer.method)} · {e(VALIDATION_LABELS[answer.validation])}</text>')
    out.append("</svg>")
    return "".join(out)


FIELD_CSS = """.fieldimg{width:100%;height:auto;display:block}.fieldimg .ft{font-size:14px;font-weight:600;fill:currentColor}.fieldimg .fu{font-weight:400;opacity:.7}
.fieldimg .fn{font-size:11.5px;fill:currentColor;opacity:.78}.fieldimg .fs{font-size:12px;fill:currentColor;font-weight:600}
.fieldimg .fhole{fill:currentColor;opacity:.07}.fieldimg .faxis{stroke:currentColor;stroke-width:1;stroke-dasharray:8 3 2 3;opacity:.5}
.fieldimg .fline{stroke:currentColor;stroke-width:1;stroke-dasharray:4 4;opacity:.6}.fieldimg .fmark{stroke:currentColor;stroke-width:4;stroke-linecap:butt}
.nofield{font-size:14px;opacity:.8;padding:24px 0}"""
