"""진단 결과 화면 (한 파일 HTML, 서버·외부 라이브러리 없음).

신호마다 실제 값, 같은 운전조건의 정상 범위, 이상 구간을 한 그림에 그린다.
"""
from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from cont.packs.diagnosis.equipment import EquipmentDiagnosis
from cont.packs.diagnosis.pack import Diagnosis, SignalResult

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 920, 220, 56, 14, 14, 30
MAX_POINTS = 900

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#17202b;--sub:#5b6776;--line:#d9dee6;--band:#dbe7f5;--sig:#1f5fae;--bad:#c8372d;--badbg:#fbe4e1;--ok:#1f7a4d;--okbg:#e2f3ea}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1a2029;--ink:#e8edf3;--sub:#9aa7b6;--line:#2c3542;--band:#24364d;--sig:#7fb2f0;--bad:#f0857c;--badbg:#3d2321;--ok:#6fcf9b;--okbg:#1c3327}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 18px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:26px 0 10px}.sub{color:var(--sub);font-size:13px}
.verdict{display:flex;gap:12px;align-items:center;padding:14px 16px;border-radius:10px;margin:16px 0;font-weight:600}
.verdict.bad{background:var(--badbg);color:var(--bad)}.verdict.ok{background:var(--okbg);color:var(--ok)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card .k{color:var(--sub);font-size:12px}.card .v{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}
.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 12px 6px;margin-bottom:12px}
.panel h3{font-size:14px;margin:0 0 2px}.tag{display:inline-block;font-size:12px;border-radius:999px;padding:1px 9px;margin-left:6px}
.tag.bad{background:var(--badbg);color:var(--bad)}.tag.ok{background:var(--okbg);color:var(--ok)}
svg{width:100%;height:auto;display:block}.ax{stroke:var(--line);stroke-width:1}.tick{fill:var(--sub);font-size:11px}
.band{fill:var(--band)}.sig{fill:none;stroke:var(--sig);stroke-width:1.3}.hit{fill:var(--bad);opacity:.16}.hitl{stroke:var(--bad);stroke-width:1}
ul{padding-left:20px;margin:6px 0}li{margin:4px 0}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:13.5px}td.n{text-align:right;font-variant-numeric:tabular-nums}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--sub);font-size:12px;margin:2px 0 6px}
.sw{display:inline-block;width:22px;height:9px;border-radius:2px;vertical-align:middle;margin-right:5px}
.sys{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:10px}
a.syscard{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:11px 13px}
a.syscard.bad{border-left-color:var(--bad)}a.syscard:hover{border-color:var(--sig)}a.syscard:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.syscard .nm{font-weight:650}.syscard .st{font-size:13px;margin-top:5px}.syscard.bad .st{color:var(--bad)}.syscard.ok .st{color:var(--ok)}
section.system{margin-top:30px;border-top:2px solid var(--line);padding-top:6px}section.system h2{font-size:18px}
.qa{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.qa .chips{display:flex;flex-wrap:wrap;gap:8px}.qa button{font:inherit;font-size:13.5px;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:5px 13px;cursor:pointer}
.qa button:hover,.qa button[aria-pressed=true]{border-color:var(--sig);color:var(--sig)}.qa button:focus-visible,.qa input:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.qa form{display:flex;gap:8px;margin-top:10px}.qa input{flex:1;min-width:0;font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 10px}
.qa .ans{margin-top:12px;white-space:pre-wrap;overflow-wrap:anywhere}.qa .ans:empty{display:none}.qa .src{color:var(--sub);font-size:12px;margin-top:6px}
.find{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--bad);border-radius:10px;padding:10px 14px;margin-bottom:8px}
.find .nm{font-weight:650;color:var(--bad)}.find .wh{color:var(--sub);font-size:12.5px}
.guide{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:8px}
.guide .nm{font-weight:650}.guide ol{margin:6px 0 2px;padding-left:22px}.guide .cause{color:var(--sub)}
.heat text{fill:var(--ink);font-size:12px}.heat .lab{fill:var(--sub);font-size:11px}.heat .c0{fill:var(--okbg)}.heat .c1{fill:var(--bad)}.heat .frame{fill:none;stroke:var(--line)}
.note{color:var(--sub);font-size:12.5px;margin-top:18px;border-top:1px solid var(--line);padding-top:10px}
"""


def _fmt(v: float | None) -> str:
    if v is None:
        return "-"
    if v == 0 or 0.01 <= abs(v) < 100000:
        return f"{v:,.3g}" if abs(v) < 100 else f"{v:,.0f}"
    return f"{v:.3g}"


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi <= lo:
        return [lo]
    step = 10 ** math.floor(math.log10((hi - lo) / n))
    for m in (1, 2, 5, 10):
        if (hi - lo) / (step * m) <= n + 1:
            step *= m
            break
    first = math.ceil(lo / step) * step
    return [first + i * step for i in range(int((hi - first) / step) + 1)]


def _chart(r: SignalResult, t: np.ndarray, z_limit: float) -> str:
    n = len(t)
    idx = np.unique(np.linspace(0, n - 1, min(n, MAX_POINTS)).astype(int))
    lo_b, hi_b = r.center - z_limit * r.scale, r.center + z_limit * r.scale
    ymin = float(min(r.value.min(), lo_b.min())); ymax = float(max(r.value.max(), hi_b.max()))
    span = (ymax - ymin) or 1.0
    ymin -= 0.06 * span; ymax += 0.06 * span
    t0, t1 = float(t[0]), float(t[-1]) if t[-1] > t[0] else float(t[0]) + 1.0

    def px(v: float) -> float:
        return PAD_L + (v - t0) / (t1 - t0) * (W - PAD_L - PAD_R)

    def py(v: float) -> float:
        return PAD_T + (ymax - v) / (ymax - ymin) * (H - PAD_T - PAD_B)

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(r.label)} 신호와 정상 범위">']
    for iv in r.intervals:
        x0, x1 = px(float(t[iv.start])), px(float(t[iv.end]))
        out.append(f'<rect class="hit" x="{x0:.1f}" y="{PAD_T}" width="{max(x1 - x0, 2):.1f}" height="{H - PAD_T - PAD_B}"/>')
    upper = " ".join(f"{px(float(t[i])):.1f},{py(float(hi_b[i])):.1f}" for i in idx)
    lower = " ".join(f"{px(float(t[i])):.1f},{py(float(lo_b[i])):.1f}" for i in idx[::-1])
    out.append(f'<polygon class="band" points="{upper} {lower}"/>')
    out.append('<polyline class="sig" points="' + " ".join(f"{px(float(t[i])):.1f},{py(float(r.value[i])):.1f}" for i in idx) + '"/>')
    out.append(f'<line class="ax" x1="{PAD_L}" y1="{H - PAD_B}" x2="{W - PAD_R}" y2="{H - PAD_B}"/>')
    for v in _ticks(ymin, ymax):
        out.append(f'<line class="ax" x1="{PAD_L - 4}" y1="{py(v):.1f}" x2="{PAD_L}" y2="{py(v):.1f}"/>'
                   f'<text class="tick" x="{PAD_L - 7}" y="{py(v) + 4:.1f}" text-anchor="end">{_fmt(v)}</text>')
    for v in _ticks(t0, t1, 6):
        out.append(f'<text class="tick" x="{px(v):.1f}" y="{H - PAD_B + 16}" text-anchor="middle">{_fmt(v)}</text>')
    out.append("</svg>")
    return "".join(out)


LEGEND = ('<div class="legend"><span><span class="sw" style="background:var(--sig)"></span>실제 값</span>'
          '<span><span class="sw" style="background:var(--band)"></span>같은 운전조건의 정상 범위</span>'
          '<span><span class="sw" style="background:var(--bad);opacity:.3"></span>이상 구간</span></div>')
LEVELS = {"low": "낮음", "medium": "중간", "high": "높음"}


def _panels(d: Diagnosis) -> str:
    e = html.escape; out = []
    for r in d.signals:
        tag = (f'<span class="tag bad">이상 {len(r.intervals)}건</span>' if r.intervals else '<span class="tag ok">정상 범위</span>')
        unit = f" ({e(r.unit)})" if r.unit else ""
        out.append(f'<div class="panel"><h3>{e(r.label)}{unit} <span class="sub">· {e(r.column)}</span>{tag}</h3>'
                   f'{_chart(r, d.time, d.settings.z_limit)}</div>')
    return "".join(out)


def _table(a) -> str:
    e = html.escape
    rows = "".join(f"<tr><td>{e(q.label)}</td><td class='n'>{_fmt(q.value)}</td><td>{e(q.unit)}</td><td>{e(q.note or '')}</td></tr>"
                   for q in a.quantities)
    return f"<table><thead><tr><th>항목</th><th>값</th><th>단위</th><th>비고</th></tr></thead><tbody>{rows}</tbody></table>"


def _page(title: str, body: str) -> str:
    return (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main>\n{body}\n</main></body></html>")


def _cards(cards: list[tuple[str, str]]) -> str:
    return '<div class="cards">' + "".join(f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in cards) + "</div>"


def render_diagnosis(d: Diagnosis, title: str = "설비 공통 이상진단", subtitle: str = "") -> str:
    """계통 하나의 진단 화면."""
    a = d.answer
    e = html.escape
    n_iv = sum(len(r.intervals) for r in d.signals)
    changes = [q for q in a.quantities if q.key.startswith("change_")]
    if n_iv:
        verdict = f'<div class="verdict bad">이상 징후 {n_iv}건: ' + ", ".join(e(q.label.split(" (")[0]) for q in changes) + "</div>"
    else:
        verdict = '<div class="verdict ok">모든 신호가 같은 운전조건의 정상 범위 안에 있습니다.</div>'
    first = a.get("first_anomaly_time").value
    level = LEVELS.get(a.confidence.level, a.confidence.level)
    cards = [("진단 모듈", e(d.module.title)), ("이상 구간", f"{n_iv}건"),
             ("첫 이상 시각", _fmt(first) if first is not None else "없음"),
             ("이상 구간 비율", f"{a.value('anomaly_fraction') * 100:.1f}%"), ("신뢰도", level)]
    basis = "".join(f"<li>{e(b)}</li>" for b in a.basis)
    q_html = f'<div class="sub">질문: {e(a.question)}</div>' if a.question else ""
    return _page(title, f"""<h1>{e(title)}</h1><div class="sub">{e(subtitle)}</div>{q_html}
{verdict}
{_cards(cards)}
<h2>신호와 정상 범위</h2>
{LEGEND}
{_panels(d)}
<h2>판단 근거</h2><ul>{basis}</ul>
<h2>물리량</h2>{_table(a)}
<div class="note">계산 방법: {e(a.method)}<br>신뢰도 {e(level)}: {e(a.confidence.reason)}</div>""")


QA_JS = """
(function(){var box=document.getElementById('qa');if(!box)return;var data=JSON.parse(document.getElementById('qa-data').textContent);
var ans=box.querySelector('.ans'),src=box.querySelector('.src'),btns=box.querySelectorAll('button[data-i]');
function show(t,s){ans.textContent=t;src.textContent=s;}
btns.forEach(function(b){b.addEventListener('click',function(){btns.forEach(function(x){x.setAttribute('aria-pressed','false')});
b.setAttribute('aria-pressed','true');var d=data.items[+b.dataset.i];show(d.text,d.source);});});
var f=box.querySelector('form');if(f){f.addEventListener('submit',function(ev){ev.preventDefault();var q=f.querySelector('input').value.trim();if(!q)return;
show('답을 만드는 중입니다…','');fetch(data.ask_url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})})
.then(function(r){return r.json()}).then(function(d){show(d.text,d.source);}).catch(function(){show('답을 받지 못했습니다. 진단 서버가 켜져 있는지 확인해 주세요.','');});});}
})();
"""


def _qa(qa: Sequence[tuple[str, str, str]], ask_url: str | None) -> str:
    """묻고 답하기 영역. qa: (질문, 답, 답의 출처 설명). ask_url이 있으면 직접 묻는 칸도 둔다 (진단 서버가 답한다)."""
    if not qa and not ask_url:
        return ""
    e = html.escape
    chips = "".join(f'<button type="button" data-i="{i}" aria-pressed="false">{e(q)}</button>' for i, (q, _, _) in enumerate(qa))
    form = ('<form><input type="text" aria-label="질문" placeholder="예: 유압 쪽은 언제부터 이상했나요?"><button type="submit">묻기</button></form>'
            if ask_url else "")
    data = json.dumps({"items": [{"text": t, "source": s} for _, t, s in qa], "ask_url": ask_url}, ensure_ascii=False).replace("</", "<\\/")
    hint = "질문을 누르면 진단 결과에서 만든 답이 나옵니다." + ("" if ask_url else " 직접 묻기는 진단 서버(python -m cont.dialogue.serve)에서 됩니다.")
    return (f'<h2>묻고 답하기</h2><div class="qa" id="qa"><div class="sub" style="margin-bottom:8px">{e(hint)}</div>'
            f'<div class="chips">{chips}</div>{form}<div class="ans" aria-live="polite"></div><div class="src"></div></div>'
            f'<script type="application/json" id="qa-data">{data}</script><script>{QA_JS}</script>')


TREND_WORD = {"worsening": "뒤로 갈수록 늘어남", "easing": "뒤로 갈수록 줄어듦", "steady": "비슷하게 이어짐", "normal": "정상"}


def _trend(tr: Any) -> str:
    """상태 추이: 계통(줄) × 진단 구간의 토막(칸). 칸이 진할수록 그 토막에서 벗어나 있던 시간이 길다."""
    if tr is None:
        return ""
    e = html.escape
    left, cw, rh, top, right = 150, (W - 150 - 190) / tr.windows, 26, 18, 190
    h = top + rh * len(tr.systems) + 6
    out = [f'<svg class="heat" viewBox="0 0 {W} {h}" role="img" aria-label="계통별 상태 추이">',
           f'<text class="lab" x="{left}" y="12">구간 처음</text><text class="lab" x="{W - right}" y="12" text-anchor="end">구간 끝</text>']
    for i, s in enumerate(tr.systems):
        y = top + i * rh
        out.append(f'<text x="0" y="{y + 17}">{e(s.name)}</text>')
        for j in range(tr.windows):
            f = float(s.fraction[j]); x = left + j * cw
            cell = (f'<rect class="c1" x="{x:.1f}" y="{y + 2}" width="{cw - 2:.1f}" height="{rh - 4}" rx="3" opacity="{0.25 + 0.75 * f:.2f}"/>' if f > 0
                    else f'<rect class="c0" x="{x:.1f}" y="{y + 2}" width="{cw - 2:.1f}" height="{rh - 4}" rx="3"/>')
            out.append(f'<g><title>{e(s.name)} · {j + 1}번째 토막 · 벗어난 비율 {f * 100:.0f}% · 최대 이탈 {float(s.peak[j]):.1f}배</title>{cell}</g>')
        out.append(f'<text class="lab" x="{W - right + 8}" y="{y + 17}">{TREND_WORD[s.direction]}</text>')
    out.append("</svg>")
    order = (" → ".join(e(n) for n in tr.order)) if tr.order else "없음"
    return (f'<h2>상태 추이</h2><div class="panel">{"".join(out)}<div class="sub" style="margin:4px 0 6px">진단 구간을 {tr.windows}토막으로 나눈 것입니다. '
            f'칸이 진할수록 그 토막에서 정상 범위를 벗어나 있던 시간이 깁니다. 이상이 시작된 순서: {order}</div></div>')


def _guidance(g: Any) -> str:
    """원인 후보와 점검 안내."""
    if g is None or not g.items:
        return ""
    e = html.escape
    blocks = []
    for i, it in enumerate(g.items):
        steps = "".join(f'<li>{"<span class=cause>" + e(c.cause) + "</span> → " if c.cause else ""}{e(c.check)}</li>' for c in it.candidates)
        tag = '<span class="tag bad">특화 해석</span>' if it.kind == "special" else ""
        blocks.append(f'<div class="guide"><div class="nm">{i + 1}. {e(it.system)}: {e(it.title)}{tag}</div>'
                      f'<div class="sub">{e(it.signal)} · {_fmt(it.start)}부터</div><ol>{steps or "<li>지식표에 항목이 없습니다</li>"}</ol></div>')
    return ('<h2>원인 후보와 점검 안내</h2>' + "".join(blocks) + '<div class="sub" style="margin-bottom:6px">먼저 시작된 변화부터, 확인하기 쉬운 것부터 '
            "늘어놓았습니다. 확률 순서가 아니며 원인을 판정한 것이 아닙니다. 일반적인 설비 지식으로 쓴 출발점입니다.</div>")


def _findings(findings: Sequence[Any], heading: str = "이 공정에서의 뜻 (특화 진단)") -> str:
    """특화 진단의 해석 결과. findings의 각 항목은 label, meaning, system, signal, start, onset을 가진다."""
    if not findings:
        return ""
    e = html.escape
    onset = {"abrupt": "갑자기", "gradual": "서서히"}
    items = "".join(f'<div class="find"><div class="nm">{e(f.label)}</div><div class="wh">{e(f.system)} · {e(f.signal)} · '
                    f'{_fmt(f.start)}부터 {onset.get(f.onset, f.onset)}</div><div>{e(f.meaning)}</div></div>' for f in findings)
    return (f'<h2>{e(heading)}</h2>{items}<div class="sub" style="margin-bottom:6px">일반적인 공정 지식으로 쓴 규칙의 결과입니다. '
            "점검할 곳을 좁히는 단서이며, 현장 기록으로 검증한 판정이 아닙니다.</div>")


@dataclass(frozen=True)
class Section:
    """특화 진단 화면의 한 부분."""
    heading: str
    sub: str
    ok: bool
    verdict: str
    answer: Any                                   # PhysicsAnswer
    charts: tuple[tuple[Any, Any, float], ...] = ()   # (SignalResult, 가로축 값, 범위 배수)
    band_label: str = "정상 범위"
    findings: tuple[Any, ...] = field(default_factory=tuple)


def render_special(sections: Sequence[Section], title: str = "설비 특화 이상진단", subtitle: str = "") -> str:
    """특화 진단 화면: 부분마다 결론, 공정 해석, 그림, 근거, 물리량."""
    e = html.escape
    nav = "".join(f'<a class="syscard {"ok" if s.ok else "bad"}" href="#sp{i + 1}"><div class="nm">{e(s.heading)}</div>'
                  f'<div class="sub">{e(s.sub)}</div><div class="st">{e(s.verdict)}</div></a>' for i, s in enumerate(sections))
    body = []
    for i, s in enumerate(sections):
        a = s.answer
        level = LEVELS.get(a.confidence.level, a.confidence.level)
        legend = ('<div class="legend"><span><span class="sw" style="background:var(--sig)"></span>값</span>'
                  f'<span><span class="sw" style="background:var(--band)"></span>{e(s.band_label)}</span>'
                  '<span><span class="sw" style="background:var(--bad);opacity:.3"></span>벗어난 구간</span></div>') if s.charts else ""
        panels = "".join(f'<div class="panel"><h3>{e(r.label)}{" (" + e(r.unit) + ")" if r.unit else ""}'
                         f'<span class="tag {"bad" if r.intervals else "ok"}">{"벗어남 " + str(len(r.intervals)) + "건" if r.intervals else "범위 안"}</span></h3>'
                         f'{_chart(r, x, zl)}</div>' for r, x, zl in s.charts)
        body.append(f'<section class="system" id="sp{i + 1}"><h2>{e(s.heading)} <span class="sub">· {e(s.sub)}</span></h2>'
                    f'<div class="verdict {"ok" if s.ok else "bad"}">{e(s.verdict)}</div>{_findings(s.findings, "공정 해석")}{legend}{panels}'
                    f'<h3>판단 근거</h3><ul>{"".join(f"<li>{e(b)}</li>" for b in a.basis)}</ul><h3>물리량</h3>{_table(a)}'
                    f'<div class="note">계산 방법: {e(a.method)}<br>신뢰도 {e(level)}: {e(a.confidence.reason)}</div></section>')
    return _page(title, f'<h1>{e(title)}</h1><div class="sub">{e(subtitle)}</div>\n<h2>한눈에 보기</h2><div class="sys">{nav}</div>\n{"".join(body)}')


def render_equipment(eq: EquipmentDiagnosis, title: str = "설비 공통 이상진단", subtitle: str = "",
                     qa: Sequence[tuple[str, str, str]] = (), ask_url: str | None = None, findings: Sequence[Any] = (),
                     guidance: Any = None, trend: Any = None) -> str:
    """설비 한 대의 진단 화면: 계통별 상태를 먼저 보이고, 계통마다 신호 그림과 근거를 잇는다."""
    a = eq.answer
    e = html.escape
    bad = [s for s in eq.systems if s.interval_count]
    if bad:
        verdict = (f'<div class="verdict bad">계통 {len(eq.systems)}개 가운데 {len(bad)}개에서 이상 징후: '
                   + ", ".join(e(s.name) for s in bad) + "</div>")
    else:
        verdict = f'<div class="verdict ok">계통 {len(eq.systems)}개 모두 같은 운전조건의 정상 범위 안에 있습니다.</div>'
    level = LEVELS.get(a.confidence.level, a.confidence.level)
    cards, sections = [], []
    for i, s in enumerate(eq.systems):
        d = s.diagnosis
        names = [q.label.split(" (")[0] for q in s.changes]
        first = d.answer.get("first_anomaly_time").value
        if s.interval_count:
            state = "이상 징후: " + ", ".join(names) if names else f"이상 구간 {s.interval_count}건"
            when = f'<div class="sub">첫 이상 {_fmt(first)} · 구간 {s.interval_count}건</div>'
        else:
            state, when = "정상 범위", f'<div class="sub">신호 {len(d.signals)}개 확인</div>'
        cls = "bad" if s.interval_count else "ok"
        cards.append(f'<a class="syscard {cls}" href="#sys{i + 1}"><div class="nm">{e(s.name)}</div>'
                     f'<div class="sub">{e(d.module.title)}</div><div class="st">{e(state)}</div>{when}</a>')
        found = [b for b in d.answer.basis if "→" in b]
        ev = ("<ul>" + "".join(f"<li>{e(b)}</li>" for b in found) + "</ul>") if found else \
            '<p class="sub">모든 신호가 같은 운전조건의 정상 범위 안에 있습니다.</p>'
        cond = ", ".join(f"{e(c)}({e(d.module.conditions[r].get('label', r))})" for c, r in d.answer.inputs["conditions"].items()) or "없음"
        sections.append(f'<section class="system" id="sys{i + 1}"><h2>{e(s.name)} <span class="sub">· {e(d.module.title)}</span>'
                        f'<span class="tag {cls}">{"이상 " + str(s.interval_count) + "건" if s.interval_count else "정상 범위"}</span></h2>'
                        f'<div class="sub">운전조건: {cond}</div>{ev}{_panels(d)}</section>')
    q_html = f'<div class="sub">질문: {e(a.question)}</div>' if a.question else ""
    head = " · ".join(x for x in (eq.equipment, subtitle) if x)
    return _page(title, f"""<h1>{e(title)}</h1><div class="sub">{e(head)}</div>{q_html}
{verdict}
<h2>계통별 상태</h2>
<div class="sys">{"".join(cards)}</div>
{_trend(trend)}
{_findings(findings)}
{_guidance(guidance)}
{_qa(qa, ask_url)}
<h2>계통별 신호와 근거</h2>
{LEGEND}
{"".join(sections)}
<h2>물리량</h2>{_table(a)}
<div class="note">계산 방법: {e(a.method)}<br>신뢰도 {e(level)}: {e(a.confidence.reason)}</div>""")
