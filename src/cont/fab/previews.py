"""목록의 미리보기. 손으로 그린 그림이 아니라, 엔진을 예제 값으로 실제로 돌린 결과다.

함수 하나 = 미리보기 하나. {"html": 그림이나 글, "facts": [(이름, 값)]}을 돌려준다. 숫자는 모두 엔진이 낸 값이다.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache
from typing import Any, Callable

W, H = 320, 190


def _svg(text: str) -> str:
    m = re.search(r"<svg.*?</svg>", text, re.S)
    return m.group(0) if m else ""


@lru_cache(maxsize=1)
def _fastening() -> dict[str, Any]:
    from cont.dialogue.serve_fastening import example
    from cont.packs.fastening.pack import answer
    from cont.view.fastening_live import state
    j, l = example()
    a = answer(j, l)
    return {"joint": j, "load": l, "answer": a, "state": state(j, l, a)}


@lru_cache(maxsize=1)
def _special() -> list[Any]:
    from cont.packs.diagnosis.demo import synthetic_special
    return synthetic_special()


def _line(points: list[tuple[float, float]], xlabel: str, ylabel: str) -> str:
    """작은 꺾은선 그림 (값은 넘겨받은 것 그대로)."""
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


def fastening_section() -> dict[str, Any]:
    f = _fastening(); j = f["joint"]
    return {"html": _svg(f["state"]["views"]["section"]), "facts": [("예제", f"{j.size} · 강도 등급 {j.property_class}"), ("판", f"{j.plate_head.thickness:g} + {j.plate_nut.thickness:g} mm")]}


def fastening_field() -> dict[str, Any]:
    from cont.packs.fastening.field import stress_field
    f = _fastening(); a = stress_field(f["joint"], f["load"])
    return {"html": _svg(f["state"]["views"]["field"]), "facts": [("판 사이 면의 최대 압력", f"{a.value('interface_peak_pressure'):,.0f} MPa"),
                                                                   ("눌리는 반지름", f"{a.value('pressed_radius'):.1f} mm")]}


def fastening_process() -> dict[str, Any]:
    from cont.packs.fastening.process import tightening
    f = _fastening(); frames = tightening(f["joint"], f["load"])
    last = frames[-1]
    return {"html": _line([(x["torque"], x["preload"]) for x in frames], "조임 토크 (N·m)", "체결력 (N)"),
            "facts": [("나눈 칸", f"{len(frames) - 1}칸"), ("끝 값", f"{last['torque']:g} N·m → {last['preload']:,.0f} N")]}


def fastening_diagram() -> dict[str, Any]:
    f = _fastening(); a = f["answer"]
    return {"html": _svg(f["state"]["views"]["diagram"]), "facts": [("조립 체결력", f"{a.value('preload'):,.0f} N"), ("항복 안전율", f"{a.value('safety_yield'):.2f}")]}


def fastening_sensing() -> dict[str, Any]:
    from cont.packs.fastening.sensing import plan
    f = _fastening(); p = plan(f["joint"], f["load"])
    rows = "".join(f'<li><b>{html.escape(o.stage)}</b> {html.escape(o.label)}</li>' for o in p.options[:3])
    return {"html": f'<ol class="steps">{rows}</ol>', "facts": [("추천 단계", f"{len(p.options)}가지"), ("예상 볼트 늘어남", f"{p.elongation * 1000:.0f} µm")]}


def signal_baseline() -> dict[str, Any]:
    from cont.dialogue.serve_diagnosis import synthetic_cutting
    from cont.view.diagnosis_html import _chart
    eq, _ = synthetic_cutting(); d = eq.systems[0].diagnosis; r = d.signals[0]
    peak = max(abs(iv.peak_z) for iv in r.intervals)
    return {"html": _chart(r, d.time, d.settings.z_limit), "facts": [("가상 설비", f"{eq.systems[0].name} · {r.label}"), ("가장 크게 벗어난 정도", f"정상 산포의 {peak:.1f}배")]}


def guidance() -> dict[str, Any]:
    from cont.dialogue.serve_diagnosis import synthetic_cutting
    from cont.packs.diagnosis.report import report
    eq, it = synthetic_cutting(); c = report(eq, it)[0]
    e = html.escape
    body = (f'<dl class="three"><dt>관찰 사실</dt><dd>{e(c.observed.text)}</dd><dt>원인 후보</dt><dd>{e(c.candidates[0].text.split(". ")[0])}</dd>'
            f'<dt>다음 점검</dt><dd>{e(c.checks[0].text)}</dd></dl>')
    return {"html": body, "facts": [("점검 항목", f"{len(c.checks)}가지")]}


def stroke_curve() -> dict[str, Any]:
    from cont.view.diagnosis_html import _chart
    s = _special()[1]; r, t, z = s.charts[0]
    return {"html": _chart(r, t, z), "facts": [("가상 데이터", s.verdict)]}


def quality_prediction() -> dict[str, Any]:
    from cont.view.diagnosis_html import _chart
    s = _special()[2]; r, t, z = s.charts[0]
    return {"html": _chart(r, t, z), "facts": [("가상 데이터", s.verdict)]}


def cutting_force() -> dict[str, Any]:
    from cont.fab.catalog import load
    from cont.packs import get
    cut = next(i for i in load()["items"] if i["key"] == "cutting_force")["example"]
    a = get("machining").solve({"cut": cut})
    rows = [(q.label, f"{q.value:,.0f} {q.unit}") for q in a.quantities if q.unit in ("N", "N·m", "kW", "W") and q.value is not None][:3]
    body = '<dl class="nums">' + "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd>" for k, v in rows) + "</dl>"
    return {"html": body, "facts": [("예제", f"{cut['material']} · 지름 {cut['diameter']:g} mm · 절입 {cut['depth']:g} mm")]}


PREVIEWS: dict[str, Callable[[], dict[str, Any]]] = {f.__name__: f for f in (
    fastening_section, fastening_field, fastening_process, fastening_diagram, fastening_sensing, signal_baseline, guidance, stroke_curve,
    quality_prediction, cutting_force)}
