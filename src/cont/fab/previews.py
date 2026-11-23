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


def _line(points: list[tuple[float, float]], xlabel: str, ylabel: str) -> str:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x1, y1 = max(xs) or 1.0, max(ys) or 1.0
    px = lambda x: 44 + x / x1 * (W - 60)
    py = lambda y: H - 30 - y / y1 * (H - 52)
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in points)
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(ylabel)} 대 {html.escape(xlabel)}">'
            f'<line class="ax" x1="44" y1="{H - 30}" x2="{W - 16}" y2="{H - 30}"/><line class="ax" x1="44" y1="22" x2="44" y2="{H - 30}"/>'
            f'<polyline class="sig" points="{pts}"/><circle cx="{px(xs[-1]):.1f}" cy="{py(ys[-1]):.1f}" r="4" class="dot"/>'
            f'<text class="tick" x="{W - 16}" y="{H - 10}" text-anchor="end">{html.escape(xlabel)} {xs[-1]:g}</text>'
            f'<text class="tick" x="44" y="14">{html.escape(ylabel)} {ys[-1]:,.0f}</text></svg>')


def fastening_section(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.view.iso_svg import iso_svg

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        j = f["joint"]
        return iso_svg(f["state"]["viewer"], label=f"{j.size} 볼트 조인트 3D"), [("규격", f"{j.size} · {j.property_class}"), ("판", f"{j.plate_head.thickness:g} + {j.plate_nut.thickness:g} mm")]
    return _each(item, make, params)


def fastening_field(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.packs.fastening.field import stress_field

    def make(f: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
        a = stress_field(f["joint"], f["load"])
        return _svg(f["state"]["views"]["field"]), [("판 사이 면의 최대 압력", f"{a.value('interface_peak_pressure'):,.0f} MPa"), ("눌리는 반지름", f"{a.value('pressed_radius'):.1f} mm")]
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


def signal_baseline(item: Mapping[str, Any], params: Mapping[str, Any] | None = None) -> list[Sample]:
    from cont.view.diagnosis_html import _chart
    out: list[Sample] = []
    for eq, _ in _plants():
        for s in eq.systems:
            d = s.diagnosis
            for r in d.signals:
                peak = max((abs(iv.peak_z) for iv in r.intervals), default=None)
                out.append({"label": f"{s.name} · {r.label}", "html": _chart(r, d.time, d.settings.z_limit), "params": {},
                            "facts": [("가상 설비", eq.equipment), ("가장 크게 벗어난 정도", "범위 안" if peak is None else f"정상 산포의 {peak:.1f}배")], "_found": peak is not None})
    out.sort(key=lambda x: not x["_found"])                    # 벗어난 것이 있는 신호를 앞에
    limit = int((item.get("samples") or {}).get("max", len(out)))
    return [{k: v for k, v in x.items() if k != "_found"} for x in out[:limit]]


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
    fastening_section, fastening_field, fastening_process, fastening_video, fastening_diagram, fastening_torque, fastening_sensing, signal_baseline, guidance,
    stroke_curve, quality_prediction, cutting_force)}
# 조건을 받아 그 자리에서 다시 만들 수 있는 것 (규격과 조임 토크)
MAKEABLE = ("fastening_section", "fastening_field", "fastening_process", "fastening_video", "fastening_diagram", "fastening_torque", "fastening_sensing")
