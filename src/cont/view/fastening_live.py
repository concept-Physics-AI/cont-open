"""체결 화면 (움직이는 한 화면). 2026-11-23 대표 의견으로 만들었다:

- 고정된 긴 문서가 아니라 한 화면. 보기(3D, 단면, 체결 선도, 토크)를 오가고, 값이 바뀌면 그 자리에서 변한다.
- 지나간 말은 사라지고, 눈여겨볼 것만 자연스럽게 나타난다.
- 답은 한 줄 결론과 숫자 몇 개. 긴 글은 "자세히"에 접어 둔다.

화면은 "상태"의 목록을 받는다. 상태 하나는 조인트 한 시점의 값·그림·형상과, 그 상태로 오게 한 말과 짧은 답이다.
서버에서는 말을 보낼 때마다 새 상태를 받아 그 자리에서 바뀐다. 파일로 낸 화면은 미리 만든 상태들을 차례로 보여 준다.
합격·불합격은 표시하지 않는다. 안전율이 1.0을 넘나들 때만 그 사실을 알린다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Sequence

from cont.answer import PhysicsAnswer
from cont.packs.fastening.joint import BoltedJoint, LoadCase
from cont.packs.fastening.shape import bolt_length, compression_zone, joint_shape
from cont.shape import revolve
from cont.view.diagnosis_html import CSS, LEVELS
from cont.view.fastening_html import EXTRA_CSS, SAFETY, _joint_diagram, _section, _table, _torque_chart
from cont.view.field_image import FIELD_CSS, field_image
from cont.packs.fastening.field import stress_field
from cont.packs.fastening.sensing import plan as sensing_plan
from cont.view.viewer3d import viewer_data

LINGER_MS = 9000        # 고를 것이 없는 답이 화면에 머무는 시간

# 읽는 값: (묶음, 답변 묶음의 키, 이름, 단위, 소수 자리). 묶음은 "보이는 물리"와 "숨은 물리"다.
#   보이는 물리 = 사람이 정하거나 현장에서 잴 수 있는 값.  숨은 물리 = 직접 잴 수 없어 계산으로 드러내는 상태.
TILES = (
    ("seen", "tightening_torque", "조임 토크", "N·m", 1), ("seen", "axial_load_max", "축방향 운전 하중", "N", 0), ("seen", "clamp_length", "체결 길이", "mm", 1),
    ("hidden", "preload", "조립 체결력", "N", 0), ("hidden", "load_share", "볼트가 받는 운전 하중의 몫", "%", 1),
    ("hidden", "residual_clamp_min", "남는 체결력 (최소)", "N", 0), ("hidden", "bolt_equivalent_stress_working", "볼트 등가응력", "MPa", 0),
    ("hidden", "surface_pressure", "좌면 압력", "MPa", 0),
)
# (묶음, 이름, 지위, 풀이). 지위는 docs/hidden_physics.md의 구분을 따른다. 체결에는 센서가 없어 "관측"과 "추정"이 아니라 "입력"과 "해석"이다.
GROUPS = (("seen", "보이는 물리", "입력", "직접 정하거나 잴 수 있는 값"), ("hidden", "숨은 물리", "해석", "직접 잴 수 없는 안쪽 상태"))

def core_numbers(joint: BoltedJoint, answer: PhysicsAnswer) -> list[dict[str, Any]]:
    """기본 화면의 핵심 숫자 (셋까지): 숨은 물리 둘과 결과 하나."""
    stress = answer.value("bolt_equivalent_stress_working")
    lo_hi = answer.get("preload").expected_range
    spread = f"마찰에 따라 {lo_hi[0]:,.0f} ~ {lo_hi[1]:,.0f}" if lo_hi and lo_hi[0] != lo_hi[1] else "마찰 범위를 주지 않아 한 값만 있음"
    lowest = min(((answer.value(k), label) for k, label in SAFETY if answer.value(k) is not None), default=(None, ""))
    return [
        {"label": "조립 체결력", "value": answer.value("preload"), "unit": "N", "digits": 0, "status": "숨은 물리 · 해석", "range": spread, "low": False},
        {"label": "볼트 응력 ÷ 항복강도", "value": stress / joint.yield_strength, "unit": "", "digits": 2, "status": "숨은 물리 · 해석",
         "range": f"{stress:,.0f} ÷ {joint.yield_strength:,.0f} MPa", "low": stress > joint.yield_strength},
        {"label": f"가장 낮은 안전율 ({lowest[1]})", "value": lowest[0], "unit": "", "digits": 2, "status": "결과 · 해석", "range": "1.0이 경계",
         "low": lowest[0] is not None and lowest[0] < 1.0},
    ]


def trust(joint: BoltedJoint, load: LoadCase, answer: PhysicsAnswer) -> list[list[str]]:
    """이 결과를 믿어도 되는가. 내용은 답변 묶음이 스스로 낸다 (PhysicsAnswer.trust)."""
    return answer.trust()


BOLT = ("bolt_head", "bolt_shank", "nut")
# 바꾼 항목 → (3D에서 표시할 부품들, 이름표를 붙일 부품, 이름, 단위). 이름표를 붙일 부품이 없으면 화면 위쪽에 글로만 알린다.
MARKS = {
    "size": (BOLT, "bolt_head", "볼트", ""), "property_class": (BOLT, "bolt_shank", "강도 등급", ""),
    "tightening_torque": (("bolt_head", "nut"), "nut", "조임 토크", "N·m"),
    "plate_head_thickness": (("plate_head",), "plate_head", "머리 쪽 판", "mm"), "plate_nut_thickness": (("plate_nut",), "plate_nut", "너트 쪽 판", "mm"),
    "outer_diameter": (("plate_head", "plate_nut"), "plate_head", "바깥지름", "mm"), "shank_length": (("bolt_shank",), "bolt_shank", "축부 길이", "mm"),
    "axial_load_max": ((), None, "축방향 하중", "N"), "transverse_load": ((), None, "축직각 하중", "N"), "friction_thread": ((), None, "마찰계수", ""),
    "friction_range": ((), None, "마찰 범위", ""), "friction_interface": ((), None, "판 사이 마찰계수", ""), "embedding": ((), None, "함몰량", "mm"),
}


def _show(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        return "~".join(_show(x) for x in v)
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"
    return "없음" if v is None else str(v)


def marks(old_joint: BoltedJoint, old_load: LoadCase, joint: BoltedJoint, load: LoadCase) -> dict[str, Any]:
    """바뀐 곳: 두 시점의 조인트·하중을 견주어, 3D에서 빛낼 부품, 부품에 붙일 이름표, 부품이 없는 변화의 알림을 만든다."""
    pairs = {
        "size": (old_joint.size, joint.size), "property_class": (old_joint.property_class, joint.property_class),
        "tightening_torque": (old_load.tightening_torque, load.tightening_torque),
        "plate_head_thickness": (old_joint.plate_head.thickness, joint.plate_head.thickness),
        "plate_nut_thickness": (old_joint.plate_nut.thickness, joint.plate_nut.thickness),
        "outer_diameter": (old_joint.outer_diameter, joint.outer_diameter), "shank_length": (old_joint.shank_length, joint.shank_length),
        "axial_load_max": (old_load.axial_load_max, load.axial_load_max), "transverse_load": (old_load.transverse_load, load.transverse_load),
        "friction_thread": (old_load.friction_thread, load.friction_thread), "friction_range": (old_load.friction_range, load.friction_range),
        "friction_interface": (old_load.friction_interface, load.friction_interface), "embedding": (old_load.embedding, load.embedding),
    }
    glow: list[str] = []; tags: dict[str, list[str]] = {}; notes: list[str] = []
    for key, (a, b) in pairs.items():
        if a == b:
            continue
        roles, anchor, name, unit = MARKS[key]
        text = f"{name} {_show(a)} → {_show(b)}{(' ' + unit) if unit else ''}"
        glow += [r for r in roles if r not in glow]
        if anchor:
            tags.setdefault(anchor, []).append(text)
        else:
            notes.append(text)
    return {"glow": glow, "tags": [{"role": r, "text": " / ".join(t)} for r, t in tags.items()], "notes": notes}


def sensing_html(joint: BoltedJoint, load: LoadCase) -> str:
    """현장 계측 추천: 무엇을 달고, 어떻게 잇고, 이 조인트에서 신호가 얼마나 나오는가."""
    e = html.escape
    p = sensing_plan(joint, load)

    def number(v: float | None) -> str:
        return "-" if v is None else (f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}" if abs(v) >= 10 else f"{v:.3g}")

    out = [f'<p class="why">{e(p.summary)}</p>']
    for o in p.options:
        sig = "".join(f'<div class="sg"><span>{e(x.label)}</span><b>{number(x.value)} <i>{e(x.unit)}</i></b>'
                      + (f'<em>{e(x.note)}</em>' if x.note else "") + "</div>" for x in o.signals)
        chain = '<span class="ar"></span>'.join(f"<span>{e(c)}</span>" for c in o.chain)
        out.append(f'<div class="sen"><div class="sh"><span class="sst">{e(o.stage)}</span>{e(o.label)}</div>'
                   f'<p class="swhy">{e(o.why)}</p><div class="sgs">{sig}</div>'
                   f'<div class="chain">{chain}</div>'
                   f'<dl class="tr"><dt>재는 것</dt><dd>{e(o.measures)}</dd><dt>필요한 것</dt><dd>{e(", ".join(o.hardware))}</dd>'
                   f'<dt>통신</dt><dd>{e(o.protocol)}</dd><dt>ConT에서</dt><dd>{e(o.into_cont.replace("`", ""))}</dd>'
                   f'<dt>주의</dt><dd>{e("; ".join(o.cautions))}</dd></dl></div>')
    out.append('<p class="why">' + " · ".join(e(x) for x in p.limits) + "</p>")
    return "".join(out)


def stress_image(joint: BoltedJoint, load: LoadCase) -> str:
    """물리 이미지: 판 안의 압축 응력 분포와 그 아래 한 줄 (수치해석과 VDI 식의 차이, 평형 잔차)."""
    a = stress_field(joint, load)
    t = joint.plate_nut.thickness
    r_h, r_w = joint.hole / 2, min(joint.bearing_diameter, joint.outer_diameter) / 2
    img = field_image(a, "plate_axial_compression", lines=((t, "판 사이 면"),),
                      marks=((r_h, r_w, joint.clamp_length, "머리 좌면"), (r_h, r_w, 0.0, "너트 좌면")))
    res = a.residuals[0]
    facts = (f'판 사이 면의 최대 압력 <b>{a.value("interface_peak_pressure"):,.0f} MPa</b> · 눌리는 반지름 <b>{a.value("pressed_radius"):.1f} mm</b>'
             f' (VDI 원뿔 {a.value("pressed_radius_vdi_cone"):.1f} mm) · 판 컴플라이언스는 VDI 식보다 <b>{a.value("plate_resilience_deviation"):+.1f}%</b>'
             f' · 평형 잔차 {res.value:,.0f} N')
    return f'{img}<div class="fcap">{facts}<br>볼트는 풀지 않고 좌면에 고른 압력으로 걸었고, 두 판은 붙어 있다고 가정했습니다. 청회색은 당겨지는 것으로 계산된 곳이며 실제로는 판이 벌어지는 곳입니다. 판정은 하지 않습니다.</div>'


def state(joint: BoltedJoint, load: LoadCase, answer: PhysicsAnswer, before: PhysicsAnswer | None = None,
          brief: dict[str, Any] | None = None, detail: str = "") -> dict[str, Any]:
    """화면이 그리는 한 시점. before: 바꾸기 전의 답 (있으면 바뀐 곳 표시와 점선 겹침을 만든다). brief: 짧은 답 (첫 상태는 없음)."""
    shape = joint_shape(joint)
    old = None
    if before is not None:
        old = (BoltedJoint.from_dict(before.inputs["joint"]), LoadCase.from_dict(before.inputs["load"]))
    special = {"tightening_torque": load.tightening_torque, "axial_load_max": load.axial_load_max, "clamp_length": joint.clamp_length,
               "load_share": answer.value("load_factor") * 100.0}
    tiles = [{"group": group, "label": label, "value": special[key] if key in special else answer.value(key), "unit": unit, "digits": d, "range": ""}
             for group, key, label, unit, d in TILES]
    lo_hi = answer.get("preload").expected_range
    if lo_hi and lo_hi[0] != lo_hi[1]:                       # 같은 토크로 조여도 마찰에 따라 체결력이 달라진다
        next(t for t in tiles if t["label"] == "조립 체결력")["range"] = f"마찰에 따라 {lo_hi[0]:,.0f} ~ {lo_hi[1]:,.0f}"
    safety = [{"label": label, "value": answer.value(key), "note": answer.get(key).note or ""} for key, label in SAFETY]
    basis = "".join(f"<li>{html.escape(b)}</li>" for b in answer.basis)
    level = LEVELS.get(answer.confidence.level, answer.confidence.level)
    view = viewer_data(shape.opened(("plate_head", "plate_nut")))
    for part, spec in zip(view["parts"], shape.parts):
        part["anchor"] = [0.0, 0.0, (spec.z0 + spec.z1) / 2]
        part["reach"] = spec.outer / 2                       # 이름표를 부품 바깥쪽에 두는 데 쓴다
    zone = revolve(compression_zone(joint), sweep=270.0)
    view["parts"].append({"name": "판이 눌리는 영역", "role": "zone", "color": "--zone", "anchor": [0.0, 0.0, 0.0], "reach": 0.0,
                          "tri": [round(float(x), 3) for x in zone.vertices[zone.faces].reshape(-1)]})
    stress = answer.value("bolt_equivalent_stress_working")
    return {
        "title": f"{joint.size} · {joint.property_class}", "size": joint.size, "grade": joint.property_class,
        "sub": f"판 {joint.plate_head.thickness:g} + {joint.plate_nut.thickness:g} mm, 볼트 길이 {bolt_length(joint):.1f} mm",
        "tiles": tiles, "safety": safety, "viewer": view, "core": core_numbers(joint, answer), "trust": trust(joint, load, answer), "truth_line": answer.truth_line(), "sensing": sensing_html(joint, load),
        "hidden": {"use": stress / joint.yield_strength, "stress": stress, "yield": joint.yield_strength},   # 볼트 색: 등가응력 ÷ 항복강도
        "views": {"section": _section(joint, old[0] if old else None), "diagram": _joint_diagram(joint, load, old),
                  "torque": _torque_chart(joint, load, old), "field": stress_image(joint, load)},
        "marks": marks(*old, joint, load) if old else {"glow": [], "tags": [], "notes": []},
        "brief": brief, "detail": detail,
        "more": f"<h3>물리: 계산한 모든 값</h3>{_table(answer, before)}<h3>수학·조건: 식과 가정</h3><ul>{basis}</ul>"
                f'<div class="note">계산 방법: {html.escape(answer.method)}<br>신뢰도 {html.escape(level)}: {html.escape(answer.confidence.reason)}</div>',
    }


LIVE_CSS = """
:root{--paper:#E7EAEE;--panel:#F6F7F9;--ink:#171C22;--sub:#5C6875;--line:#CDD3DA;--mark:#A8741A;--markbg:rgba(176,122,30,.13);--bad:#B3261E;--sig:#2C5F8A;
--bg:var(--paper);--card:var(--panel);--vp1:#27303A;--vp2:#11151A;--vink:#E8ECF0;--vsub:#9BA7B3;--vline:#3A444F;--glow:#F2B544;
--p-bolt:#CBD3DC;--p-plate1:#5F7F9D;--p-plate2:#6E917E;--zone:#B78CF2}
@media (prefers-color-scheme:dark){:root{--paper:#0E1216;--panel:#161B21;--ink:#E8ECF0;--sub:#96A2AE;--line:#2A323B;--mark:#E0A93B;--markbg:rgba(224,169,59,.14);--bad:#F0857C;--sig:#7FB2E0;--vp1:#222A33;--vp2:#0B0E12}}
html,body{height:100%}body{background:var(--paper);color:var(--ink);overflow-x:hidden;font-family:"Segoe UI Variable Text","Segoe UI","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;letter-spacing:-.005em}
.app{max-width:1280px;margin:0 auto;padding:18px 20px 28px;display:grid;grid-template-columns:minmax(0,1.7fr) minmax(300px,1fr);gap:22px;align-items:start}
@media (max-width:900px){.app{grid-template-columns:1fr;padding:12px 12px 24px;gap:16px}}
/* ---- 무대: 어두운 작업 화면 ---- */
.stage{--ink:var(--vink);--sub:var(--vsub);--line:var(--vline);--bg:#1A2027;--card:#1A2027;--band:#2B4055;--sig:#8FC1EE;--ok:#7FD0A0;--okbg:#27433A;--bad:#FF8A7A;--mark:var(--glow);
color:var(--vink);background:radial-gradient(120% 90% at 50% 30%,var(--vp1),var(--vp2));border-radius:18px;position:relative;overflow:hidden;
display:flex;flex-direction:column;box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 18px 40px -22px rgba(10,14,18,.55)}
.tabs{display:flex;gap:2px;padding:12px 12px 0;position:relative;z-index:3}
.tabs button{font:inherit;font-size:13.5px;color:var(--vsub);background:transparent;border:0;border-bottom:2px solid transparent;padding:6px 12px 8px;cursor:pointer;position:relative}
.tabs button[aria-selected=true]{color:var(--vink);border-bottom-color:var(--vink);font-weight:600}.tabs button:hover{color:var(--vink)}
.tabs button:focus-visible{outline:2px solid var(--glow);outline-offset:2px;border-radius:4px}
.tabs button.new::after{content:"";position:absolute;right:3px;top:6px;width:7px;height:7px;border-radius:50%;background:var(--glow)}
.vp{position:relative;height:min(58vh,540px);min-height:340px}
.pane{position:absolute;inset:0;display:none;padding:6px 16px 0}.pane.on{display:block;animation:slide .32s ease}@keyframes slide{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
@media (max-width:900px){.vp{height:auto;min-height:0}.pane{position:static;padding:6px 10px 0}#pane-shape{position:relative}}
#pane-shape{padding:0}.pane canvas{width:100%;height:100%;display:block;touch-action:none;cursor:grab}@media (max-width:900px){.pane canvas{aspect-ratio:1/1;height:auto}}
.pane canvas:focus-visible{outline:2px solid var(--glow);outline-offset:-3px;border-radius:14px}
.pane .fcap{color:var(--vsub);font-size:12.5px;line-height:1.55;margin-top:4px}.pane .fcap b{color:var(--vink);font-weight:600}#pane-field{color:var(--vink);overflow:auto}
.pane .swap{transition:opacity .28s;max-width:640px;margin:0 auto}.pane .swap.out{opacity:0}.pane .cap{color:var(--vsub);font-size:12.5px;max-width:640px;margin:2px auto 0}
.cap i{display:inline-block;width:18px;border-top:2px dashed var(--glow);vertical-align:middle;margin-right:5px}
/* 3D 위의 이름표: 바뀐 부품에 붙는다 */
.tag{position:absolute;left:0;top:0;pointer-events:none;z-index:2;display:flex;align-items:center;gap:0;opacity:0;transition:opacity .4s}
.tag.on{opacity:1}.tag.flip{flex-direction:row-reverse}.tag::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--glow);box-shadow:0 0 0 4px rgba(242,181,68,.25);flex:none}
.tag i{width:26px;border-top:1px solid var(--glow);flex:none}.tag span{background:rgba(14,18,22,.82);border:1px solid rgba(242,181,68,.55);color:#F7E3B5;font-size:12.5px;padding:3px 9px;border-radius:6px;white-space:nowrap}
.notes{position:absolute;right:12px;top:48px;z-index:2;display:grid;gap:6px;justify-items:end;pointer-events:none}
.notes div{background:rgba(14,18,22,.82);border:1px solid rgba(242,181,68,.55);color:#F7E3B5;font-size:12.5px;padding:3px 9px;border-radius:6px;animation:rise .4s ease}
.hint{position:absolute;left:16px;top:8px;right:150px;color:var(--vsub);font-size:12px;z-index:1}.hint a{color:var(--vink)}
.xr{position:absolute;right:12px;top:8px;z-index:3;font:inherit;font-size:12.5px;color:var(--vink);background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.16);border-radius:999px;padding:4px 12px 4px 30px;cursor:pointer}
.xr::before{content:"";position:absolute;left:10px;top:50%;width:12px;height:12px;margin-top:-6px;border-radius:50%;border:2px solid var(--vsub)}.xr[aria-pressed=true]{border-color:var(--zone);color:#fff}.xr[aria-pressed=true]::before{background:var(--zone);border-color:var(--zone)}
.xr:focus-visible{outline:2px solid var(--glow);outline-offset:2px}
.key{position:absolute;left:16px;bottom:10px;z-index:2;font-size:12px;color:var(--vsub);display:none;max-width:min(360px,calc(100% - 32px))}.xray .key{display:block}.badge{display:none}.xray .badge{display:block}
.key .sc{position:relative;height:8px;border-radius:4px;margin:5px 0 3px;background:linear-gradient(90deg,#4C7DF0,#46C2A5 50%,#F2C94C 80%,#F0524A)}.key .sc i{position:absolute;top:-4px;bottom:-4px;width:2px;background:#fff;box-shadow:0 0 0 1px rgba(0,0,0,.5);transition:left .7s cubic-bezier(.2,.7,.2,1)}
.key .ends{display:flex;justify-content:space-between}.key b{color:var(--vink);font-weight:600}.key .z{margin-top:6px}.key .z i{display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--zone);vertical-align:-1px;margin-right:5px}
/* ---- 말과 답 ---- */
.talk{padding:8px 14px 14px;position:relative;z-index:4}
.said{text-align:right;min-height:0;font-size:13px;color:var(--vsub);height:0;position:relative}
.said span{position:absolute;right:0;bottom:10px;z-index:5;background:rgba(255,255,255,.08);border-radius:12px 12px 3px 12px;padding:4px 11px;animation:fly 3.2s ease forwards;white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
@keyframes fly{0%{opacity:0;transform:translateY(8px)}12%{opacity:1;transform:none}70%{opacity:1}100%{opacity:0;transform:translateY(-22px)}}
#reply{position:relative}
.reply{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.09);border-radius:12px;padding:10px 14px 9px;margin-bottom:10px;animation:rise .4s ease;position:relative}
.reply.gone{animation:leave .45s ease forwards}@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}@keyframes leave{to{opacity:0;transform:translateY(-16px)}}
.reply .hl{font-weight:600;font-size:15.5px;padding-right:30px;line-height:1.4}.reply .al{margin-top:4px;font-weight:600}.reply .al.low{color:#FF8A7A}
.reply .x{position:absolute;right:6px;top:5px;font:inherit;border:0;background:transparent;color:var(--vsub);cursor:pointer;padding:3px 8px;border-radius:6px}.reply .x:hover{color:var(--vink)}.reply .x:focus-visible{outline:2px solid var(--glow)}
.chips{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px}.chip{font-size:13px;color:var(--vsub);animation:rise .45s ease backwards}
.chip b{font-size:16px;font-weight:600;color:var(--vink);font-variant-numeric:tabular-nums}.chip .was{text-decoration:line-through;margin:0 4px 0 6px;font-variant-numeric:tabular-nums}
.chip.spot{color:#F7E3B5}.chip.spot b{color:var(--glow)}.chip:nth-child(2){animation-delay:.07s}.chip:nth-child(3){animation-delay:.14s}.chip:nth-child(4){animation-delay:.21s}
.opt{display:grid;gap:6px;margin-top:9px}.opt button,.ex button{font:inherit;text-align:left;color:var(--vink);background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:8px 12px;cursor:pointer}
.opt button:hover,.ex button:hover{border-color:var(--glow)}.opt button:focus-visible,.ex button:focus-visible{outline:2px solid var(--glow);outline-offset:1px}.opt .d{color:var(--vsub);font-size:12.5px;margin-left:6px}
.ex{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.ex button{font-size:13px;padding:5px 12px;border-radius:999px}
.reply .more{margin-top:6px;font-size:12.5px}.reply .more summary{cursor:pointer;color:var(--vsub)}.reply .more pre{white-space:pre-wrap;font:inherit;color:var(--vsub);margin:6px 0 0;max-height:150px;overflow:auto;scrollbar-color:#4A5561 transparent;scrollbar-width:thin}
#say{display:flex;gap:8px}#say input{flex:1;min-width:0;font:inherit;font-size:16px;color:var(--vink);background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:11px 14px}
#say input::placeholder{color:var(--vsub)}#say button{font:inherit;font-weight:600;color:#12161B;background:var(--vink);border:0;border-radius:10px;padding:10px 18px;cursor:pointer}
#say button:hover{background:#fff}#say input:focus-visible,#say button:focus-visible{outline:2px solid var(--glow);outline-offset:2px}#say button[disabled]{opacity:.5;cursor:default}
/* ---- 오른쪽: 읽는 값 ---- */
.rail{display:grid;gap:18px;padding-top:6px;align-content:start}
.st{display:inline-block;font-size:11.5px;font-weight:600;border-radius:4px;padding:1px 7px;margin-left:8px;vertical-align:1px;background:var(--line);color:var(--ink)}
.st.h{background:rgba(122,82,199,.14);color:#6A44B8}.st.c{background:var(--markbg);color:var(--mark)}@media (prefers-color-scheme:dark){.st.h{background:rgba(183,140,242,.18);color:var(--zone)}}
.core{border-top:1px solid var(--line)}.core .c{padding:12px 0 11px 12px;border-bottom:1px solid var(--line);position:relative}
.core .c::before{content:"";position:absolute;left:0;top:10px;bottom:10px;width:3px;border-radius:2px;background:transparent;transition:background .4s}.core .c.moved::before{background:var(--mark)}
.core .k{font-size:13.5px;color:var(--sub)}.core .v{font-size:34px;font-weight:350;font-variant-numeric:tabular-nums;letter-spacing:-.025em;line-height:1.15;margin-top:2px}.core .v.low{color:var(--bad)}
.core .u{font-size:14px;color:var(--sub);margin-left:6px;font-weight:400;letter-spacing:0}.core .rg{font-size:12.5px;color:var(--sub)}.core .dl{font-size:12.5px;color:var(--mark);font-variant-numeric:tabular-nums}.core .dl:empty{display:none}
.acc{border-bottom:1px solid var(--line)}.acc:first-of-type{border-top:1px solid var(--line)}.acc>summary{cursor:pointer;padding:11px 0;font-size:14px;font-weight:600;list-style:none;display:flex;align-items:center;gap:0;position:relative}
.acc>summary::-webkit-details-marker{display:none}.acc>summary::after{content:"";margin-left:auto;width:8px;height:8px;border-right:2px solid var(--sub);border-bottom:2px solid var(--sub);transform:rotate(45deg);transition:transform .2s;margin-right:4px}
.acc[open]>summary::after{transform:rotate(-135deg)}.acc>summary:focus-visible{outline:2px solid var(--sig);outline-offset:2px}.acc>summary .d{font-weight:400;color:var(--sub);font-size:12.5px;margin-left:8px}
.acc>summary.new::before{content:"";position:absolute;left:-12px;top:50%;width:7px;height:7px;margin-top:-4px;border-radius:50%;background:var(--mark)}
.acc .why{font-size:12.5px;color:var(--sub);margin:0 0 8px;line-height:1.55}.acc .read{border-top:1px solid var(--line);margin-bottom:10px}.acc .read .r:last-child{border-bottom:0}.acc .gauges{padding-bottom:10px}
.tr{display:grid;grid-template-columns:86px 1fr;gap:6px 12px;font-size:13px;padding:0 0 12px;line-height:1.5}.tr dt{color:var(--sub)}.tr dd{margin:0}
.badge{position:absolute;right:12px;bottom:10px;z-index:2;font-size:12px;color:var(--vsub);background:rgba(14,18,22,.7);border:1px solid var(--vline);border-radius:6px;padding:3px 9px}.badge b{color:var(--vink);font-weight:600}
.sen{border-top:1px solid var(--line);padding:11px 0 2px}.sen .sh{font-size:14px;font-weight:600}.sen .sst{display:block;font-size:12px;font-weight:600;color:var(--mark);margin-bottom:1px}
.sen .swhy{font-size:12.5px;color:var(--sub);margin:4px 0 8px;line-height:1.55}.sgs{display:grid;gap:5px;margin-bottom:9px}
.sg{display:grid;grid-template-columns:1fr auto;gap:0 10px;font-size:13px;align-items:baseline}.sg b{font-weight:600;font-variant-numeric:tabular-nums}.sg b i{font-style:normal;font-weight:400;color:var(--sub);font-size:12px}
.sg em{grid-column:1/-1;font-style:normal;font-size:12px;color:var(--sub)}
.chain{display:flex;flex-wrap:wrap;align-items:center;gap:5px 0;font-size:12.5px;margin-bottom:9px}.chain span:not(.ar){border:1px solid var(--line);border-radius:5px;padding:2px 7px}
.chain .ar{width:14px;height:1px;background:var(--sub);position:relative;margin:0 3px}.chain .ar::after{content:"";position:absolute;right:0;top:-3px;border-left:5px solid var(--sub);border-top:3.5px solid transparent;border-bottom:3.5px solid transparent}
.opt .cand{font-size:12px;color:var(--vsub);margin-bottom:2px}
.name{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.name h1{font-size:44px;line-height:1;margin:0;font-weight:650;letter-spacing:-.03em;font-family:"Segoe UI Variable Display","Segoe UI","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
.name .g{font-size:15px;color:var(--sub)}.name .g b{color:var(--ink);font-weight:600}.rail .sub{font-size:13px;color:var(--sub);margin-top:6px}
.read{border-top:1px solid var(--line)}.read .r{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:10px;padding:7px 0 6px 12px;border-bottom:1px solid var(--line);position:relative}
.read .r::before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:3px;border-radius:2px;background:transparent;transition:background .4s}.read .r.moved::before{background:var(--mark)}
.read .k{font-size:13.5px;color:var(--sub)}.read .v{font-size:22px;font-weight:400;font-variant-numeric:tabular-nums;letter-spacing:-.02em;line-height:1.1;text-align:right}
.read .u{font-size:13px;color:var(--sub);margin-left:5px;font-weight:400;letter-spacing:0}.read .rg{grid-column:1/-1;text-align:right;font-size:12px;color:var(--sub);margin-top:-2px}.read .rg:empty{display:none}.read .dl:empty{display:none}
.read .dl{grid-column:1/-1;text-align:right;font-size:12.5px;color:var(--mark);min-height:0;font-variant-numeric:tabular-nums;margin-top:-2px}
.gauges h2{font-size:13.5px;font-weight:600;margin:0 0 4px;color:var(--ink)}.gauges h2 span{font-weight:400;color:var(--sub)}
.row{display:grid;grid-template-columns:92px 1fr 52px;gap:10px;align-items:center;font-size:13.5px;padding:7px 0 7px 12px;position:relative}
.row::before{content:"";position:absolute;left:0;top:7px;bottom:7px;width:3px;border-radius:2px;background:transparent;transition:background .4s}.row.moved::before{background:var(--mark)}
.row .bar{position:relative;height:6px;background:var(--line);border-radius:3px}
.row .fill{position:absolute;left:0;top:0;bottom:0;background:var(--sig);border-radius:3px;transition:width .7s cubic-bezier(.2,.7,.2,1),background .4s}.row .fill.low{background:var(--bad)}
.row .one{position:absolute;top:-5px;bottom:-5px;width:2px;background:var(--ink)}.row .was{position:absolute;top:-6px;bottom:-6px;width:0;border-left:2px dashed var(--mark);display:none}.row.moved .was{display:block}
.row .n{text-align:right;font-weight:600;font-variant-numeric:tabular-nums}.row .n.low{color:var(--bad)}.row.off{color:var(--sub)}.row.off .bar{opacity:.4}
.legend2{font-size:12px;color:var(--sub);margin-top:6px;padding-left:12px}.legend2 i{display:inline-block;width:0;height:11px;border-left:2px dashed var(--mark);vertical-align:middle;margin:0 5px 0 0}
.detail{grid-column:1/-1;border-top:1px solid var(--line);padding-top:4px}.detail summary{cursor:pointer;color:var(--sub);font-size:13.5px;padding:8px 0}.detail summary:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.detail h3{font-size:14px;margin:14px 0 6px}.detail table{background:var(--panel)}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01s!important;transition-duration:.01s!important}}
"""

LIVE_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('live-data').textContent),S=D.states,cur=null,idx=0;
var $=function(q,r){return (r||document).querySelector(q)},reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion:reduce)').matches;
function esc(t){var d=document.createElement('div');d.textContent=t==null?'':String(t);return d.innerHTML;}
function fmt(v,d){return v==null?'-':Number(v).toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d});}
function tween(ms,step,done){if(reduce||ms<=0){step(1);if(done)done();return;}var t0=performance.now();(function f(now){var k=Math.min(1,(now-t0)/ms),e=1-Math.pow(1-k,3);step(e);if(k<1)requestAnimationFrame(f);else if(done)done();})(t0);}
function css(v){return getComputedStyle(document.documentElement).getPropertyValue(v).trim();}
function hex(v){var h=css(v).replace('#','');if(h.length===3)h=h.replace(/./g,'$&$&');var n=parseInt(h,16);return [(n>>16&255)/255,(n>>8&255)/255,(n&255)/255];}
var COLOR={bolt_head:'--p-bolt',bolt_shank:'--p-bolt',nut:'--p-bolt',plate_head:'--p-plate1',plate_nut:'--p-plate2',zone:'--zone'};
var RAMP=[[0,[0.30,0.49,0.94]],[0.5,[0.27,0.76,0.65]],[0.8,[0.95,0.79,0.30]],[1,[0.94,0.32,0.29]]];
function ramp(u){u=Math.max(0,Math.min(1,u));for(var i=1;i<RAMP.length;i++){if(u<=RAMP[i][0]){var a=RAMP[i-1],b=RAMP[i],k=(u-a[0])/(b[0]-a[0]);return [a[1][0]+(b[1][0]-a[1][0])*k,a[1][1]+(b[1][1]-a[1][1])*k,a[1][2]+(b[1][2]-a[1][2])*k];}}return RAMP[3][1];}

/* ---------- 3D 보기: 꼭짓점이 옛 자리에서 새 자리로 옮겨 가고, 바뀐 부품은 잠깐 빛난다 ---------- */
var V=(function(){var cv=$('#cv'),box=$('#pane-shape'),gl=cv.getContext('webgl',{antialias:true,alpha:true});
if(!gl){$('#cvmsg').textContent='이 브라우저에서는 3D 보기를 쓸 수 없습니다. "단면"을 눌러 주세요.';cv.style.display='none';return {set:function(){},draw:function(){},mark:function(){},hidden:function(){}};}
function sh(t,s){var o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);return o;}
var pr=gl.createProgram();
gl.attachShader(pr,sh(gl.VERTEX_SHADER,'attribute vec3 p;attribute vec3 n;uniform mat3 r;uniform vec3 c;uniform float s;uniform float a;varying float l;varying float g;void main(){vec3 q=r*((p-c)*s);vec3 m=normalize(r*n);vec3 L=normalize(vec3(0.35,0.6,0.72));l=0.30+0.70*max(dot(m,L),0.0);g=pow(max(dot(m,normalize(L+vec3(0.0,0.0,1.0))),0.0),26.0);gl_Position=vec4(q.x/a,q.y,-q.z*0.5,1.0);}'));
gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,'precision mediump float;uniform vec3 k;uniform float sp;uniform float al;varying float l;varying float g;void main(){gl_FragColor=vec4((k*l+vec3(g*sp))*al,al);}'));
gl.linkProgram(pr);gl.useProgram(pr);var U={};['r','c','s','a','k','sp','al'].forEach(function(x){U[x]=gl.getUniformLocation(pr,x)});
var ap=gl.getAttribLocation(pr,'p'),an=gl.getAttribLocation(pr,'n'),bp=gl.createBuffer(),bn=gl.createBuffer();
function normals(t){var n=new Float32Array(t.length);for(var i=0;i<t.length;i+=9){var ux=t[i+3]-t[i],uy=t[i+4]-t[i+1],uz=t[i+5]-t[i+2],vx=t[i+6]-t[i],vy=t[i+7]-t[i+1],vz=t[i+8]-t[i+2],x=uy*vz-uz*vy,y=uz*vx-ux*vz,z=ux*vy-uy*vx,q=Math.sqrt(x*x+y*y+z*z)||1;for(var j=0;j<9;j+=3){n[i+j]=x/q;n[i+j+1]=y/q;n[i+j+2]=z/q;}}return n;}
var now=null,yaw0=-0.785,pitch0=0.36,yaw=yaw0,pitch=pitch0,zoom=1.0,glow={},tags=[],raf=0,R=[1,0,0,0,1,0,0,0,1],W=1,H=1,xray=true,use=0;
function project(p){var x=(p[0]-now.center[0])*zoom/now.radius,y=(p[1]-now.center[1])*zoom/now.radius,z=(p[2]-now.center[2])*zoom/now.radius;
var qx=R[0]*x+R[3]*y+R[6]*z,qy=R[1]*x+R[4]*y+R[7]*z;return [(qx/(W/H)*0.5+0.5)*cv.clientWidth,(1-(qy*0.5+0.5))*cv.clientHeight];}
function draw(){raf=0;if(!now)return;W=cv.clientWidth*devicePixelRatio|0;H=cv.clientHeight*devicePixelRatio|0;if(!W||!H)return;if(cv.width!==W||cv.height!==H){cv.width=W;cv.height=H;}
gl.viewport(0,0,W,H);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
var cy=Math.cos(yaw),sy=Math.sin(yaw),cp=Math.cos(pitch),sp=Math.sin(pitch);R=[cy,sp*sy,-cp*sy,-sy,sp*cy,-cp*cy,0,cp,sp];
gl.uniformMatrix3fv(U.r,false,new Float32Array(R));gl.uniform3fv(U.c,now.center);gl.uniform1f(U.s,zoom/now.radius);gl.uniform1f(U.a,W/H);
var t=performance.now(),busy=false,gc=hex('--glow');
/* 숨은 물리 보기: 판을 비쳐 보이게 하고, 판이 눌리는 영역을 드러내고, 볼트를 등가응력 ÷ 항복강도로 칠한다 */
function paint(p,alpha){var plate=p.role.indexOf('plate')===0,bolt=p.role==='bolt_head'||p.role==='bolt_shank'||p.role==='nut';
var base=(xray&&bolt)?ramp(use):hex(COLOR[p.role]||'--p-bolt'),w=0;if(glow[p.role]){var age=(t-glow[p.role])/2600;if(age<1){w=(1-age)*(0.55+0.45*Math.cos(age*18));w=Math.max(0,w)*0.9;busy=true;}else delete glow[p.role];}
gl.uniform3fv(U.k,[base[0]+(gc[0]-base[0])*w,base[1]+(gc[1]-base[1])*w,base[2]+(gc[2]-base[2])*w]);gl.uniform1f(U.sp,plate||p.role==='zone'?0.10:0.38);gl.uniform1f(U.al,alpha);
gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,p.tri,gl.DYNAMIC_DRAW);gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,3,gl.FLOAT,false,0,0);
gl.bindBuffer(gl.ARRAY_BUFFER,bn);gl.bufferData(gl.ARRAY_BUFFER,normals(p.tri),gl.DYNAMIC_DRAW);gl.enableVertexAttribArray(an);gl.vertexAttribPointer(an,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.TRIANGLES,0,p.tri.length/3);}
var solid=now.parts.filter(function(p){return p.role.indexOf('plate')!==0&&(xray||p.role!=='zone');}),plates=now.parts.filter(function(p){return p.role.indexOf('plate')===0;});
gl.disable(gl.BLEND);gl.depthMask(true);solid.forEach(function(p){paint(p,1);});
if(xray){gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);plates.forEach(function(p){paint(p,0.2);});gl.depthMask(true);gl.disable(gl.BLEND);}else plates.forEach(function(p){paint(p,1);});
tags.forEach(function(g){var p=now.parts.filter(function(x){return x.role===g.role;})[0];if(!p)return;var q=project(p.anchor);var flip=q[0]+g.el.offsetWidth>cv.clientWidth-6;g.el.classList.toggle('flip',flip);g.el.style.transform='translate('+Math.round(flip?q[0]-g.el.offsetWidth+4:q[0]-4)+'px,'+Math.round(q[1]-12)+'px)';});
if(busy&&!reduce)ask();}
function ask(){if(!raf)raf=requestAnimationFrame(draw);}
function pack(d){return {center:d.center.slice(),radius:d.radius,parts:d.parts.map(function(p){return {role:p.role,anchor:p.anchor.slice(),tri:new Float32Array(p.tri)};})};}
function set(d,animate){var to=pack(d),from=now;
var same=from&&from.parts.length===to.parts.length&&from.parts.every(function(p,i){return p.tri.length===to.parts[i].tri.length;});
if(!animate||!same){now=to;draw();return;}
var a=pack({center:from.center,radius:from.radius,parts:from.parts.map(function(p){return {role:p.role,anchor:p.anchor,tri:Array.prototype.slice.call(p.tri)};})});
now=from;tween(800,function(e){for(var i=0;i<3;i++)now.center[i]=a.center[i]+(to.center[i]-a.center[i])*e;now.radius=a.radius+(to.radius-a.radius)*e;
now.parts.forEach(function(p,i){var x=a.parts[i].tri,y=to.parts[i].tri,t=p.tri;for(var j=0;j<t.length;j++)t[j]=x[j]+(y[j]-x[j])*e;for(var k=0;k<3;k++)p.anchor[k]=a.parts[i].anchor[k]+(to.parts[i].anchor[k]-a.parts[i].anchor[k])*e;});draw();},function(){now=to;draw();});}
function mark(m){tags.forEach(function(g){if(g.el.parentNode)g.el.parentNode.removeChild(g.el);});tags=[];glow={};var t=performance.now();
(m.glow||[]).forEach(function(r){glow[r]=t;});
(m.tags||[]).forEach(function(g){var el=document.createElement('div');el.className='tag';el.innerHTML='<i></i><span>'+esc(g.text)+'</span>';box.appendChild(el);tags.push({role:g.role,el:el});setTimeout(function(){el.classList.add('on');},500);});
$('#notes').innerHTML=(m.notes||[]).map(function(x){return '<div>'+esc(x)+'</div>';}).join('');ask();}
function clamp(){pitch=Math.max(-1.5,Math.min(1.5,pitch));zoom=Math.max(0.4,Math.min(6,zoom));}
var last=null;cv.addEventListener('pointerdown',function(e){last=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId);cv.style.cursor='grabbing';});
cv.addEventListener('pointermove',function(e){if(!last)return;yaw-=(e.clientX-last[0])*0.01;pitch+=(e.clientY-last[1])*0.01;last=[e.clientX,e.clientY];clamp();draw();});
function up(){last=null;cv.style.cursor='grab';}cv.addEventListener('pointerup',up);cv.addEventListener('pointercancel',up);
cv.addEventListener('wheel',function(e){e.preventDefault();zoom*=e.deltaY<0?1.1:0.9;clamp();draw();},{passive:false});
cv.addEventListener('keydown',function(e){var k=e.key,d=0.1;if(k==='ArrowLeft')yaw+=d;else if(k==='ArrowRight')yaw-=d;else if(k==='ArrowUp')pitch-=d;else if(k==='ArrowDown')pitch+=d;else if(k==='+'||k==='=')zoom*=1.1;else if(k==='-')zoom*=0.9;else return;e.preventDefault();clamp();draw();});
window.addEventListener('resize',draw);
function hidden(on,u){xray=on;use=u;box.classList.toggle('xray',on);draw();}
return {set:set,draw:draw,mark:mark,hidden:hidden};})();

$('#xr').addEventListener('click',function(){var on=this.getAttribute('aria-pressed')!=='true';this.setAttribute('aria-pressed',on?'true':'false');V.hidden(on,cur?cur.hidden.use:0);});
document.querySelectorAll('.acc').forEach(function(a){a.addEventListener('toggle',function(){if(a.open)$('summary',a).classList.remove('new');});});
/* ---------- 보기 바꾸기. 내용이 바뀐 보기에는 점이 붙고, 열어 보면 없어진다 ---------- */
var tabs=document.querySelectorAll('.tabs button');
function open(b){tabs.forEach(function(x){x.setAttribute('aria-selected',x===b?'true':'false');});b.classList.remove('new');
document.querySelectorAll('.pane').forEach(function(p){p.classList.toggle('on',p.id==='pane-'+b.dataset.v);});if(b.dataset.v==='shape')V.draw();}
tabs.forEach(function(b){b.addEventListener('click',function(){open(b);});});
function dot(v,on){var b=$('.tabs button[data-v="'+v+'"]');if(b)b.classList.toggle('new',on&&b.getAttribute('aria-selected')!=='true');}

/* ---------- 상태를 화면에 반영 ---------- */
function show(s,animate){
var prev=cur;cur=s;
$('#size').textContent=s.size;$('#grade').textContent=s.grade;$('#sub').textContent=s.sub;
s.core.forEach(function(t,i){var el=$('#core'+i),v=$('.num',el),old=prev?prev.core[i]:null,from=old&&old.value!=null?old.value:t.value,ch=animate&&old&&t.value!=null&&fmt(from,t.digits)!==fmt(t.value,t.digits);
$('.k span',el).textContent=t.label;$('.rg',el).textContent=t.range;$('.v',el).classList.toggle('low',!!t.low);el.classList.toggle('moved',!!ch);
$('.dl',el).textContent=ch?((t.value>from?'▲ ':'▼ ')+fmt(Math.abs(t.value-from),t.digits)+' (이전 '+fmt(from,t.digits)+')'):'';
if(t.value==null)v.textContent='-';else if(ch)tween(750,function(e){v.textContent=fmt(from+(t.value-from)*e,t.digits);});else v.textContent=fmt(t.value,t.digits);});
$('#sensing').innerHTML=s.sensing;
$('#trust').innerHTML=s.trust.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join('');var tb=$('#truth');if(tb)tb.textContent=s.truth_line||'';
s.tiles.forEach(function(t,i){var el=$('#tile'+i),v=$('.num',el),dl=$('.dl',el),from=prev?prev.tiles[i].value:t.value,ch=animate&&prev&&fmt(from,t.digits)!==fmt(t.value,t.digits);
$('.rg',el).textContent=t.range||'';el.classList.toggle('moved',!!ch);dl.textContent=ch?((t.value>from?'▲ ':'▼ ')+fmt(Math.abs(t.value-from),t.digits)+' (이전 '+fmt(from,t.digits)+')'):'';
if(ch)tween(750,function(e){v.textContent=fmt(from+(t.value-from)*e,t.digits);});else v.textContent=fmt(t.value,t.digits);});
var top=Math.max.apply(null,s.safety.map(function(x){return x.value||0;}).concat(prev?prev.safety.map(function(x){return x.value||0;}):[]).concat([2]))*1.05;
s.safety.forEach(function(x,i){var r=$('#sf'+i),f=$('.fill',r),n=$('.n',r),was=$('.was',r),old=prev?prev.safety[i].value:null;
r.classList.toggle('off',x.value==null);r.title=x.value==null?x.note:'';
var ch=animate&&old!=null&&x.value!=null&&fmt(old,2)!==fmt(x.value,2);r.classList.toggle('moved',!!ch);if(ch)was.style.left=(Math.min(old/top,1)*100)+'%';
$('.one',r).style.left=(100/top)+'%';f.style.width=(x.value==null?0:Math.min(x.value/top,1)*100)+'%';f.classList.toggle('low',x.value!=null&&x.value<1);n.classList.toggle('low',x.value!=null&&x.value<1);
if(x.value==null)n.textContent='-';else if(ch)tween(750,function(e){n.textContent=fmt(old+(x.value-old)*e,2);});else n.textContent=fmt(x.value,2);});
['section','diagram','torque','field'].forEach(function(k){var box=$('#pane-'+k+' .swap'),ch=animate&&prev&&prev.views[k]!==s.views[k];dot(k,!!ch);
if(ch){box.classList.add('out');setTimeout(function(){box.innerHTML=s.views[k];box.classList.remove('out');},280);}else box.innerHTML=s.views[k];});
V.hidden($('#xr').getAttribute('aria-pressed')==='true',s.hidden.use);$('#useat').style.left=(Math.min(s.hidden.use,1)*100)+'%';$('#usev').textContent=fmt(s.hidden.use,2);$('#usedet').textContent=fmt(s.hidden.stress,0)+' ÷ '+fmt(s.hidden.yield,0)+' MPa';
V.set(s.viewer,animate&&!!prev);V.mark(animate?s.marks:{glow:[],tags:[],notes:[]});dot('shape',animate&&s.marks.glow.length>0);
$('#more').innerHTML=s.more;
document.querySelectorAll('.acc').forEach(function(a){$('summary',a).classList.toggle('new',!a.open&&!!a.querySelector('.moved'));});
if(s.brief)reply(s);
}
/* ---------- 말과 답: 앞의 답은 날아가고 새 답이 올라온다 ---------- */
function reply(s){var b=s.brief,area=$('#reply'),old=area.firstElementChild;
if(old){old.classList.add('gone');setTimeout(function(){if(old.parentNode)old.parentNode.removeChild(old);},460);}
$('#said').innerHTML=b.said?'<span>'+esc(b.said)+'</span>':'';
var h='<button type="button" class="x" aria-label="답 닫기">✕</button><div class="hl">'+esc(b.headline)+'</div>'+(b.alert?'<div class="al'+(b.alert_low?' low':'')+'">'+esc(b.alert)+'</div>':'');
if(b.chips.length)h+='<div class="chips">'+b.chips.map(function(c){return '<div class="chip'+(c.spot?' spot':'')+'">'+esc(c.label)+'<span class="was">'+fmt(c.from,c.digits)+'</span><b>'+fmt(c.to,c.digits)+'</b>'+(c.unit?' '+esc(c.unit):'')+' '+(c.dir==='up'?'▲':'▼')+'</div>';}).join('')+'</div>';
if(b.options.length)h+='<div class="opt"><div class="cand">생성 후보 (검증 전): 같은 계산식으로 구한 대안입니다.</div>'+b.options.map(function(o){return '<button type="button" data-say="'+esc(o.say)+'"><b>'+o.n+'번</b> '+esc(o.what)+'<span class="d">'+esc(o.detail)+'</span></button>';}).join('')+'</div>';
if(b.examples.length)h+='<div class="ex">'+b.examples.map(function(x){return '<button type="button" data-say="'+esc(x)+'">'+esc(x)+'</button>';}).join('')+'</div>';
if(s.detail)h+='<details class="more"><summary>자세히</summary><pre>'+esc(s.detail)+'</pre></details>';
var el=document.createElement('div');el.className='reply';el.innerHTML=h;setTimeout(function(){area.appendChild(el);},old?240:0);
function away(){if(!el.parentNode)return;el.classList.add('gone');setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el);},460);}
el.querySelector('.x').addEventListener('click',away);
/* 고를 것이 없는 답은 읽을 시간이 지나면 스스로 날아간다. 마우스를 올리거나 '자세히'를 열면 머문다. 바뀐 곳의 표시는 다음 말까지 남는다 */
if(!b.options.length&&!b.examples.length&&!b.alert_low){var keep=false;el.addEventListener('pointerenter',function(){keep=true;});el.addEventListener('focusin',function(){keep=true;});
setTimeout(function(){if(!keep)away();},D.linger_ms);}
}
/* ---------- 말 보내기 (서버) 또는 미리 만든 차례 (파일) ---------- */
var form=$('#say'),input=$('#say input'),btn=$('#say button');
function send(text){if(!D.ask_url||!text)return;input.disabled=btn.disabled=true;$('#said').innerHTML='<span>'+esc(text)+'</span>';
fetch(D.ask_url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text})}).then(function(r){return r.json();})
.then(function(s){show(s,true);}).catch(function(){$('#reply').innerHTML='<div class="reply"><div class="al low">답을 받지 못했습니다. 서버가 켜져 있는지 확인해 주세요.</div></div>';})
.then(function(){input.disabled=btn.disabled=false;input.value='';input.focus();});}
function next(){if(idx+1<S.length){idx++;show(S[idx],true);}btn.textContent=idx+1<S.length?'다음':'처음부터';if(idx+1>=S.length)btn.dataset.end='1';}
form.addEventListener('submit',function(e){e.preventDefault();if(D.ask_url){send(input.value.trim());return;}
if(btn.dataset.end){delete btn.dataset.end;idx=0;$('#reply').innerHTML='';$('#said').innerHTML='';cur=null;show(S[0],false);btn.textContent='다음';input.value=S[1]?S[1].brief.said:'';return;}
next();input.value=S[idx+1]?S[idx+1].brief.said:'';});
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-say]');if(!b)return;if(D.ask_url)send(b.dataset.say);});
show(S[0],false);
if(!D.ask_url){input.readOnly=true;input.value=S[1]?S[1].brief.said:'';btn.textContent=S.length>1?'다음':'끝';if(S.length<2)btn.disabled=true;}
document.body.dataset.ready='1';
})();
"""


def render_live(states: Sequence[dict[str, Any]], ask_url: str | None = None, title: str = "볼트 조인트 체결 계산",
                downloads: Sequence[tuple[str, str]] = ()) -> str:
    """states: state()의 결과들. ask_url이 있으면 말을 받아 그 자리에서 바뀌고(서버), 없으면 states를 차례로 보여 준다(파일)."""
    if not states:
        raise ValueError("at least one state is required")
    e = html.escape
    first = states[0]
    def row(i: int, t: dict[str, Any]) -> str:
        return (f'<div class="r" id="tile{i}"><div class="k">{e(t["label"])}</div><div class="v"><span class="num"></span><span class="u">{e(t["unit"])}</span></div>'
                f'<div class="rg"></div><div class="dl"></div></div>')

    why = {"hidden": '<p class="why">조임 토크는 잴 수 있지만, 그 토크가 만든 체결력은 직접 잴 수 없습니다. 마찰에 따라 달라지기 때문입니다. '
                     "아래는 관측으로 복원한 값이 아니라 계산 모형으로 구한 값입니다.</p>",
           "seen": '<p class="why">지금은 센서로 관측한 값이 아니라 사람이 넣은 값입니다.</p>'}
    groups = "".join(f'<details class="acc" id="acc-{key}"><summary>{e(name)}<span class="st{" h" if key == "hidden" else ""}">{e(status)}</span>'
                     f'<span class="d">{e(desc)}</span></summary>{why.get(key, "")}<div class="read">'
                     + "".join(row(i, t) for i, t in enumerate(first["tiles"]) if t["group"] == key) + "</div></details>" for key, name, status, desc in GROUPS)
    core = "".join(f'<div class="c" id="core{i}"><div class="k"><span></span><span class="st{" h" if "숨은" in c["status"] else ""}">{e(c["status"])}</span></div>'
                   f'<div class="v"><span class="num"></span><span class="u">{e(c["unit"])}</span></div><div class="rg"></div><div class="dl"></div></div>'
                   for i, c in enumerate(first["core"]))
    rows = "".join(f'<div class="row" id="sf{i}"><div>{e(s["label"])}</div><div class="bar"><div class="fill"></div><div class="was"></div><div class="one"></div></div>'
                   f'<div class="n"></div></div>' for i, s in enumerate(first["safety"]))
    files = (' 형상 파일 받기: ' + ", ".join(f'<a href="{e(u)}" download>{e(n)}</a>' for n, u in downloads)) if downloads else ""
    hint = "말로 바꿔 보세요. 예: M12로 바꾸고 토크 80으로" if ask_url else "미리 만든 대화입니다. '다음'을 누르면 한 마디씩 진행됩니다"
    data = json.dumps({"states": list(states), "ask_url": ask_url, "linger_ms": LINGER_MS}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    ghost = '<div class="cap"><i></i>점선은 바꾸기 전입니다.</div>'
    body = f"""<div class="app">
<div class="stage">
<div class="tabs" role="tablist" aria-label="보기">
<button type="button" role="tab" data-v="shape" aria-selected="true">3D 형상</button><button type="button" role="tab" data-v="section" aria-selected="false">단면</button>
<button type="button" role="tab" data-v="diagram" aria-selected="false">체결 선도</button><button type="button" role="tab" data-v="torque" aria-selected="false">토크와 체결력</button>
<button type="button" role="tab" data-v="field" aria-selected="false">응력 분포</button></div>
<div class="vp">
<div class="pane on" id="pane-shape"><canvas id="cv" tabindex="0" role="img" aria-label="볼트 조인트 3D 형상. 끌거나 화살표 키로 돌리고 휠이나 +, - 키로 확대합니다"></canvas>
<button type="button" class="xr" id="xr" aria-pressed="true">숨은 물리 보기</button>
<div class="notes" id="notes" aria-live="polite"></div><div class="hint"><span id="cvmsg"></span>끌어서 돌리고 휠로 확대합니다.{files}</div>
<div class="key"><div>볼트의 색: 등가응력 ÷ 항복강도 <b id="usev"></b> <span id="usedet"></span></div><div class="sc"><i id="useat"></i></div><div class="ends"><span>0</span><span>1.0</span></div>
<div class="z"><i></i>판이 눌리는 영역. VDI 2230의 계산 모형이며 해석(FEM) 결과가 아닙니다.</div></div>
<div class="badge">숨은 물리 <b>해석</b> · 관측 없음 · <b>검증 전</b></div></div>
<div class="pane" id="pane-section"><div class="swap"></div>{ghost}</div>
<div class="pane" id="pane-diagram"><div class="swap"></div>{ghost}</div>
<div class="pane" id="pane-torque"><div class="swap"></div>{ghost}</div>
<div class="pane" id="pane-field"><div class="swap"></div></div>
</div>
<div class="talk"><div class="said" id="said" aria-live="polite"></div><div id="reply" aria-live="polite"></div>
<form id="say"><input type="text" aria-label="바꿀 내용" placeholder="{e(hint)}" autocomplete="off"><button type="submit">보내기</button></form></div>
</div>
<div class="rail">
<div><div class="name"><h1 id="size"></h1><div class="g">강도 등급 <b id="grade"></b></div></div><div class="sub" id="sub"></div></div>
<div class="core">{core}</div>
<div>{groups}
<details class="acc" id="acc-safety"><summary>결과: 안전율<span class="st">해석</span><span class="d">검은 선이 1.0</span></summary>
<div class="gauges">{rows}<div class="legend2"><i></i>점선은 바꾸기 전 값입니다.</div></div></details>
<details class="acc" id="acc-trust"><summary>이 결과를 믿어도 되는가<span class="st c">검증 전</span></summary><dl class="tr" id="trust"></dl></details>
<details class="acc" id="acc-sensing"><summary>현장에서 재려면: 센서와 연결<span class="st">추천</span></summary><div id="sensing"></div></details></div>
</div>
<details class="detail"><summary>자세히: 물리, 수학·조건</summary><div id="more"></div></details>
</div>
<script type="application/json" id="live-data">{data}</script><script>{LIVE_JS}</script>"""
    return (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{e(title)}</title><style>{CSS}{EXTRA_CSS}{LIVE_CSS}{FIELD_CSS}</style></head><body>\n{body}\n</body></html>")
