"""체결 결과 화면 (한 파일 HTML): 조인트 단면, 체결 선도, 토크-체결력, 안전율, 물리량, 대화 기록.

합격·불합격을 표시하지 않는다. 안전율은 값과 함께 1.0(물리적 경계)의 위치만 보인다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Sequence

from cont.answer import PhysicsAnswer
from cont.packs.fastening.curves import joint_diagram, torque_preload
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.shape import bolt_length, joint_shape
from cont.view.diagnosis_html import CSS, LEVELS, _fmt, _page, _ticks
from cont.view.viewer3d import VIEWER_CSS, VIEWER_JS, viewer

EXTRA_CSS = """
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(330px,100%),1fr));gap:12px}
.dr .plate1{fill:var(--band);stroke:var(--sub)}.dr .plate2{fill:var(--okbg);stroke:var(--sub)}.dr .bolt{fill:var(--sig);opacity:.85}.dr .hole{fill:var(--card)}
.dr .dim{stroke:var(--sub);stroke-width:1}.dr text{fill:var(--ink);font-size:12px}.dr .cl{stroke:var(--sub);stroke-dasharray:6 3 1 3;stroke-width:.8}
.ln1{fill:none;stroke:var(--sig);stroke-width:2}.ln2{fill:none;stroke:var(--ok);stroke-width:2}.ln3{stroke:var(--bad);stroke-width:2}.dash{stroke:var(--sub);stroke-dasharray:4 3;stroke-width:1;fill:none}
.gh{fill:none;stroke:var(--mark,#b07a1e);stroke-width:1.4;stroke-dasharray:5 4}.ghn{fill:none;stroke:none}.ghpt{fill:none;stroke:var(--mark,#b07a1e);stroke-width:1.6}
.pt{fill:var(--bad)}.lbl{fill:var(--ink);font-size:11.5px}
.sf{display:grid;grid-template-columns:minmax(120px,190px) 1fr 64px;gap:6px 10px;align-items:center;font-size:13.5px}
.sf .bar{position:relative;height:14px;background:var(--bg);border:1px solid var(--line);border-radius:7px}
.sf .fill{position:absolute;left:0;top:0;bottom:0;background:var(--sig);border-radius:7px;opacity:.75}
.sf .one{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--ink)}.sf .v{text-align:right;font-variant-numeric:tabular-nums;font-weight:650}
.chg{color:var(--sub);font-size:12px}.chat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.chat .u{font-weight:650;margin-top:8px}.chat .a{white-space:pre-wrap;margin:2px 0 8px;overflow-wrap:anywhere}.chat .src{color:var(--sub);font-size:12px}
.chat form{display:flex;gap:8px;margin-top:10px}.chat input{flex:1;min-width:0;font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
.chat button{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:6px 14px;cursor:pointer}
.chat button:hover{border-color:var(--sig)}.chat input:focus-visible,.chat button:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
"""
SAFETY = (("safety_yield", "항복"), ("safety_opening", "벌어짐"), ("safety_slip", "미끄럼"), ("safety_pressure_head", "면압 (머리 쪽)"),
          ("safety_pressure_nut", "면압 (너트 쪽)"), ("safety_fatigue", "피로"))
CHAT_JS = """
(function(){var f=document.querySelector('.chat form');if(!f)return;f.addEventListener('submit',function(ev){ev.preventDefault();
var i=f.querySelector('input'),q=i.value.trim();if(!q)return;i.disabled=true;
fetch(f.dataset.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:q})})
.then(function(){location.reload()}).catch(function(){i.disabled=false;alert('답을 받지 못했습니다. 서버가 켜져 있는지 확인해 주세요.')});});})();
"""


def _section(joint: BoltedJoint, ghost: BoltedJoint | None = None) -> str:
    """조인트 단면 (축척에 맞춘 그림). 머리·너트 높이와 볼트 길이는 3D 형상과 같은 표준 데이터에서 온다.

    ghost를 주면 바꾸기 전 조인트의 윤곽을 점선으로 겹쳐 그린다 (두 판이 맞닿는 면을 맞춘다).
    """
    def dims(j: BoltedJoint) -> dict[str, float]:
        t1, t2, nut = j.plate_head.thickness, j.plate_nut.thickness, j.thread.nut_height
        return {"d": j.d, "dw": j.bearing_diameter, "dh": j.hole, "da": j.outer_diameter, "t1": t1, "t2": t2, "head": j.thread.head_height,
                "nut": nut, "stick": bolt_length(j) - (t1 + t2) - nut}

    g = dims(joint)
    both = [g] + ([dims(ghost)] if ghost else [])
    above = max(x["head"] + x["t1"] for x in both); below = max(x["t2"] + x["nut"] + x["stick"] for x in both)
    w, h, pad = 440, 300, 34
    s = min((w - 2 * pad - 70) / max(x["da"] for x in both), (h - 2 * pad) / (above + below))
    cx = pad + 35 + max(x["da"] for x in both) * s / 2
    ymid = (h - (above + below) * s) / 2 + above * s          # 두 판이 맞닿는 면

    def rects(x: dict[str, float], cls: dict[str, str]) -> str:
        def rect(name: str, width: float, za: float, zb: float) -> str:   # z는 맞닿는 면에서 아래로 +
            return (f'<rect class="{cls[name]}" x="{cx - width * s / 2:.1f}" y="{ymid + za * s:.1f}" width="{width * s:.1f}" height="{(zb - za) * s:.1f}"/>')
        return (rect("plate1", x["da"], -x["t1"], 0) + rect("plate2", x["da"], 0, x["t2"]) + rect("hole", x["dh"], -x["t1"], x["t2"])
                + rect("bolt", x["dw"], -x["t1"] - x["head"], -x["t1"]) + rect("bolt", x["d"], -x["t1"], x["t2"] + x["nut"] + x["stick"])
                + rect("bolt", x["dw"], x["t2"], x["t2"] + x["nut"]))

    y1, yn = ymid - g["t1"] * s, ymid + g["t2"] * s
    xr = cx + g["da"] * s / 2 + 14
    old = rects(dims(ghost), {"plate1": "gh", "plate2": "gh", "hole": "ghn", "bolt": "gh"}) if ghost else ""
    return (f'<svg class="dr" viewBox="0 0 {w} {h}" role="img" aria-label="볼트 조인트 단면">'
            + rects(g, {"plate1": "plate1", "plate2": "plate2", "hole": "hole", "bolt": "bolt"}) + old
            + f'<line class="cl" x1="{cx:.1f}" y1="{ymid - above * s - 12:.1f}" x2="{cx:.1f}" y2="{ymid + below * s + 12:.1f}"/>'
            + f'<line class="dim" x1="{xr:.1f}" y1="{y1:.1f}" x2="{xr:.1f}" y2="{yn:.1f}"/>'
            + f'<line class="dim" x1="{xr - 4:.1f}" y1="{y1:.1f}" x2="{xr + 4:.1f}" y2="{y1:.1f}"/><line class="dim" x1="{xr - 4:.1f}" y1="{yn:.1f}" x2="{xr + 4:.1f}" y2="{yn:.1f}"/>'
            + f'<text x="{xr + 7:.1f}" y="{(y1 + yn) / 2 + 4:.1f}">l_K {_fmt(g["t1"] + g["t2"])}</text>'
            + f'<text x="{cx - g["da"] * s / 2:.1f}" y="{(y1 + ymid) / 2 + 4:.1f}" text-anchor="end" dx="-6">{_fmt(g["t1"])}</text>'
            + f'<text x="{cx - g["da"] * s / 2:.1f}" y="{(ymid + yn) / 2 + 4:.1f}" text-anchor="end" dx="-6">{_fmt(g["t2"])}</text>'
            + f'<text x="{cx:.1f}" y="{h - 6}" text-anchor="middle">{html.escape(joint.size)} · 구멍 {_fmt(g["dh"])} · 좌면 {_fmt(g["dw"])} · 바깥지름 {_fmt(g["da"])} (mm)</text></svg>')


def _axes(w: int, h: int, x1: float, y1: float, xlab: str, ylab: str, l: int = 58, r: int = 14, t: int = 12, b: int = 34):
    def px(v: float) -> float:
        return l + v / x1 * (w - l - r)

    def py(v: float) -> float:
        return h - b - v / y1 * (h - t - b)

    out = [f'<line class="ax" x1="{l}" y1="{h - b}" x2="{w - r}" y2="{h - b}"/><line class="ax" x1="{l}" y1="{t}" x2="{l}" y2="{h - b}"/>']
    for v in _ticks(0, y1):
        out.append(f'<text class="tick" x="{l - 6}" y="{py(v) + 4:.1f}" text-anchor="end">{_fmt(v)}</text>')
    for v in _ticks(0, x1, 5):
        out.append(f'<text class="tick" x="{px(v):.1f}" y="{h - b + 15}" text-anchor="middle">{_fmt(v)}</text>')
    out.append(f'<text class="tick" x="{(l + w - r) / 2:.1f}" y="{h - 4}" text-anchor="middle">{xlab}</text>'
               f'<text class="tick" x="12" y="{t + 2}" text-anchor="start">{ylab}</text>')
    return px, py, "".join(out)


def _joint_diagram(joint: BoltedJoint, load: LoadCase, ghost: tuple[BoltedJoint, LoadCase] | None = None) -> str:
    """ghost를 주면 바꾸기 전의 선도를 점선으로 겹쳐 그린다."""
    jd = joint_diagram(joint, load)
    old = joint_diagram(*ghost) if ghost else None
    w, h = 440, 300
    x1 = max((x.bolt_elongation + x.plate_compression) for x in (jd, old) if x) * 1.08
    y1 = max((x.preload + x.bolt_extra) for x in (jd, old) if x) * 1.18
    px, py, ax = _axes(w, h, x1, y1, "변형 (mm)", "힘 (N)")
    xs, xe = jd.bolt_elongation, jd.bolt_elongation + jd.plate_compression
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="체결 선도">', ax]
    if old:
        oxs, oxe = old.bolt_elongation, old.bolt_elongation + old.plate_compression
        out.append(f'<polyline class="gh" points="{px(0):.1f},{py(0):.1f} {px(oxs):.1f},{py(old.preload):.1f} {px(oxe):.1f},{py(0):.1f}"/>'
                   f'<circle class="ghpt" cx="{px(oxs):.1f}" cy="{py(old.preload):.1f}" r="4"/>')
    out += [f'<polyline class="ln1" points="{px(0):.1f},{py(0):.1f} {px(xs + jd.extra_elongation):.1f},{py(jd.preload + jd.bolt_extra):.1f}"/>',
           f'<polyline class="ln2" points="{px(xs):.1f},{py(jd.preload):.1f} {px(xe):.1f},{py(0):.1f}"/>',
           f'<circle class="pt" cx="{px(xs):.1f}" cy="{py(jd.preload):.1f}" r="4"/>',
           f'<text class="lbl" x="{px(xs) - 8:.1f}" y="{py(jd.preload) - 8:.1f}" text-anchor="end">F_M {_fmt(jd.preload)}</text>']
    if jd.axial_load > 0:
        xa = xs + jd.extra_elongation
        out.append(f'<line class="ln3" x1="{px(xa):.1f}" y1="{py(jd.preload - jd.plate_relief):.1f}" x2="{px(xa):.1f}" y2="{py(jd.preload + jd.bolt_extra):.1f}"/>'
                   f'<text class="lbl" x="{px(xa) + 6:.1f}" y="{py(jd.preload - jd.plate_relief / 2):.1f}">F_A</text>')
    out.append("</svg>")
    if jd.axial_load > 0:
        out.append(f'<div class="sub" style="margin:2px 0 6px">운전 하중 F_A {_fmt(jd.axial_load)} N 가운데 볼트가 {_fmt(jd.bolt_extra)} N을 더 받고, '
                   f'판의 누름이 {_fmt(jd.plate_relief)} N 줄어듭니다.</div>')
    return "".join(out)


def _torque_chart(joint: BoltedJoint, load: LoadCase, ghost: tuple[BoltedJoint, LoadCase] | None = None) -> str:
    """ghost를 주면 바꾸기 전의 직선과 점을 점선·빈 점으로 겹쳐 그린다."""
    tp = torque_preload(joint, load)
    old = torque_preload(*ghost) if ghost else None
    w, h = 440, 300
    x1 = max(x.torque for x in (tp, old) if x) * 1.6
    y1 = max(max(x.slope_max * x1, x.preload_at_yield) for x in (tp, old) if x) * 1.08
    px, py, ax = _axes(w, h, x1, y1, "조임 토크 (N·m)", "체결력 (N)")
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="조임 토크와 체결력">', ax]
    if tp.slope_max != tp.slope_min:
        out.append(f'<polygon class="band" points="{px(0):.1f},{py(0):.1f} {px(x1):.1f},{py(tp.slope_max * x1):.1f} {px(x1):.1f},{py(tp.slope_min * x1):.1f}"/>')
    if old:
        out.append(f'<polyline class="gh" points="{px(0):.1f},{py(0):.1f} {px(x1):.1f},{py(old.slope * x1):.1f}"/>'
                   f'<circle class="ghpt" cx="{px(old.torque):.1f}" cy="{py(old.preload):.1f}" r="4"/>')
    out.append(f'<polyline class="ln1" points="{px(0):.1f},{py(0):.1f} {px(x1):.1f},{py(tp.slope * x1):.1f}"/>'
               f'<line class="dash" x1="{px(0):.1f}" y1="{py(tp.preload_at_yield):.1f}" x2="{px(x1):.1f}" y2="{py(tp.preload_at_yield):.1f}"/>'
               f'<text class="lbl" x="{px(x1):.1f}" y="{py(tp.preload_at_yield) - 5:.1f}" text-anchor="end">조임 중 항복 도달 {_fmt(tp.preload_at_yield)}</text>'
               f'<circle class="pt" cx="{px(tp.torque):.1f}" cy="{py(tp.preload):.1f}" r="4"/>'
               f'<text class="lbl" x="{px(tp.torque) + 8:.1f}" y="{py(tp.preload) + 14:.1f}">{_fmt(tp.torque)} N·m → {_fmt(tp.preload)} N</text></svg>')
    return "".join(out)


def _safety(a: PhysicsAnswer, before: PhysicsAnswer | None) -> str:
    vals = [(label, a.value(k), before.value(k) if before else None, a.get(k).note) for k, label in SAFETY]
    top = max([v for _, v, _, _ in vals if v is not None] + [2.0]) * 1.05
    rows = []
    for label, v, old, note in vals:
        if v is None:
            rows.append(f'<div>{label}</div><div class="chg">{html.escape(note or "계산하지 않음")}</div><div class="v">-</div>')
            continue
        chg = f' <span class="chg">(이전 {old:.2f})</span>' if old is not None and abs(old - v) > 5e-3 else ""
        rows.append(f'<div>{label}{chg}</div><div class="bar"><div class="fill" style="width:{min(v / top, 1) * 100:.1f}%"></div>'
                    f'<div class="one" style="left:{1 / top * 100:.1f}%" title="1.0"></div></div><div class="v">{v:.2f}</div>')
    return ('<div class="panel"><div class="sf">' + "".join(rows) + '</div><div class="sub" style="margin:8px 0 4px">검은 선은 1.0입니다. '
            "합격·불합격은 표시하지 않습니다. 판정 기준은 정해진 환경에서만 적용합니다.</div></div>")


def _table(a: PhysicsAnswer, before: PhysicsAnswer | None) -> str:
    e = html.escape
    rows = []
    for q in a.quantities:
        old = before.value(q.key) if before else None
        changed = old is not None and q.value is not None and abs(old - q.value) > 1e-9 * max(abs(old), 1.0)
        rng = f"{_fmt(q.expected_range[0])} ~ {_fmt(q.expected_range[1])}" if q.expected_range else ""
        rows.append(f"<tr><td>{e(q.label)}</td><td class='n'>{_fmt(q.value)}</td><td>{e(q.unit)}</td>"
                    f"<td class='n'>{_fmt(old) if changed else ''}</td><td>{rng}</td><td>{e(q.note or '')}</td></tr>")
    head = "<th>항목</th><th>값</th><th>단위</th><th>바꾸기 전</th><th>범위 (마찰 산포)</th><th>비고</th>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_fastening(joint: BoltedJoint, load: LoadCase, answer: PhysicsAnswer, before: PhysicsAnswer | None = None,
                     turns: Sequence[tuple[str, str, str]] = (), ask_url: str | None = None,
                     title: str = "볼트 조인트 체결 계산", subtitle: str = "", downloads: Sequence[tuple[str, str]] = ()) -> str:
    """turns: (사용자 말, 답, 답의 출처 설명). ask_url이 있으면 입력 칸을 둔다 (체결 서버가 받는다)."""
    e = html.escape
    a = answer
    shape = joint_shape(joint)
    dl = (" 형상 파일 받기: " + " · ".join(f'<a href="{e(u)}" download>{e(n)}</a>' for n, u in downloads)) if downloads else ""
    level = LEVELS.get(a.confidence.level, a.confidence.level)
    cards = [("볼트", f"{e(joint.size)} · {e(joint.property_class)}"), ("조임 토크", f"{_fmt(load.tightening_torque)} N·m"),
             ("조립 체결력", f"{_fmt(a.value('preload'))} N"), ("항복 안전율", f"{a.value('safety_yield'):.2f}"), ("신뢰도", level)]
    chat = ""
    if turns or ask_url:
        log = "".join(f'<div class="u">{e(u)}</div><div class="a">{e(t)}</div><div class="src">{e(s)}</div>' for u, t, s in turns)
        form = (f'<form data-url="{e(ask_url)}"><input type="text" aria-label="바꿀 내용" placeholder="예: M12로 바꾸고 토크 80으로 / 항복 안전율 1.5 이상이 되게">'
                '<button type="submit">보내기</button></form>') if ask_url else ""
        hint = "" if ask_url else '<div class="sub">미리 실행한 대화입니다. 직접 입력은 체결 서버(python -m cont.dialogue.serve_fastening)에서 됩니다.</div>'
        chat = f'<h2>대화로 바꾸기</h2><div class="chat">{hint}{log}{form}</div>' + (f"<script>{CHAT_JS}</script>" if ask_url else "")
    body = f"""<h1>{e(title)}</h1><div class="sub">{e(subtitle)}</div>
<div class="cards" style="margin-top:14px">{"".join(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in cards)}</div>
<h2>3D 형상</h2>
<div class="panel"><h3>{e(shape.name)} <span class="sub">· 판은 안이 보이게 4분의 1을 잘라 냄 · 볼트 길이 {_fmt(bolt_length(joint))} mm</span></h3>
{viewer(shape.opened(("plate_head", "plate_nut")), shape.name, (("볼트·너트", "--sig"), ("머리 쪽 판", "--band"), ("너트 쪽 판", "--okbg")))}
<div class="sub" style="margin:4px 0 6px">치수에서 만든 형상입니다. 값을 바꾸면 형상도 다시 만들어집니다. 나사산과 모따기는 그리지 않았고, 판은 체결부 대체 바깥지름의 원판입니다.{dl}</div></div>
<h2>조인트와 체결 선도</h2>
<div class="two"><div class="panel"><h3>단면 <span class="sub">· 축척에 맞춤</span></h3>{_section(joint)}</div>
<div class="panel"><h3>체결 선도 <span class="sub">· 파랑 볼트, 초록 판, 빨강 운전 하중</span></h3>{_joint_diagram(joint, load)}</div></div>
<h2>조임 토크와 체결력</h2>
<div class="two"><div class="panel"><h3>토크-체결력 <span class="sub">· 띠는 마찰 산포</span></h3>{_torque_chart(joint, load)}</div>
<div><h3 style="margin:0 0 8px;font-size:14px">안전율</h3>{_safety(a, before)}</div></div>
{chat}
<h2>물리량</h2>{_table(a, before)}
<h2>계산 근거</h2><ul>{"".join(f"<li>{e(b)}</li>" for b in a.basis)}</ul>
<div class="note">계산 방법: {e(a.method)}<br>신뢰도 {e(level)}: {e(a.confidence.reason)}</div>"""
    return _page(title, body + f"<script>{VIEWER_JS}</script>").replace("</style>", EXTRA_CSS + VIEWER_CSS + "</style>", 1)
