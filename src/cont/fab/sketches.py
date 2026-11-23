"""엔진이 아직 없는 표현 유형의 개념도 (선으로 그린 예시 그림).

이 그림은 계산 결과가 아니다. 그 유형이 어떤 모양의 결과를 내는지 알려 주는 설명용 그림이며,
그림 안에 "예시 그림 · 실제 결과 아님"이라고 적는다. 값이나 눈금 숫자는 넣지 않는다.
설비 사진이나 실제 결과 그림이 생기면 이 자리를 바꾼다.
"""
from __future__ import annotations

import html
import math
from typing import Callable, Sequence

W, H = 320, 190
NOTE = "예시 그림 · 실제 결과 아님"


def _t(x: float, y: float, s: str, cls: str = "t", anchor: str = "middle") -> str:
    return f'<text x="{x:g}" y="{y:g}" class="{cls}" text-anchor="{anchor}">{html.escape(s)}</text>'


def _l(x1: float, y1: float, x2: float, y2: float, cls: str = "l") -> str:
    return f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{cls}"/>'


def _p(d: str, cls: str = "l") -> str:
    return f'<path d="{d}" class="{cls}"/>'


def _r(x: float, y: float, w: float, h: float, cls: str = "l", rx: float = 4) -> str:
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" class="{cls}"/>'


def _c(cx: float, cy: float, r: float, cls: str = "l") -> str:
    return f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" class="{cls}"/>'


def _arrow(x1: float, y1: float, x2: float, y2: float, cls: str = "l a", size: float = 6) -> str:
    ang = math.atan2(y2 - y1, x2 - x1)
    hx = [x2 - size * math.cos(ang - 0.45), x2 - size * math.cos(ang + 0.45)]
    hy = [y2 - size * math.sin(ang - 0.45), y2 - size * math.sin(ang + 0.45)]
    return _l(x1, y1, x2 - size * 0.6 * math.cos(ang), y2 - size * 0.6 * math.sin(ang), cls) + f'<polygon points="{x2:g},{y2:g} {hx[0]:.1f},{hy[0]:.1f} {hx[1]:.1f},{hy[1]:.1f}" class="ah"/>'


def _plate(x: float, y: float, w: float, h: float, hole: bool = True, cls: str = "l") -> str:
    out = _r(x, y, w, h, cls, 6)
    return out + (_c(x + w / 2, y + h / 2, min(w, h) * 0.12, cls) if hole else "")


def _axes(x: float, y: float, w: float, h: float, xl: str = "", yl: str = "") -> str:
    return (_l(x, y + h, x + w, y + h) + _l(x, y, x, y + h) + (_t(x + w, y + h + 14, xl, "t", "end") if xl else "") + (_t(x + 4, y - 4, yl, "t", "start") if yl else ""))


def frame(inner: str, label: str) -> str:
    return (f'<svg class="sk" viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(label)} 개념도 ({NOTE})">'
            f'{inner}<text x="10" y="{H - 8}" class="cap" text-anchor="start">{NOTE}</text></svg>')


# ---------------- 이미지: 분포 ----------------
def contour() -> str:
    cx, cy = 160, 90
    rings = "".join(_p(f'M{cx - 20 - k * 16},{cy} a{20 + k * 16},{14 + k * 11} 0 1 0 {2 * (20 + k * 16)},0 a{20 + k * 16},{14 + k * 11} 0 1 0 {-2 * (20 + k * 16)},0', "l d a" if k % 2 else "l a") for k in range(1, 5))
    return _r(50, 28, 220, 124, "l f", 8) + rings + _c(cx, cy, 8, "l") + _t(cx, 24, "같은 값을 잇는 선", "t")


def deform() -> str:
    return (_r(60, 60, 200, 60, "l d", 4) + _p("M60,60 Q160,40 260,60 L260,128 Q160,108 60,128 Z", "l a fa2") + _arrow(160, 150, 160, 130) + _t(160, 168, "하중", "t") + _t(262, 56, "원래", "t", "start") + _t(262, 132, "변형 후", "t", "start"))


def hotspot() -> str:
    return (_plate(60, 36, 200, 118, True) + '<ellipse cx="218" cy="62" rx="30" ry="22" class="fa"/>' + _p("M188,62 a30,22 0 1 0 60,0 a30,22 0 1 0 -60,0", "l a d") + _t(218, 108, "집중 영역", "t") + _l(218, 86, 218, 98, "l a"))


def diff() -> str:
    out = ""
    for i, (x, lab) in enumerate(((20, "기준"), (118, "현재"), (216, "차이"))):
        out += _plate(x, 56, 84, 70, True) + _t(x + 42, 146, lab, "t")
        if i == 2:
            out += '<ellipse cx="258" cy="80" rx="16" ry="12" class="fa"/>'
    return out + _t(106, 96, "−", "tb") + _t(204, 96, "=", "tb")


def photo() -> str:
    return (_r(40, 26, 240, 132, "l f", 8) + _r(90, 70, 90, 56, "l", 4) + _c(205, 98, 22, "l") + _l(180, 98, 183, 98) + _c(110, 90, 5, "l a fa") + _c(150, 108, 5, "l a fa")
            + _p("M184,92 a22,22 0 0 1 0,12", "l a d") + '<ellipse cx="205" cy="98" rx="30" ry="26" class="l a d" fill="none"/>' + _t(110, 80, "측정 위치", "t") + _t(205, 140, "계산한 영역", "t") + _t(160, 20, "현장 사진", "t"))


def layout() -> str:
    out = _r(28, 26, 264, 134, "l f", 6) + _r(52, 50, 70, 40, "l") + _r(150, 50, 60, 40, "l") + _r(52, 110, 110, 32, "l") + _r(220, 100, 52, 44, "l")
    for x, y, c in ((60, 58, "a fa"), (190, 58, "a"), (110, 124, "a fa"), (250, 112, "a")):
        out += _c(x, y, 6, "l " + c)
    return out + _t(160, 20, "배치도 위 센서 상태", "t")


def uncertain() -> str:
    hatch = "".join(_l(130 + k * 12, 52, 110 + k * 12, 124, "l a h") for k in range(7))
    return _plate(60, 36, 200, 118, True) + '<clipPath id="uq"><rect x="110" y="60" width="100" height="70"/></clipPath>' + f'<g clip-path="url(#uq)">{hatch}</g>' + _r(110, 60, 100, 70, "l a d", 4) + _t(160, 148, "오차가 큰 영역", "t")


# ---------------- 이미지: 단면·벡터 ----------------
def multicut() -> str:
    out = _p("M40,40 L130,40 L160,60 L160,100 L70,100 L40,80 Z", "l f") + _l(40, 40, 70, 60) + _l(70, 60, 160, 60) + _l(70, 60, 70, 100)
    for k, x in enumerate((88, 108, 128)):
        out += _l(x, 60, x - 18, 40 + 0, "l a d")
    for k in range(3):
        out += _r(24 + k * 98, 124, 80, 40, "l") + _c(64 + k * 98, 144, 6 + k * 2, "l a") + _t(64 + k * 98, 176, f"단면 {k + 1}", "t")
    return out


def longtrans() -> str:
    return (_r(40, 40, 150, 50, "l f", 4) + _l(115, 34, 115, 96, "l a d") + _r(220, 40, 60, 50, "l", 4) + _c(250, 65, 18, "l a") + _t(115, 112, "길이 방향", "t") + _t(250, 112, "가로 방향", "t") + _r(40, 124, 150, 36, "l") + _l(60, 142, 170, 142, "l a d") + _t(115, 176, "길이 방향 단면", "t"))


def cutaway() -> str:
    return (_p("M60,70 L130,50 L240,50 L240,130 L170,150 L60,150 Z", "l f") + _p("M60,70 L170,70 L240,50", "l") + _l(170, 70, 170, 150) + _p("M100,110 L170,110 L200,100", "l a d") + _p("M135,118 Q170,95 205,118", "l a") + _t(160, 38, "겉을 걷어 낸 모습", "t") + _t(205, 138, "안쪽 구조", "t"))


def forcevec() -> str:
    return (_r(100, 70, 120, 56, "l f", 4) + _arrow(160, 20, 160, 66, "l a", 8) + _t(176, 40, "힘", "t", "start") + _r(150, 126, 20, 34, "l") + _p("M130,172 a30,12 0 0 0 60,0", "l a") + _arrow(188, 168, 192, 160, "l a", 7) + _t(210, 172, "토크", "t", "start"))


def dispvec() -> str:
    out = _r(50, 30, 220, 130, "l d", 8)
    for i in range(6):
        for j in range(4):
            x, y = 70 + i * 36, 52 + j * 30
            dx = 10 + 14 * (i / 5) * (1 - j / 6)
            out += _arrow(x, y, x + dx, y + 4 + j * 2, "l a", 5)
    return out + _t(160, 22, "위치마다 움직이는 방향과 크기", "t")


def fluxvec() -> str:
    out = _r(50, 40, 220, 100, "l f", 6) + _t(36, 94, "고온", "t", "end") + _t(284, 94, "저온", "t", "start")
    for k, y in enumerate((60, 80, 100, 120)):
        out += _arrow(70, y, 250 - k * 14, y, "l a", 6)
    return out + _t(160, 160, "열이 이동하는 방향", "t")


def streamline() -> str:
    out = _p("M30,50 L290,50 M30,140 L290,140", "l") + _c(160, 95, 20, "l f")
    for k, dy in enumerate((-30, -15, 15, 30)):
        y = 95 + dy * 1.1
        out += _p(f"M30,{y:g} C100,{y:g} 120,{95 + dy * 2.1:g} 160,{95 + dy * 2.1:g} S 220,{y:g} 288,{y:g}", "l a")
    return out + _arrow(270, 95, 292, 95, "l a", 6)


# ---------------- 신호 · 그래프 ----------------
def spectrum() -> str:
    out = _axes(40, 30, 240, 120, "주파수", "크기")
    for x, h in ((70, 30), (100, 95), (130, 24), (160, 60), (190, 18), (220, 40), (250, 14)):
        out += _l(x, 150, x, 150 - h, "l a w")
    return out


def spectrogram() -> str:
    out = _axes(40, 30, 240, 120, "시간", "주파수")
    for i in range(12):
        for j in range(6):
            strength = max(0.0, 1 - abs(j - (1 + i * 0.35)) / 1.6)
            if strength > 0.1:
                out += f'<rect x="{44 + i * 19.5:g}" y="{34 + (5 - j) * 19:g}" width="18" height="18" class="fa3" opacity="{strength:.2f}"/>'
    return out


def hist() -> str:
    out = _axes(30, 30, 170, 120, "측정값", "횟수")
    for k, h in enumerate((20, 46, 84, 100, 70, 40, 18)):
        out += _r(38 + k * 22, 150 - h, 18, h, "l a fa", 2)
    out += _l(250, 40, 250, 140) + _r(236, 70, 28, 40, "l a", 2) + _l(236, 90, 264, 90, "l a") + _l(250, 40, 250, 70) + _l(250, 110, 250, 140)
    return out + _t(250, 160, "상자 그림", "t")


# ---------------- 3D ----------------
def assembly() -> str:
    return (_r(120, 24, 80, 14, "l", 3) + _r(150, 38, 20, 100, "l f", 2) + _r(70, 70, 180, 22, "l f", 3) + _r(70, 94, 180, 22, "l f", 3) + _r(138, 138, 44, 16, "l", 3) + _t(262, 84, "판", "t", "start") + _t(210, 32, "볼트", "t", "start") + _t(190, 150, "너트", "t", "start"))


def exploded() -> str:
    out = ""
    for k, (y, lab) in enumerate(((22, "볼트"), (66, "위 판"), (108, "아래 판"), (148, "너트"))):
        out += _r(100, y, 120, 22 if k in (1, 2) else 16, "l f" if k in (1, 2) else "l", 3) + _t(236, y + 14, lab, "t", "start")
    return out + _l(160, 38, 160, 148, "l a d") + _arrow(60, 150, 60, 24, "l a")


def deformed() -> str:
    return (_p("M40,100 L280,100", "l d") + _p("M40,100 Q160,150 280,100", "l a", ) + _arrow(160, 56, 160, 96, "l", 6) + _t(160, 48, "하중", "t") + _t(160, 164, "변형된 형상", "t") + _t(160, 90, "원래 형상", "t"))


def mesh() -> str:
    out = _r(50, 30, 220, 130, "l", 6)
    for i in range(1, 11):
        out += _l(50 + i * 20, 30, 50 + i * 20, 160, "l m")
    for j in range(1, 6):
        out += _l(50, 30 + j * 21.6, 270, 30 + j * 21.6, "l m")
    for i in range(10):
        for j in range(6):
            out += _l(50 + i * 20, 30 + j * 21.6, 70 + i * 20, 51.6 + j * 21.6, "l m")
    return out + _l(50, 30, 50, 160, "l a w") + _arrow(30, 95, 48, 95, "l a", 6)


def scan() -> str:
    out = _p("M70,140 C70,60 130,40 160,40 C200,40 250,70 250,140", "l d")
    for k in range(56):
        t = k / 55
        x = 72 + t * 176
        y = 140 - 100 * math.sin(math.pi * t) ** 0.8 + math.sin(k * 7.3) * 3
        out += _c(round(x, 1), round(y, 1), 1.8, "dot")
    return out + _l(70, 146, 250, 146, "l d") + _t(160, 170, "점들로 얻은 실제 형상 / 점선은 기준 형상", "t")


def workcell() -> str:
    return (_p("M30,150 L290,150", "l") + _r(60, 130, 50, 20, "l f", 3) + _l(85, 130, 85, 96) + _l(85, 96, 140, 62) + _l(140, 62, 190, 92) + _c(85, 96, 5, "l a") + _c(140, 62, 5, "l a") + _p("M60,150 A150,150 0 0 1 250,110", "l a d") + _r(215, 120, 46, 30, "l f", 3) + _t(232, 114, "작업물", "t") + _t(150, 40, "도달 범위", "t"))


# ---------------- 4D · 영상 ----------------
def _film(draw: Callable[[int, float, float, float, float], str], note: str) -> str:
    out = ""
    for i in range(4):
        x = 14 + i * 76
        out += _r(x, 36, 66, 86, "l f", 5) + draw(i, x, 36, 66, 86)
        if i < 3:
            out += _arrow(x + 68, 79, x + 76, 79, "l a", 4)
    out += _l(30, 146, 290, 146, "l") + _c(30 + 260 * 0.4, 146, 6, "l a fa") + '<polygon points="22,162 22,176 34,169" class="ah"/>' + _t(46, 174, note, "t", "start")
    return out


def film_load() -> str:
    return _film(lambda i, x, y, w, h: _r(x + 14, y + 54 - i * 8, w - 28, 22 + i * 8, "l a fa", 2) + _arrow(x + w / 2, y + 10, x + w / 2, y + 30 + i * 2, "l a", 5), "하중 단계를 따라 재생")


def film_heat() -> str:
    return _film(lambda i, x, y, w, h: _c(x + w / 2, y + h / 2, 10 + i * 6, "l a fa4") + f'<circle cx="{x + w / 2:g}" cy="{y + h / 2:g}" r="{10 + i * 6}" class="fa" opacity="{0.2 + i * 0.2:.1f}"/>', "해석 시간을 따라 재생")


def film_fill() -> str:
    return _film(lambda i, x, y, w, h: _r(x + 14, y + 14, w - 28, h - 28, "l", 3) + _r(x + 14, y + h - 14 - (i + 1) * 12, w - 28, (i + 1) * 12, "l a fa", 2), "해석 시간을 따라 재생")


def film_mode() -> str:
    return _film(lambda i, x, y, w, h: _p(f"M{x + 8},{y + h / 2:g} Q{x + w / 4:g},{y + h / 2 - 24 * math.cos(i * 0.8):.1f} {x + w / 2:g},{y + h / 2:g} T{x + w - 8},{y + h / 2:g}", "l a"), "모드의 위상을 따라 재생")


def film_robot() -> str:
    return _film(lambda i, x, y, w, h: _l(x + 14, y + h - 12, x + 14, y + 40, "l") + _l(x + 14, y + 40, x + 14 + 30 * math.cos(0.3 + i * 0.35), y + 40 - 30 * math.sin(0.3 + i * 0.35), "l a"), "경로 진행률을 따라 재생")


def film_machining() -> str:
    return _film(lambda i, x, y, w, h: _r(x + 10, y + 40, w - 20, 34, "l fa", 2) + _r(x + 10, y + 40, 6 + i * 14, 10 + i * 3, "l d", 1) + _l(x + 14 + i * 14, y + 14, x + 14 + i * 14, y + 40, "l a"), "공정 단계를 따라 재생")


def film_record() -> str:
    return _film(lambda i, x, y, w, h: _p(f"M{x + 6},{y + 56} L{x + 20},{y + 46 - i * 2} L{x + 32},{y + 60} L{x + 46},{y + 38 + i * 3} L{x + w - 6},{y + 52}", "l a") + _l(x + 10 + i * 14, y + 14, x + 10 + i * 14, y + h - 14, "l d"), "기록 시각을 따라 재생")


def _vframe(x: float = 50, y: float = 24, w: float = 220, h: float = 104) -> str:
    return _r(x, y, w, h, "l f", 8) + f'<polygon points="{x + w / 2 - 10:g},{y + h / 2 - 14:g} {x + w / 2 - 10:g},{y + h / 2 + 14:g} {x + w / 2 + 16:g},{y + h / 2:g}" class="ah"/>'


def vid_process() -> str:
    out = _vframe()
    for k, lab in enumerate(("1 준비", "2 조임", "3 확인")):
        out += _c(80 + k * 80, 148, 5, "l a fa") + _t(92 + k * 80, 152, lab, "t", "start")
    return out


def vid_compare() -> str:
    return _r(30, 28, 120, 96, "l f", 6) + _r(170, 28, 120, 96, "l f", 6) + _t(90, 144, "조건 A", "t") + _t(230, 144, "조건 B", "t") + _arrow(150, 76, 170, 76, "l a", 5) + _arrow(170, 82, 150, 82, "l a", 5) + _t(160, 168, "같은 시간에 함께 재생", "t")


def vid_sync() -> str:
    return _r(40, 18, 240, 82, "l f", 6) + '<polygon points="150,48 150,70 168,59" class="ah"/>' + _p("M40,150 L80,132 L120,146 L160,118 L200,140 L240,126 L280,138", "l a") + _l(160, 106, 160, 164, "l a d") + _t(160, 180, "같은 시각의 영상과 신호", "t")


def vid_event() -> str:
    return _r(30, 40, 260, 20, "l f", 6) + _r(150, 40, 60, 20, "l a fa", 6) + _l(180, 30, 180, 70, "l a") + _t(180, 24, "이상 발생", "t") + _r(70, 90, 80, 56, "l", 4) + _r(170, 90, 80, 56, "l", 4) + _t(110, 162, "직전", "t") + _t(210, 162, "직후", "t")


def vid_3d() -> str:
    return _p("M110,60 L170,40 L230,60 L230,120 L170,140 L110,120 Z", "l f") + _l(170, 40, 170, 100, "l") + _l(110, 60, 170, 80, "l") + _l(230, 60, 170, 80, "l") + _p("M80,140 A100,40 0 0 0 250,150", "l a d") + _arrow(244, 148, 252, 150, "l a", 6) + _t(160, 22, "돌리고 자르고 분해", "t")


def vid_inspect() -> str:
    out = _vframe(40, 22, 240, 108)
    for k, (x, y) in enumerate(((90, 56), (160, 100), (230, 62))):
        out += _c(x, y, 9, "l a fa") + _t(x, y + 4, str(k + 1), "t")
    return out + _t(160, 152, "점검 위치와 순서를 화면 위에 표시", "t")


def vid_summary() -> str:
    out = _r(30, 24, 150, 100, "l f", 6) + '<polygon points="94,62 94,86 114,74" class="ah"/>'
    for k, w in enumerate((90, 70, 80)):
        out += _l(200, 40 + k * 26, 200 + w, 40 + k * 26, "l a")
    return out + _t(105, 144, "핵심 장면", "t") + _t(245, 130, "조건 · 결과 요약", "t")


# ---------------- 계산값 · 판단 ----------------
def calc(args: Sequence[str]) -> str:
    a = list(args) + ["", "", ""]
    out = _r(20, 40, 80, 28, "l", 6) + _t(60, 58, a[0], "t") + _r(20, 90, 80, 28, "l", 6) + _t(60, 108, a[1], "t")
    out += _r(130, 62, 60, 50, "l a fa", 8) + _t(160, 92, "계산", "t") + _arrow(100, 54, 128, 76, "l", 5) + _arrow(100, 104, 128, 98, "l", 5)
    out += _arrow(192, 87, 220, 87, "l a", 6) + _r(222, 64, 78, 46, "l a", 8) + _t(261, 90, a[2], "tb")
    return out + _t(160, 150, "입력을 바꾸면 값이 다시 계산됩니다", "t")


def judge(args: Sequence[str]) -> str:
    out = ""
    for k, s in enumerate(list(args)[:3]):
        y = 28 + k * 40
        out += _r(40, y, 180, 30, "l f", 6) + _c(58, y + 15, 6, "l a") + _t(72, y + 19, s, "t", "start")
    return out + _p("M250,50 L290,50 L300,66 L290,82 L250,82 L240,66 Z", "l a fa") + _t(270, 70, "보류", "tb")


SKETCHES: dict[str, Callable[..., str]] = {
    "contour": contour, "deform": deform, "hotspot": hotspot, "diff": diff, "photo": photo, "layout": layout, "uncertain": uncertain,
    "multicut": multicut, "longtrans": longtrans, "cutaway": cutaway, "forcevec": forcevec, "dispvec": dispvec, "fluxvec": fluxvec, "streamline": streamline,
    "spectrum": spectrum, "spectrogram": spectrogram, "hist": hist,
    "assembly": assembly, "exploded": exploded, "deformed": deformed, "mesh": mesh, "scan": scan, "workcell": workcell,
    "film_load": film_load, "film_heat": film_heat, "film_fill": film_fill, "film_mode": film_mode, "film_robot": film_robot, "film_machining": film_machining, "film_record": film_record,
    "vid_process": vid_process, "vid_compare": vid_compare, "vid_sync": vid_sync, "vid_event": vid_event, "vid_3d": vid_3d, "vid_inspect": vid_inspect, "vid_summary": vid_summary,
    "calc": calc, "judge": judge,
}


def sketch(kind: str, label: str, args: Sequence[str] = ()) -> str:
    """개념도 SVG. kind는 SKETCHES의 키."""
    fn = SKETCHES[kind]
    return frame(fn(args) if kind in ("calc", "judge") else fn(), label)


SKETCH_CSS = """.sk{display:block;width:100%;height:100%}.sk .l{fill:none;stroke:#4B5661;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}.sk .f{fill:#E9EEF2}.sk .fa{fill:#CFEAE7}.sk .fa2{fill:rgba(11,132,128,.12)}.sk .fa3{fill:#0B8480}.sk .fa4{fill:rgba(11,132,128,.08)}
.sk .a{stroke:#0B8480}.sk .d{stroke-dasharray:4 3}.sk .h{stroke-width:1.1}.sk .m{stroke-width:.8;opacity:.6}.sk .w{stroke-width:3}.sk .ah{fill:#0B8480}.sk .dot{fill:#0B8480}
.sk .t{font-size:11px;fill:#4B5661}.sk .tb{font-size:13px;font-weight:600;fill:#2B3640}.sk .cap{font-size:9.5px;fill:#7A8590}"""
