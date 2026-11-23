"""물리 이미지 (C4 표현): 물리장(Field)을 그린 그림.

그림은 답변 묶음의 물리장에서만 나온다. 그릴 물리장이 없으면 그리지 않는다 (docs/generation.md).
값의 지위와 계산 방법을 그림 안에 적는다. 축대칭 단면은 축을 가운데 두고 좌우로 펼쳐 그린다.
"""
from __future__ import annotations

import base64
import html
import struct
import zlib
from typing import Sequence

import numpy as np

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


RASTER_SCALE = 1.0           # 그림 한 칸의 화소 수 (SVG 단위당). 부드럽게 늘려 보이므로 작게 잡는다


def _png(rgba: np.ndarray) -> bytes:
    """RGBA 배열(높이, 너비, 4)을 PNG로 (표준 라이브러리 zlib만 사용)."""
    h, w, _ = rgba.shape
    a = rgba.astype(np.int16)
    sub = a.copy()
    sub[:, 1:, :] = a[:, 1:, :] - a[:, :-1, :]                    # Sub 필터: 완만한 색 변화가 잘 압축된다
    raw = np.hstack([np.ones((h, 1), np.uint8), (sub % 256).astype(np.uint8).reshape(h, w * 4)]).tobytes()

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _two(c: np.ndarray, v: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    if len(c) >= 2:
        return c, v
    return np.array([c[0] - 0.5, c[0] + 0.5]), np.repeat(v, 2, axis=axis)


def raster(f: Field, top: float, ax: np.ndarray, ys: np.ndarray, hole: float = 0.0) -> np.ndarray:
    """물리장을 칸 모양이 아니라 부드러운 색으로 그린 RGBA 화소. 칸이 없는 곳(None)은 투명하다."""
    fx, fy = np.asarray(f.x, float), np.asarray(f.y, float)
    vals = np.array([[np.nan if v is None else v for v in row] for row in f.values], float)
    fx, vals = _two(fx, vals, 1)
    fy, vals = _two(fy, vals, 0)
    ix = np.clip(np.searchsorted(fx, ax) - 1, 0, len(fx) - 2)[None, :]
    iy = np.clip(np.searchsorted(fy, ys) - 1, 0, len(fy) - 2)[:, None]
    tx = np.clip((ax - fx[ix[0]]) / (fx[ix[0] + 1] - fx[ix[0]]), 0, 1)[None, :]
    ty = np.clip((ys - fy[iy[:, 0]]) / (fy[iy[:, 0] + 1] - fy[iy[:, 0]]), 0, 1)[:, None]
    num = np.zeros((len(ys), len(ax))); den = np.zeros_like(num)
    for dy, wy in ((0, 1 - ty), (1, ty)):
        for dx, wx in ((0, 1 - tx), (1, tx)):
            v = vals[iy + dy, ix + dx]
            w = wy * wx * ~np.isnan(v)
            num += w * np.nan_to_num(v); den += w
    v = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
    near = vals[np.clip(np.rint(iy + ty).astype(int), 0, len(fy) - 1), np.clip(np.rint(ix + tx).astype(int), 0, len(fx) - 1)]
    keep = (den > 0) & ~np.isnan(near) & (ax[None, :] >= hole)
    ramp_t, ramp_c = [r[0] for r in RAMP], np.array([r[1] for r in RAMP], float)
    u = np.clip(v / top, 0, 1)
    rgb = np.stack([np.interp(u, ramp_t, ramp_c[:, k]) for k in range(3)], axis=-1)
    rgb = np.where((v < 0)[..., None], np.array(BELOW, float), rgb)
    return np.dstack([np.rint(rgb), np.where(keep, 255, 0)]).astype(np.uint8)


def field_image(answer: PhysicsAnswer, key: str, *, mirrored: bool = True, lines: Sequence[tuple[float, str]] = (),
                marks: Sequence[tuple[float, float, float, str]] = (), width: int = 560, height: int = 360) -> str:
    """물리장 하나를 그린 SVG. lines: (높이, 이름) 가로 점선. marks: (r0, r1, 높이, 이름) 굵은 선 (예: 좌면).

    색 띠는 0에서 최댓값까지다. 0보다 작은 곳은 따로 정한 색으로 칠하고 범례에 적는다.
    카드에서는 그림 영역만 보이도록 data-card에 잘라 볼 범위를 적는다.
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
    pad_l, pad_r, pad_t, pad_b = 44, 14, 36, 66
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    scale = min(w / (half - x_min), h / (ye[-1] - ye[0]))
    pw, ph = scale * (half - x_min), scale * (ye[-1] - ye[0])
    ox, oy = pad_l + (w - pw) / 2, pad_t + (h - ph) / 2

    def px(x: float) -> float:
        return ox + (x - x_min) * scale

    def py(y: float) -> float:
        return oy + (ye[-1] - y) * scale

    nw, nh = max(2, round(pw * RASTER_SCALE)), max(2, round(ph * RASTER_SCALE))
    xs = np.linspace(x_min, half, nw)
    pix = raster(f, top, np.abs(xs) if mirrored else xs, np.linspace(ye[-1], ye[0], nh), hole=xe[0] if mirrored else 0.0)
    below = bool((pix[..., 3] > 0).any() and any(v is not None and v < 0 for row in f.values for v in row))
    e = html.escape
    out = [f'<svg class="fieldimg" viewBox="0 0 {width} {height}" data-card="{ox - 4:.0f} {oy - 4:.0f} {pw + 8:.0f} {ph + 8:.0f}" role="img" aria-label="{e(f.label)} 분포. 최대 {rng[1]:,.0f} {e(f.unit)}">',
           '<defs><linearGradient id="fr" x1="0" x2="1" y1="0" y2="0">' + "".join(f'<stop offset="{t0:g}" stop-color="{colour(t0)}"/>' for t0, _ in RAMP) + '</linearGradient></defs>',
           f'<text x="{pad_l}" y="20" class="ft">{e(f.label)} <tspan class="fu">({e(f.unit)})</tspan></text>',
           f'<rect x="{ox:.1f}" y="{oy:.1f}" width="{pw:.1f}" height="{ph:.1f}" rx="6" class="fbg"/>',
           f'<image href="data:image/png;base64,{base64.b64encode(_png(pix)).decode()}" x="{ox:.1f}" y="{oy:.1f}" width="{pw:.1f}" height="{ph:.1f}" preserveAspectRatio="none"/>']
    if mirrored and xe[0] > 0:                              # 가운데 빈 곳: 계산에 넣지 않은 볼트 자리
        out.append(f'<line x1="{px(0):.1f}" y1="{py(ye[-1]) - 8:.1f}" x2="{px(0):.1f}" y2="{py(ye[-1]) + 10:.1f}" class="faxis"/><line x1="{px(0):.1f}" y1="{py(ye[0]) - 10:.1f}" x2="{px(0):.1f}" y2="{py(ye[0]) + 8:.1f}" class="faxis"/>')
        out.append(f'<text x="{px(0):.1f}" y="{py((ye[0] + ye[-1]) / 2):.1f}" class="fn" text-anchor="middle" transform="rotate(-90 {px(0):.1f} {py((ye[0] + ye[-1]) / 2):.1f})" dy="4">볼트 자리 (계산에 넣지 않음)</text>')
    for y, name in lines:
        out.append(f'<line x1="{px(x_min):.1f}" y1="{py(y):.1f}" x2="{px(half):.1f}" y2="{py(y):.1f}" class="fline"/>')
        out.append(f'<text x="{px(half) - 6:.1f}" y="{py(y) - 6:.1f}" class="fn fl" text-anchor="end">{e(name)}</text>')
    for r0, r1, y, name in marks:
        for sign in ((1, -1) if mirrored else (1,)):
            out.append(f'<line x1="{px(sign * r0):.1f}" y1="{py(y):.1f}" x2="{px(sign * r1):.1f}" y2="{py(y):.1f}" class="fmark"/>')
        above = y >= (ye[0] + ye[-1]) / 2
        out.append(f'<text x="{px(r1) + 6:.1f}" y="{py(y) + (-8 if above else 16):.1f}" class="fn fl">{e(name)}</text>')
    out.append(f'<text x="{px(x_min) - 8:.1f}" y="{py(ye[-1]) + 4:.1f}" class="fn" text-anchor="end">{round(ye[-1], 2):g}</text>')
    out.append(f'<text x="{px(x_min) - 8:.1f}" y="{py(ye[0]) + 4:.1f}" class="fn" text-anchor="end">{round(ye[0], 2):g}</text>')
    out.append(f'<text x="{px(x_min) - 8:.1f}" y="{py((ye[0] + ye[-1]) / 2) + 4:.1f}" class="fn" text-anchor="end">z {e(f.axis_unit)}</text>')
    by, bw = height - pad_b + 20, 240
    out.append(f'<rect x="{pad_l}" y="{by}" width="{bw}" height="10" rx="5" fill="url(#fr)"/>')
    out.append(f'<text x="{pad_l}" y="{by + 26}" class="fn">0</text><text x="{pad_l + bw}" y="{by + 26}" class="fn" text-anchor="end">{top:,.0f} {e(f.unit)}</text>')
    if below:
        out.append(f'<rect x="{pad_l + bw + 24}" y="{by}" width="16" height="10" rx="3" fill="#%02x%02x%02x"/>' % BELOW)
        out.append(f'<text x="{pad_l + bw + 46}" y="{by + 10}" class="fn">0보다 작은 곳 (가장 작은 값 {rng[0]:,.0f} {e(f.unit)})</text>')
    status = STATUS_LABELS[answer.field_status(key)]
    out.append(f'<text x="{pad_l}" y="{height - 6}" class="fs">{e(status)} · {e(answer.method)} · {e(VALIDATION_LABELS[answer.validation])}</text>')
    out.append("</svg>")
    return "".join(out)


FIELD_CSS = """.fieldimg{width:100%;height:auto;display:block}.fieldimg .ft{font-size:14px;font-weight:600;fill:currentColor}.fieldimg .fu{font-weight:400;opacity:.7}
.fieldimg .fn{font-size:11.5px;fill:currentColor;opacity:.78}.fieldimg .fs{font-size:11.5px;fill:currentColor;font-weight:600}
.fieldimg .fbg{fill:currentColor;opacity:.06}.fieldimg image{image-rendering:auto}.fieldimg .faxis{stroke:currentColor;stroke-width:1;stroke-dasharray:8 3 2 3;opacity:.5}
.fieldimg .fline{stroke:currentColor;stroke-width:1;stroke-dasharray:4 4;opacity:.6}.fieldimg .fmark{stroke:currentColor;stroke-width:4;stroke-linecap:butt}
.nofield{font-size:14px;opacity:.8;padding:24px 0}"""
