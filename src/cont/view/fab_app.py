"""ConT Fab 화면: 왼쪽에 현장 설정, 가운데에 신호와 정상 범위, 오른쪽에 ConT Agent (관찰 사실 · 원인 후보 · 다음 점검).

- 값은 진단 팩이 낸 것만 싣는다. 원인은 후보로만 말하고 판정하지 않는다.
- 점검 상태(미확인 → 점검 중 → 조치 → 재확인)는 지금은 이 화면 안에서만 바뀐다. 저장하지 않는다.
- 색은 청록 하나(연결되고 고른 것)와 주황(확정하지 않았다는 알림)만 쓴다.
"""
from __future__ import annotations

import html
import json
from typing import Any, Mapping, Sequence

from cont.packs.diagnosis.equipment import EquipmentDiagnosis
from cont.packs.diagnosis.report import Card
from cont.view.diagnosis_html import CSS, _chart

STATES = ("미확인", "점검 중", "조치", "재확인")
LEVELS = {"low": "낮음", "medium": "중간", "high": "높음"}

FAB_CSS = """
:root,:root:root{color-scheme:light;--bg:#fff;--card:#fff;--ink:#101317;--sub:#5A626B;--line:#E1E4E8;--band:#D9EFEC;--sig:#0E8F8A;--bad:#B4541A;--t:#0E8F8A;--ts:#E3F4F2;--warn:#8A5200;--warnbg:#FDF1DC}
html,body{height:100%}body{margin:0;overflow:hidden;background:#fff;color:var(--ink);font-family:"IBM Plex Sans KR","Segoe UI","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;font-size:15px;line-height:1.55;letter-spacing:-.01em}
button,input{font:inherit;color:inherit}button{cursor:pointer}h1,h2,h3{margin:0}
.fab{height:100dvh;display:grid;grid-template-rows:56px 58px minmax(0,1fr)}
.bar{display:flex;align-items:center;padding:0 26px;border-bottom:1px solid var(--line);min-width:0}
.bar .name{font-size:24px;font-weight:600;letter-spacing:-.02em;margin-right:26px;white-space:nowrap}.bar .sep{width:1px;height:24px;background:var(--line);margin-right:10px}
.bar .prod{height:56px;display:flex;align-items:center;padding:0 22px;font-size:16px;border-bottom:3px solid transparent;color:var(--sub)}.bar .prod.on{color:var(--t);font-weight:600;border-bottom-color:var(--t)}
.bar select{margin-left:auto;height:40px;padding:0 12px;border-radius:8px;border:1px solid var(--ink);background:#fff;font-size:14px}
.head{display:flex;align-items:center;gap:22px;padding:0 26px;border-bottom:1px solid var(--line);min-width:0}.head h1{font-size:23px;font-weight:600;letter-spacing:-.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.head .q{font-size:15px;color:var(--sub);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.head .demo{margin-left:auto;flex:none;font-size:14px;font-weight:500;color:var(--warn);background:var(--warnbg);padding:5px 12px;border-radius:6px}
.cols{display:grid;grid-template-columns:290px minmax(0,1fr) minmax(380px,500px);min-height:0}
.left,.mid,.right{min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#C3C9D0 transparent}
.left{padding:6px 22px 20px;border-right:1px solid var(--line)}.sec{padding:16px 0;border-bottom:1px solid var(--line)}.sec:last-child{border-bottom:0}
.sec h2{font-size:15px;font-weight:600;margin-bottom:8px}.sec h2 small{font-weight:400;color:var(--sub);font-size:12.5px;margin-left:8px}
.sys{display:flex;flex-direction:column;gap:2px}.sys button{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px;padding:4px 12px;border:0;border-radius:8px;background:transparent;font-size:14px;text-align:left}
.sys button:hover{background:#F3F5F7}.sys button[aria-pressed=true]{background:var(--ts);font-weight:500}.sys .n{flex:none;font-size:12.5px;color:var(--sub)}.sys .n.has{color:var(--bad);font-weight:500}
.kv{display:grid;grid-template-columns:88px 1fr;font-size:14px;line-height:1.9}.kv span:nth-child(odd){color:var(--sub)}.plain{font-size:13.5px;color:var(--sub);line-height:1.65;margin:0}
.mid{padding:20px 26px 24px}.mid h2{font-size:19px;font-weight:600}.mid .cap{font-size:13.5px;color:var(--sub);margin:2px 0 14px}
.sig{border-top:1px solid var(--line);padding:14px 0 6px}.sig .t{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}.sig h3{font-size:16px;font-weight:600}.sig h3 small{font-weight:400;color:var(--sub);font-size:13px;margin-left:6px}
.sig .dev{margin-left:auto;font-size:14px;color:var(--sub)}.sig .dev b{color:var(--bad);font-weight:600;font-size:16px;margin-left:4px}.sig .dev.ok b{color:var(--t)}
.sig svg{display:block;width:100%;height:auto;margin-top:4px}.sig .tick{font-size:11.5px}.sig .sig{stroke-width:1.6}
.legend{display:flex;gap:18px;flex-wrap:wrap;color:var(--sub);font-size:12.5px;margin:10px 0 0}.legend i{display:inline-block;width:22px;height:9px;border-radius:2px;vertical-align:middle;margin-right:6px}
.right{padding:20px 26px 24px;border-left:1px solid var(--line);display:flex;flex-direction:column}.right>h2{font-size:22px;font-weight:600;letter-spacing:-.02em}
.banner{display:flex;align-items:center;gap:10px;margin-top:14px;padding:11px 14px;border-radius:10px;background:var(--warnbg);color:var(--warn);font-size:14.5px;font-weight:600}.banner svg{flex:none;width:20px;height:20px}
.none{margin-top:16px;font-size:15px}
.find{margin-top:16px;border:1px solid var(--line);border-radius:14px;overflow:hidden}.find[data-on="1"]{border-color:var(--ink)}
.find>button{display:flex;align-items:center;gap:10px;width:100%;min-height:52px;padding:8px 16px;border:0;background:#fff;text-align:left;font-size:15px;font-weight:600}
.find>button small{font-weight:400;color:var(--sub);font-size:13px}.find>button .st{margin-left:auto;flex:none;font-size:12.5px;font-weight:500;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:2px 10px}
.find>button .st.go{color:var(--t);border-color:var(--t)}.find .body{padding:0 16px 16px}.find[data-open="0"] .body{display:none}
.part{margin-top:12px}.part h3{font-size:14px;font-weight:600}.part p,.part li{font-size:14.5px;line-height:1.65;margin:3px 0 0}.part ol,.part ul{margin:0;padding-left:0;list-style:none}
.part .tg{display:inline-block;min-width:44px;color:var(--sub);font-size:12.5px;font-variant-numeric:tabular-nums}
.flow{display:flex;align-items:center;gap:6px;margin-top:14px;flex-wrap:wrap}.flow span{font-size:13px;color:var(--sub);padding:4px 10px;border-radius:999px;border:1px solid var(--line)}.flow span.on{color:#fff;background:var(--t);border-color:var(--t);font-weight:500}
.flow span.done{color:var(--t);border-color:var(--t)}.flow i{width:10px;height:1px;background:var(--line)}
.acts{display:flex;gap:8px;margin-top:10px}.acts button{flex:1;min-height:44px;border-radius:10px;font-size:14px}.acts .next{border:0;background:var(--t);color:#fff;font-weight:600}.acts .next[disabled]{opacity:.45;cursor:default}
.acts .hold{border:1px solid var(--ink);background:#fff}.keep{font-size:12.5px;color:var(--sub);margin:8px 0 0}
.ask{margin-top:auto;padding-top:20px}.ask h3{font-size:14px;font-weight:600;margin-bottom:8px}.chips{display:flex;flex-wrap:wrap;gap:8px}
.chips button{min-height:44px;padding:0 14px;border-radius:22px;border:1px solid var(--line);background:#fff;font-size:14px;text-align:left}.chips button:hover,.chips button[aria-pressed=true]{border-color:var(--t);color:var(--t)}
.me{align-self:flex-end;margin-top:12px;padding:10px 16px;border-radius:18px 18px 4px 18px;background:#E4E8EC;font-size:15px;max-width:90%}
.ans{margin-top:10px;font-size:14.5px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}.ans:empty,.me:empty{display:none}.src{font-size:12.5px;color:var(--sub);margin-top:4px}.src:empty{display:none}
#say{display:flex;gap:8px;margin-top:10px}#say input{flex:1;min-width:0;height:46px;padding:0 16px;border-radius:23px;border:1px solid var(--line);font-size:15px;background:#fff}#say input:focus{outline:none;border-color:var(--t)}
#say button{flex:none;height:46px;padding:0 18px;border-radius:23px;border:0;background:var(--ink);color:#fff;font-size:14px}
.fab button:focus-visible,.fab select:focus-visible,.fab input:focus-visible{outline:2px solid var(--t);outline-offset:2px}
@media (max-width:1100px){body{overflow:auto}.fab{height:auto;display:block}.bar{height:56px;overflow-x:auto}.head{min-height:58px;flex-wrap:wrap;padding:8px 26px}.cols{display:block}
.left,.mid,.right{overflow:visible;border:0;border-bottom:1px solid var(--line)}.bar .prod{padding:0 14px}}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01s!important;transition-duration:.01s!important}}
"""

FAB_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('fab-data').textContent),C=null,sys=0,state={};
var $=function(q,r){return (r||document).querySelector(q)},STATES=D.states;
function esc(t){var d=document.createElement('div');d.textContent=t==null?'':String(t);return d.innerHTML;}
function tg(x){return '<span class="tg">'+esc(x.tag)+'</span>'+esc(x.text);}
function pick(i){C=D.cases[i];sys=0;var first=C.cards[0];if(first)sys=Math.max(0,C.systems.map(function(s){return s.name;}).indexOf(first.system));
$('#title').textContent=C.equipment+' · '+C.heading;$('#quest').textContent=C.question||'';$('#demo').hidden=!C.synthetic;
$('#conf').textContent=C.cards.length?('현장 점검 전 · 원인 미확정 · 신뢰도 '+C.confidence):'같은 운전조건의 정상 범위 안에서 운전하고 있습니다';
$('#banner').classList.toggle('calm',!C.cards.length);left();mid();right();asks();}
function left(){$('#sys').innerHTML=C.systems.map(function(s,i){return '<button type="button" data-sys="'+i+'" aria-pressed="'+(i===sys)+'"><span>'+esc(s.name)+'</span><span class="n'+(s.found?' has':'')+'">'+(s.found?('벗어남 '+s.found+'건'):'범위 안')+'</span></button>';}).join('');
var s=C.systems[sys];$('#cond').innerHTML='<span>계통</span><span>'+esc(s.module)+'</span>'+s.conditions.map(function(c){return '<span>'+esc(c[0])+'</span><span>'+esc(c[1])+'</span>';}).join('')+'<span>가로축</span><span>'+esc(s.time)+'</span>';
$('#sigs').innerHTML=s.signals.map(function(g){return '<span>'+esc(g.label)+'</span><span>'+esc(g.column)+(g.unit?' ('+esc(g.unit)+')':'')+'</span>';}).join('');}
function mid(){var s=C.systems[sys];$('#mh').textContent=s.name+' · 신호와 정상 범위';
$('#charts').innerHTML=s.signals.map(function(g){return '<div class="sig"><div class="t"><h3>'+esc(g.label)+(g.unit?'<small>'+esc(g.unit)+'</small>':'')+'</h3><span class="dev'+(g.peak==null?' ok':'')+'">'+(g.peak==null?'<b>범위 안</b>':('가장 크게 벗어난 정도 <b>정상 산포의 '+esc(g.peak)+'배</b>'))+'</span></div>'+g.chart+'</div>';}).join('');}
function right(){var box=$('#finds');if(!C.cards.length){box.innerHTML='<p class="none">찾아낸 변화가 없습니다. 점검할 항목이 없습니다.</p>';return;}
box.innerHTML=C.cards.map(function(c,i){var st=state[C.id+':'+i]||0,open=(i===0)?1:0;
return '<div class="find" data-i="'+i+'" data-open="'+open+'" data-on="'+open+'"><button type="button" aria-expanded="'+(open?'true':'false')+'"><span>'+esc(c.title)+' <small>'+esc(c.system)+' · '+esc(c.label)+'</small></span><span class="st'+(st?' go':'')+'">'+STATES[st]+'</span></button><div class="body">'
+'<div class="part"><h3>관찰 사실</h3><p>'+tg(c.observed)+'</p></div>'
+'<div class="part"><h3>원인 후보 <small style="font-weight:400;color:var(--sub)">확정한 원인이 아닙니다</small></h3>'+(c.candidates.length?'<ul>'+c.candidates.map(function(x){return '<li>'+tg(x)+'</li>';}).join('')+'</ul>':'<p>지식표에 후보가 없습니다.</p>')+'</div>'
+'<div class="part"><h3>다음 점검 <small style="font-weight:400;color:var(--sub)">확인하기 쉬운 것부터</small></h3>'+(c.checks.length?'<ol>'+c.checks.map(function(x){return '<li>'+tg(x)+'</li>';}).join('')+'</ol>':'<p>지식표에 항목이 없습니다.</p>')+'</div>'
+'<div class="flow">'+STATES.map(function(n,k){return (k?'<i></i>':'')+'<span class="'+(k===st?'on':k<st?'done':'')+'">'+n+'</span>';}).join('')+'</div>'
+'<div class="acts"><button type="button" class="next"'+(st>=STATES.length-1?' disabled':'')+'>'+(st>=STATES.length-1?'재확인까지 마침':('"'+STATES[Math.min(st+1,STATES.length-1)]+'"(으)로'))+'</button><button type="button" class="hold">처음으로</button></div>'
+'<p class="keep">상태는 이 화면에서만 바뀝니다. 아직 저장하지 않습니다.</p></div></div>';}).join('');}
function asks(){$('#chips').innerHTML=C.questions.map(function(q,i){return '<button type="button" data-q="'+i+'" aria-pressed="false">'+esc(q.q)+'</button>';}).join('');$('#me').textContent='';$('#ans').textContent='';$('#src').textContent='';
$('#say').hidden=!D.ask_url;}
function answer(q,a,src){$('#me').textContent=q;$('#ans').textContent=a;$('#src').textContent=src||'';$('#ans').scrollIntoView({block:'nearest'});}
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('button');if(!b)return;
if(b.dataset.sys!=null){sys=Number(b.dataset.sys);left();mid();return;}
if(b.dataset.q!=null){var q=C.questions[Number(b.dataset.q)];document.querySelectorAll('#chips button').forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false');});answer(q.q,q.a,q.src);return;}
var f=b.closest('.find');if(!f)return;var i=Number(f.dataset.i),key=C.id+':'+i;
if(b.parentNode===f){var open=f.dataset.open!=='1';document.querySelectorAll('.find').forEach(function(x){x.dataset.open='0';x.dataset.on='0';x.firstChild.setAttribute('aria-expanded','false');});
if(open){f.dataset.open='1';f.dataset.on='1';b.setAttribute('aria-expanded','true');var k=C.systems.map(function(s){return s.name;}).indexOf(C.cards[i].system);if(k>=0&&k!==sys){sys=k;left();mid();}}return;}
if(b.classList.contains('next')){state[key]=Math.min((state[key]||0)+1,STATES.length-1);}else if(b.classList.contains('hold')){state[key]=0;}else return;
right();var again=document.querySelector('.find[data-i="'+i+'"]');document.querySelectorAll('.find').forEach(function(x){x.dataset.open='0';x.dataset.on='0';});again.dataset.open='1';again.dataset.on='1';});
$('#case').addEventListener('change',function(){pick(Number(this.value));});
$('#say').addEventListener('submit',function(e){e.preventDefault();var inp=$('#say input'),q=inp.value.trim();if(!q)return;inp.value='';answer(q,'답을 만드는 중입니다.','');
fetch(D.ask_url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,case:C.id})}).then(function(r){return r.json();})
.then(function(m){answer(q,m.answer,m.source);}).catch(function(){answer(q,'답을 받지 못했습니다. 서버가 켜져 있는지 확인해 주세요.','');});});
pick(0);document.body.dataset.ready='1';
})();
"""

WARN = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5l8 14H2z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
        '<path d="M10 8v4M10 14.4v.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>')


def case(case_id: str, heading: str, eq: EquipmentDiagnosis, cards: Sequence[Card], questions: Sequence[tuple[str, str, str]] = (),
         synthetic: bool = False) -> dict[str, Any]:
    """화면에 싣는 설비 하나. questions: (질문, 답, 답을 만든 방법)."""
    systems = []
    for s in eq.systems:
        d = s.diagnosis
        used = (eq.answer.inputs or {}).get("systems", [])
        mine = next((u for u in used if u.get("name") == s.name), {})
        conds = [(d.module.conditions.get(role, {}).get("label", role), col) for role, col in (mine.get("conditions") or {}).items()]
        sigs = []
        for r in d.signals:
            peak = max((abs(iv.peak_z) for iv in r.intervals), default=None)
            sigs.append({"label": r.label, "unit": r.unit, "column": r.column, "peak": None if peak is None else f"{peak:.1f}",
                         "chart": _chart(r, d.time, d.settings.z_limit)})
        systems.append({"name": s.name, "module": d.module.title, "time": mine.get("time") or "표본 번호", "conditions": conds, "signals": sigs,
                        "found": sum(c.system == s.name for c in cards)})
    c = eq.answer.confidence
    return {"id": case_id, "heading": heading, "equipment": eq.equipment, "question": eq.answer.question, "synthetic": synthetic,
            "confidence": LEVELS.get(c.level, c.level), "systems": systems,
            "cards": [{"system": k.system, "label": k.label, "title": k.title, "kind": k.kind,
                       "observed": {"tag": k.observed.tag, "text": k.observed.text},
                       "candidates": [{"tag": t.tag, "text": t.text} for t in k.candidates],
                       "checks": [{"tag": t.tag, "text": t.text} for t in k.checks]} for k in cards],
            "questions": [{"q": q, "a": a, "src": src} for q, a, src in questions]}


def render_fab(cases: Sequence[Mapping[str, Any]], ask_url: str | None = None, title: str = "ConT Fab") -> str:
    if not cases:
        raise ValueError("at least one case is required")
    e = html.escape
    opts = "".join(f'<option value="{i}">{e(c["equipment"])}</option>' for i, c in enumerate(cases))
    blob = json.dumps({"cases": list(cases), "ask_url": ask_url, "states": STATES}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = f"""<div class="fab">
<header class="bar"><span class="name">ConT Fab</span><span class="sep"></span><span class="prod">Physics</span><span class="prod on" aria-current="page">Fab</span><span class="prod">Studio</span>
<select id="case" aria-label="설비 고르기">{opts}</select></header>
<div class="head"><h1 id="title"></h1><span class="q" id="quest"></span><span class="demo" id="demo">가상 데이터 시연</span></div>
<div class="cols">
<aside class="left" aria-label="현장 설정">
<div class="sec"><h2>현장 설정<small>계통을 고르면 가운데가 바뀝니다</small></h2><div class="sys" id="sys"></div></div>
<div class="sec"><h2>운전조건</h2><div class="kv" id="cond"></div></div>
<div class="sec"><h2>정상 기준<small>같은 운전조건의 평소</small></h2><p class="plain">정상 운전 구간에서 잡은 범위입니다. 합격·불합격의 기준이 아니며, 벗어난 정도만 보고합니다.</p></div>
<div class="sec"><h2>입력 신호<small>이름 → 현장 열</small></h2><div class="kv" id="sigs"></div></div>
</aside>
<section class="mid" aria-label="신호"><h2 id="mh"></h2><p class="cap">선은 실제 값, 띠는 같은 운전조건의 정상 범위, 칠한 곳은 벗어난 구간입니다.</p><div id="charts"></div>
<div class="legend"><span><i style="background:var(--sig)"></i>실제 값</span><span><i style="background:var(--band)"></i>정상 범위</span><span><i style="background:var(--bad);opacity:.3"></i>벗어난 구간</span></div></section>
<section class="right" aria-label="ConT Agent"><h2>ConT Agent</h2>
<div class="banner" id="banner">{WARN}<span id="conf"></span></div>
<div id="finds"></div>
<div class="ask"><h3>물어보기</h3><div class="chips" id="chips"></div><div class="me" id="me"></div><div class="ans" id="ans" aria-live="polite"></div><div class="src" id="src"></div>
<form id="say"><input type="text" aria-label="진단 결과에 대해 묻기" placeholder="진단 결과에 대해 물어보세요" autocomplete="off"><button type="submit">묻기</button></form></div>
</section>
</div></div>
<script type="application/json" id="fab-data">{blob}</script><script>{FAB_JS}</script>"""
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">')
    return (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f"<title>{e(title)}</title>{fonts}<style>{CSS}{FAB_CSS}</style></head><body>\n{body}\n</body></html>")
