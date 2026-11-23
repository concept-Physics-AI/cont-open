"""목록의 샘플. 손으로 그린 그림이 아니라, 엔진을 조건마다 실제로 돌린 결과다.

함수 하나 = 상품 하나의 샘플들. 샘플: {"label": 조건 이름, "html": 그림이나 글, "facts": [(이름, 값)], "params": 만든 조건}.
숫자는 모두 엔진이 낸 값이다. 규격별 샘플의 조임 토크는 추천 엔진이 고른다 (목록의 sample_rule).
"""
from __future__ import annotations

import html
import re
from dataclasses import replace
from functools import lru_cache
from typing import Any, Callable, Mapping

W, H = 320, 190
Sample = dict[str, Any]


def _svg(text: str) -> str:
    m = re.search(r"<svg.*?</svg>", text, re.S)
    return m.group(0) if m else ""


def _rule() -> dict[str, Any]:
    from cont.fab.catalog import load
    return load()["rule"]


@lru_cache(maxsize=64)
def joint_for(size: str, torque: float | None = None) -> dict[str, Any]:
    """예제 조인트에서 규격을 바꾸고 조임 토크를 정한 것. torque가 없으면 추천 엔진이 예시 목표를 만족하는 토크를 고른다."""
    from cont.dialogue.fastening_chat import Session
    from cont.dialogue.serve_fastening import example
    from cont.packs.fastening.pack import answer
    from cont.view.fastening_live import state
    s = Session(*example())
    if size != s.joint.size:
        t = s.say(f"{size}로 바꿔")
        if t.kind != "changed":
            raise ValueError(f"{size}: {t.reply}")
    if torque is None:
        s.say(f"항복 안전율 {_rule()['yield_safety']:g} 이상이 되게 해 줘")
        if s.offers:
            s.say("1번으로")                                  # 가장 적게 바꾸는 추천 (대개 토크만)
    else:
        s.load = replace(s.load, tightening_torque=float(torque)); s.answer = answer(s.joint, s.load)
    j, l, a = s.joint, s.load, s.answer
    return {"joint": j, "load": l, "answer": a, "state": state(j, l, a), "label": f"{j.size} · {l.tightening_torque:g} N·m",
            "params": {"size": j.size, "torque": l.tightening_torque}}


def _sizes(item: Mapping[str, Any]) -> list[str]:
    return list((item.get("samples") or {}).get("sizes") or ["M10"])


def _each(item: Mapping[str, Any], make: Callable[[dict[str, Any]], tuple[str, list[tuple[str, str]]]], params: Mapping[str, Any] | None) -> list[Sample]:
    cases = [joint_for(params["size"], params.get("torque"))] if params else []
    if not params:
        for size in _sizes(item):
            try:
                cases.append(joint_for(size))
            except Exception:                                 # 그 규격으로 계산이 안 되면 샘플을 내지 않는다
                continue
    out = []
    for f in cases:
        body, facts = make(f)
        out.append({"label": f["label"], "html": body, "facts": facts, "params": f["params"]})
    return out


def _line(points: list[tuple[float, float]], xlabel: str, ylabel: str, marks: tuple[tuple[float, str], ...] = (), yfmt: str = ",.0f") -> str:
    """작은 꺾은선 그림 (값은 넘겨받은 것 그대로). marks: (가로 값, 이름) 세로 점선."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y1 = min(xs), max(xs) or 1.0, max(max(ys), 0.0) or 1.0
    y0 = min(min(ys), 0.0)
    px = lambda x: 44 + (x - x0) / ((x1 - x0) or 1.0) * (W - 60)
    py = lambda y: H - 30 - (y - y0) / ((y1 - y0) or 1.0) * (H - 52)
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in points)
    extra = "".join(f'<line class="ax" stroke-dasharray="4 3" x1="{px(m):.1f}" y1="22" x2="{px(m):.1f}" y2="{H - 30}"/>'
                    f'<text class="tick" x="{px(m) + 4:.1f}" y="32">{html.escape(t)}</text>' for m, t in marks)
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(ylabel)} 대 {html.escape(xlabel)}">'
            f'<line class="ax" x1="44" y1="{py(0):.1f}" x2="{W - 16}" y2="{py(0):.1f}"/><line class="ax" x1="44" y1="22" x2="44" y2="{H - 30}"/>{extra}'
            f'<polyline class="sig" points="{pts}"/>'
            f'<text class="tick" x="44" y="{H - 10}">{x0:.3g}</text><text class="tick" x="{W - 16}" y="{H - 10}" text-anchor="end">{html.escape(xlabel)} {x1:.3g}</text>'
            f'<text class="tick" x="44" y="14">{html.escape(ylabel)} · 최대 {format(max(ys), yfmt)}</text></svg>')


def fastening_section(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.view.iso_svg import iso_svg

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        j = f["joint"]
        return iso_svg(f["state"]["viewer"], label=f"{j.size} 볼트 조인트 3D"), [("규격", f"{j.size} · {j.property_class}"), ("판", f"{j.plate_head.thickness:g} + {j.plate_nut.thickness:g} mm")]
    return _each(item, make, params)


def fastening_hidden(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.view.iso_svg import iso_svg

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        h = f["state"]["hidden"]
        return (iso_svg(f["state"]["viewer"], hidden=True, use=h["use"], label="숨은 물리 3D"),
                [("볼트 응력 ÷ 항복강도", f"{h['use']:.2f}"), ("운전 시 등가응력", f"{h['stress']:,.0f} MPa")])
    return _each(item, make, params)


def fastening_drawing(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        j = f["joint"]
        return _svg(f["state"]["views"]["section"]), [("체결 길이", f"{j.clamp_length:g} mm"), ("바깥지름", f"{j.outer_diameter:g} mm")]
    return _each(item, make, params)


def fastening_field(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.fastening.field import stress_field
    from cont.view.field_image import field_image
    key = item.get("field", "plate_axial_compression")

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        j, a = f["joint"], stress_field(f["joint"], f["load"])
        fld = next(x for x in a.fields if x.key == key)
        vals = [v for row in fld.values for v in row if v is not None]
        unit = fld.unit
        img = field_image(a, key, lines=((j.plate_nut.thickness, "판 사이 면"),))
        return img, [("가장 큰 값", f"{max(vals):,.1f} {unit}"), ("건 체결력", f"{a.value('preload'):,.0f} N")]
    return _each(item, make, params)


def interface_pressure(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.fastening.field import stress_field

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        j, a = f["joint"], stress_field(f["joint"], f["load"])
        fld = next(x for x in a.fields if x.key == "plate_axial_compression")
        t = j.plate_nut.thickness
        below = max(k for k, y in enumerate(fld.y) if y < t); above = below + 1          # 판 사이 면의 바로 아래 줄과 위 줄
        pts = [(x, (fld.values[below][i] + fld.values[above][i]) / 2) for i, x in enumerate(fld.x)
               if fld.values[below][i] is not None and fld.values[above][i] is not None]
        r = a.value("pressed_radius")
        return (_line(pts, "반지름 (mm)", "압력 (MPa)", marks=((r, "눌리는 반지름"),)),
                [("최대 압력", f"{a.value('interface_peak_pressure'):,.0f} MPa"), ("눌리는 반지름", f"{r:.1f} mm")])
    return _each(item, make, params)


def fastening_safety(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        rows = [x for x in f["state"]["safety"] if x["value"] is not None]
        top = max(max(x["value"] for x in rows), 2.0) * 1.05
        bars = ""
        for k, x in enumerate(rows):
            y = 16 + k * 27; w = x["value"] / top * (W - 150)
            bars += (f'<text class="tick" x="8" y="{y + 12}">{html.escape(x["label"])}</text><rect class="bar{" low" if x["value"] < 1 else ""}" x="100" y="{y}" width="{w:.1f}" height="14" rx="3"/>'
                     f'<text class="tick" x="{104 + w:.1f}" y="{y + 12}">{x["value"]:.2f}</text>')
        one = 100 + 1.0 / top * (W - 150)
        svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="안전율 막대">{bars}<line class="ax" stroke-dasharray="4 3" x1="{one:.1f}" y1="8" x2="{one:.1f}" y2="{H - 8}"/>'
               f'<text class="tick" x="{one + 3:.1f}" y="{H - 4}">1.0</text></svg>')
        low = min(rows, key=lambda x: x["value"])
        return svg, [("가장 낮은 안전율", f"{low['value']:.2f} ({low['label']})")]
    return _each(item, make, params)


def fastening_estimate(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.fastening.estimate import ElongationMeasurement, estimate, synthetic_elongations
    ex = item["example"]

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        j, l = f["joint"], f["load"]
        values = synthetic_elongations(j, l, float(ex["true_friction"]), float(ex["noise_um"]) / 1000.0, int(ex["count"]))
        est = estimate(j, l, ElongationMeasurement(values, float(ex["instrument_um"]) / 1000.0, "합성 관측"))
        rows = [("추정 체결력", f"{est.preload:,.0f} N"), ("범위", f"{est.preload_range[0]:,.0f} ~ {est.preload_range[1]:,.0f} N"),
                ("추정 마찰계수", f"{est.friction:.3f}")]
        body = '<dl class="nums">' + "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>" for k, v in rows) + "</dl>"
        return body, [("합성 관측", f"{len(values)}번 · 평균 {sum(values) / len(values) * 1000:.0f} µm")]
    return _each(item, make, params)


def _frames(f: dict[str, Any], n: int) -> list[dict[str, Any]]:
    from cont.packs.fastening.process import tightening
    frames = tightening(f["joint"], f["load"])
    last = len(frames) - 1
    return [frames[round(last * k / n)] for k in range(1, n + 1)]


def fastening_process(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.view.iso_svg import iso_svg

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        picks = _frames(f, int(_rule()["process_frames"]))
        cells = "".join(f'<figure>{iso_svg(f["state"]["viewer"], 150, 150, use=x["use"], label="조이는 과정의 한 장면")}'
                        f'<figcaption>{x["torque"]:.1f} N·m</figcaption></figure>' for x in picks)
        end = picks[-1]
        return f'<div class="strip">{cells}</div>', [("끝", f"{end['torque']:.1f} N·m → {end['preload']:,.0f} N"), ("조립 시 응력 ÷ 항복강도", f"{end['use']:.2f}")]
    return _each(item, make, params)


def fastening_video(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.fastening.process import settings
    from cont.view.iso_svg import iso_svg

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        first, end = _frames(f, 4)[0], _frames(f, 4)[-1]
        cells = "".join(f'<figure>{iso_svg(f["state"]["viewer"], 150, 150, use=x["use"], label="영상의 한 장면")}<figcaption>{t}</figcaption></figure>'
                        for x, t in ((first, "처음"), (end, "끝")))
        return f'<div class="strip two">{cells}</div>', [("길이", f"약 {settings()['play_seconds']:g}초"), ("끝", f"{end['torque']:g} N·m → {end['preload']:,.0f} N")]
    return _each(item, make, params)


def fastening_diagram(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        a = f["answer"]
        return _svg(f["state"]["views"]["diagram"]), [("조립 체결력", f"{a.value('preload'):,.0f} N"), ("항복 안전율", f"{a.value('safety_yield'):.2f}")]
    return _each(item, make, params)


def fastening_torque(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        a = f["answer"]
        return _svg(f["state"]["views"]["torque"]), [("조임 토크", f"{f['load'].tightening_torque:g} N·m"), ("조립 체결력", f"{a.value('preload'):,.0f} N")]
    return _each(item, make, params)


def fastening_sensing(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.fastening.sensing import plan

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        p = plan(f["joint"], f["load"])
        rows = "".join(f'<li><b>{html.escape(o.stage)}</b> {html.escape(o.label)}</li>' for o in p.options[:3])
        return f'<ol class="steps">{rows}</ol>', [("추천 단계", f"{len(p.options)}가지"), ("예상 볼트 늘어남", f"{p.elongation * 1000:.0f} µm")]
    return _each(item, make, params)


@lru_cache(maxsize=1)
def _plants() -> list[tuple[Any, Any]]:
    """가상 설비 둘 (절삭 설비, 계통 넷인 설비)과 그 특화 해석."""
    from cont.dialogue.serve_diagnosis import synthetic_cutting
    from cont.packs.diagnosis.demo import synthetic_equipment
    cut, it = synthetic_cutting()
    return [(cut, it), (synthetic_equipment(), None)]


def signal_module(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    """계통 하나(구동계, 압력·유동계, 열관리계, 동작 사이클)의 신호들."""
    from cont.view.diagnosis_html import _chart
    out: list[Sample] = []
    for eq, _ in _plants():
        for s in eq.systems:
            d = s.diagnosis
            if d.module.name != item["module"]:
                continue
            for r in d.signals:
                peak = max((abs(iv.peak_z) for iv in r.intervals), default=None)
                out.append({"label": f"{r.label} · {s.name}", "html": _chart(r, d.time, d.settings.z_limit), "params": {},
                            "facts": [("가상 설비", eq.equipment), ("가장 크게 벗어난 정도", "범위 안" if peak is None else f"정상 산포의 {peak:.1f}배")], "_found": peak is not None})
    out.sort(key=lambda x: not x["_found"])                    # 벗어난 것이 있는 신호를 앞에
    return [{k: v for k, v in x.items() if k != "_found"} for x in out]


def trend_heat(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.diagnosis.trend import trend
    from cont.view.diagnosis_html import _trend
    out: list[Sample] = []
    for eq, _ in _plants():
        if len(eq.systems) < 2:
            continue
        tr = trend(eq)
        out.append({"label": eq.equipment, "html": _svg(_trend(tr)), "params": {}, "facts": [("가상 설비", eq.equipment), ("계통", f"{len(eq.systems)}개")]})
    return out


def cutting_curve(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs import get
    base = dict(item["example"]); spec = item.get("samples") or {}
    out: list[Sample] = []
    for m in spec.get("materials") or [base["material"]]:
        pts = []
        for feed in spec["feeds"]:
            a = get("machining").solve({"cut": {**base, "material": m, "feed": feed}})
            pts.append((float(feed), next(q.value for q in a.quantities if q.unit == "N" and q.value is not None)))
        out.append({"label": m, "html": _line(pts, "이송 (mm/rev)", "주절삭력 (N)"), "params": {},
                    "facts": [("조건", f"지름 {base['diameter']:g} mm · 절입 {base['depth']:g} mm"), ("이송 범위", f"{pts[0][0]:g} ~ {pts[-1][0]:g} mm/rev")]})
    return out


def guidance(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.diagnosis.report import report
    e = html.escape
    out: list[Sample] = []
    for eq, it in _plants():
        for c in report(eq, it):
            cand = c.candidates[0].text.split(". ")[0] if c.candidates else "지식표에 후보가 없습니다"
            body = (f'<dl class="three"><dt>관찰 사실</dt><dd>{e(c.observed.text)}</dd><dt>원인 후보</dt><dd>{e(cand)}</dd>'
                    f'<dt>다음 점검</dt><dd>{e(c.checks[0].text) if c.checks else "지식표에 항목이 없습니다"}</dd></dl>')
            out.append({"label": f"{c.title} · {c.system}", "html": body, "params": {}, "facts": [("가상 설비", eq.equipment), ("점검 항목", f"{len(c.checks)}가지")]})
    return out[: int((item.get("samples") or {}).get("max", len(out)))]


def _special(index: int) -> list[Sample]:
    from cont.packs.diagnosis.demo import synthetic_special
    from cont.view.diagnosis_html import _chart
    s = synthetic_special()[index]; r, t, z = s.charts[0]
    return [{"label": s.heading.split(": ")[-1], "html": _chart(r, t, z), "params": {}, "facts": [("가상 데이터", s.verdict)]}]


def stroke_curve(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    return _special(1)


def quality_prediction(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    return _special(2)


def cutting_force(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs import get
    base = dict(item["example"]); spec = item.get("samples") or {}
    out: list[Sample] = []
    for m in spec.get("materials") or [base["material"]]:
        for feed in spec.get("feeds") or [base["feed"]]:
            cut = {**base, "material": m, "feed": feed}
            a = get("machining").solve({"cut": cut})
            rows = [(q.label, f"{q.value:,.0f} {q.unit}") for q in a.quantities if q.unit in ("N", "N·m", "kW", "W") and q.value is not None][:3]
            body = '<dl class="nums">' + "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>" for k, v in rows) + "</dl>"
            out.append({"label": f"{m} · 이송 {feed:g} mm/rev", "html": body, "params": {},
                        "facts": [("조건", f"지름 {cut['diameter']:g} mm · 절입 {cut['depth']:g} mm · {cut['cutting_speed']:g} m/min")]})
    return out


PREVIEWS: dict[str, Callable[..., list[Sample]]] = {f.__name__: f for f in (
    fastening_section, fastening_hidden, fastening_drawing, fastening_field, interface_pressure, fastening_process, fastening_video, fastening_diagram,
    fastening_torque, fastening_safety, fastening_estimate, fastening_sensing, signal_module, trend_heat, guidance, stroke_curve, quality_prediction,
    cutting_force, cutting_curve)}
# 조건을 받아 그 자리에서 다시 만들 수 있는 것 (규격과 조임 토크)
MAKEABLE = ("fastening_section", "fastening_hidden", "fastening_drawing", "fastening_field", "interface_pressure", "fastening_process", "fastening_video",
            "fastening_diagram", "fastening_torque", "fastening_safety", "fastening_estimate", "fastening_sensing")
