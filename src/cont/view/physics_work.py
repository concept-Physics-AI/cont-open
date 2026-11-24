"""ConT Physics 작업대 (체결): 잰 값에서 숨은 상태를 추정하고, 목표를 주어 설계 후보를 본다.

계산은 하지 않는다. 서비스 층(`cont.service.api`)이 체결 팩의 `estimate`, `recommend` 동작을 불러 낸 답변 묶음을 그대로 보인다.
공개 화면(GitHub Pages)에는 미리 계산한 예시를 싣고, 로컬 서비스(`/physics`)에서는 값을 바꿔 다시 계산한다.
예시의 늘어남 값은 합성 관측이며 실제 측정이 아니다. 결과는 계산값이고 검증 전이다.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from cont.answer import STATUS_LABELS
from cont.dialogue.serve_fastening import example
from cont.packs.fastening.estimate import synthetic_elongations
from cont.service import api

SYNTHETIC = "합성 관측 (실제 측정 아님)"
DEFAULTS = {"instrument_uncertainty": 0.0005, "targets": {"safety_yield": 1.3, "safety_slip": 1.2}}

CSS = """.wb{margin:8px 0 8px;border:1px solid #DDE2E7;border-radius:16px;padding:20px 22px;background:#fff}
.wb h2{margin-top:0}.wb .steps{display:grid;gap:18px}.wb .st>h3{font-size:15px;font-weight:600;margin:0 0 6px}
.wb .row{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:flex-end}.wb label{font-size:12.5px;color:#59636D;display:flex;flex-direction:column;gap:3px}
.wb input{font:inherit;font-size:14px;padding:6px 8px;border:1px solid #C9D0D6;border-radius:8px;width:150px}.wb input:disabled{background:#F4F6F8;color:#59636D}
.wb button{font:inherit;font-size:14px;padding:8px 14px;border-radius:10px;border:1px solid #0B8480;background:#0B8480;color:#fff;cursor:pointer}
.wb button.sec{background:#fff;color:#0B8480}.wb button:disabled{opacity:.5;cursor:not-allowed}
.wb .big{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.wb .num{border:1px solid #DDE2E7;border-radius:12px;padding:10px 14px}
.wb .num b{font-size:24px;font-weight:600;display:block}.wb .num span{font-size:12.5px;color:#59636D}
.wb .chip{display:inline-block;font-size:11.5px;border-radius:999px;padding:1px 8px;background:#E7F3F2;color:#0B6B67;margin-left:6px}
.wb table{border-collapse:collapse;width:100%;font-size:13.5px}.wb td,.wb th{border-top:1px solid #E6EAEE;padding:6px 8px;text-align:left;vertical-align:top}
.wb th{width:150px;font-weight:600;color:#3B454E}.wb .warn{font-size:12.5px;color:#8A5A00;background:#FFF3DC;border-radius:8px;padding:6px 10px;margin:8px 0}
.wb ol{margin:4px 0 0;padding-left:20px;font-size:13.5px}.wb .err{color:#A13030;font-size:13px}"""

JS = r"""(function(){
var D=JSON.parse(document.getElementById('wb-data').textContent),LIVE=D.live,S=D.status_labels;
function esc(x){return String(x).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function fmt(v,u){if(v===null||v===undefined)return '보고하지 않음';var a=Math.abs(v),s=a!==0&&(a<0.001||a>=100000)?v.toExponential(2):(a>=100?v.toFixed(0):a>=1?v.toFixed(2):v.toPrecision(3));return s+(u&&u!=='-'?' '+u:'');}
function q(a,k){for(var i=0;i<a.answer.quantities.length;i++)if(a.answer.quantities[i].key===k)return a.answer.quantities[i];return null;}
function num(a,k,label){var x=q(a,k);if(!x)return '';var st=x.status||a.answer.status,r=x.expected_range?'<span>범위 '+fmt(x.expected_range[0],x.unit)+' ~ '+fmt(x.expected_range[1],x.unit)+'</span>':'';
return '<div class="num"><span>'+esc(label)+'<i class="chip">'+esc(S[st]||st)+'</i></span><b>'+esc(fmt(x.value,x.unit))+'</b>'+r+'</div>';}
function trust(a){return '<table>'+a.trust.map(function(r){return '<tr><th>'+esc(r[0])+'</th><td>'+esc(r[1])+'</td></tr>';}).join('')+'</table>';}
function render(){
var e=D.estimate,r=D.recommend,h='';
h+='<div class="st"><h3>① 잰 값과 조건</h3><p class="sub">'+esc(D.condition)+'</p><div class="warn">'+esc(D.measured_note)+'</div></div>';
if(e.error)h+='<p class="err">추정하지 못했습니다: '+esc(e.error)+'</p>';else{
h+='<div class="st"><h3>② 추정한 값과 범위</h3><div class="big">'+num(e,'preload_estimated','체결력')+num(e,'friction_estimated','마찰계수')+num(e,'safety_yield_estimated','항복 안전율 (추정한 체결력으로)')+'</div></div>';
h+='<div class="st"><h3>③ 이 값을 믿어도 되는가</h3>'+trust(e)+'</div>';}
if(r.error)h+='<p class="err">설계 후보를 찾지 못했습니다: '+esc(r.error)+'</p>';else{
var items=r.answer.basis.filter(function(b){return /^\d안:|^목표:|^지금 설계:/.test(b);});
h+='<div class="st"><h3>④ 목표를 주고 설계 후보 보기</h3><p class="sub">목표를 만족하는 조합 '+esc(fmt(q(r,'candidates').value,'개'))+'. 비용이나 무게로 고른 순서가 아니라, 지금 설계에서 적게 바꾸는 순서입니다.</p><ol>'+items.map(function(b){return '<li>'+esc(b)+'</li>';}).join('')+'</ol>';
h+='<details><summary>이 후보는 믿어도 되는가</summary>'+trust(r)+'</details></div>';}
h+='<div class="st"><h3>⑤ 근거와 입력 내보내기</h3><button type="button" class="sec" id="wb-dl">JSON으로 내려받기</button> <span class="sub">실행 ID '+esc((e.run_id||'-'))+' · 개정 '+esc((e.revision_id||'-'))+'</span></div>';
document.getElementById('wb-out').innerHTML=h;
document.getElementById('wb-dl').onclick=function(){var b=new Blob([JSON.stringify({inputs:D.inputs,estimate:e,recommend:r},null,1)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='physics_fastening_'+(e.revision_id||'result')+'.json';a.click();};}
function post(act,inp){return fetch('/v1/packs/fastening/'+act,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inputs:inp})}).then(function(x){return x.json().then(function(j){if(!x.ok)throw new Error(j.error||x.status);return j;});});}
var f=document.getElementById('wb-form');
if(!LIVE){f.querySelectorAll('input,button').forEach(function(x){x.disabled=true;});}
else{document.getElementById('wb-static').style.display='none';
f.onsubmit=function(ev){ev.preventDefault();var g=function(n){return parseFloat(f.elements[n].value);},
vals=f.elements.values.value.split(',').map(parseFloat).filter(function(x){return x>0;}),
load=Object.assign({},D.inputs.load,{tightening_torque:g('torque'),axial_load_max:g('axial')}),
base={joint:D.inputs.joint,load:load},
inE=Object.assign({},base,{measured:{values:vals,instrument_uncertainty:g('unc'),source:'화면에서 입력한 값'}}),
inR=Object.assign({},base,{targets:{safety_yield:g('t_yield'),safety_slip:g('t_slip')}});
D.measured_note='입력한 늘어남 '+vals.length+'회: '+vals.join(', ')+' mm';
D.condition='조임 토크 '+g('torque')+' N·m, 축방향 운전 하중 '+g('axial')+' N, 그 밖의 조건은 예제 조인트 그대로';
Promise.all([post('estimate',inE).catch(function(x){return {error:x.message};}),post('recommend',inR).catch(function(x){return {error:x.message};})]).then(function(z){D.estimate=z[0];D.recommend=z[1];D.inputs={joint:D.inputs.joint,load:load,measured:inE.measured,targets:inR.targets};render();});};}
render();})();"""


def example_data() -> dict[str, Any]:
    """예제 조인트와 합성 관측으로 서비스 층을 불러 미리 계산한 결과."""
    joint, load = example()
    elong = synthetic_elongations(joint, load, 0.12, 0.0004, 5, seed=1)
    base = {"joint": asdict(joint), "load": asdict(load)}
    measured = {"values": [round(v, 6) for v in elong], "instrument_uncertainty": DEFAULTS["instrument_uncertainty"], "source": SYNTHETIC}
    est = api.solve("fastening", {**base, "measured": measured}, "", action="estimate")
    rec = api.solve("fastening", {**base, "targets": DEFAULTS["targets"]}, "", action="recommend")
    return {"inputs": {**base, "measured": measured, "targets": DEFAULTS["targets"]}, "estimate": est, "recommend": rec,
            "condition": f"예제 조인트: {joint.size} {joint.property_class}, 판 두 장, 조임 토크 {load.tightening_torque:g} N·m, 축방향 운전 하중 {load.axial_load_max:g} N",
            "measured_note": f"볼트 늘어남 {len(elong)}회 ({SYNTHETIC}): " + ", ".join(f"{v:.5f}" for v in elong) + " mm"}


def render_workbench(live: bool = False) -> str:
    d = example_data()
    d["live"], d["status_labels"] = live, STATUS_LABELS
    data = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    m, load = d["inputs"]["measured"], d["inputs"]["load"]
    form = (f'<form id="wb-form" class="row"><label>조임 토크 (N·m)<input name="torque" type="number" step="any" value="{load["tightening_torque"]:g}"></label>'
            f'<label>축방향 운전 하중 (N)<input name="axial" type="number" step="any" value="{load["axial_load_max"]:g}"></label>'
            f'<label>잰 늘어남 (mm, 쉼표로)<input name="values" type="text" style="width:300px" value="{", ".join(str(v) for v in m["values"])}"></label>'
            f'<label>계기 불확도 (mm)<input name="unc" type="number" step="any" value="{m["instrument_uncertainty"]:g}"></label>'
            f'<label>목표 항복 안전율<input name="t_yield" type="number" step="any" value="{DEFAULTS["targets"]["safety_yield"]:g}"></label>'
            f'<label>목표 미끄럼 안전율<input name="t_slip" type="number" step="any" value="{DEFAULTS["targets"]["safety_slip"]:g}"></label>'
            '<button type="submit">계산</button></form>')
    static = ('<p class="warn" id="wb-static">이 공개 화면은 미리 계산한 예시입니다. 값을 바꿔 계산하려면 이 컴퓨터에서 서비스를 켜고 '
              '<code>python -m cont.service.serve</code> 후 <code>http://127.0.0.1:8770/physics</code>를 여세요.</p>')
    return (f'<section class="wb"><h2>체결 작업대</h2><p class="sub">잰 값에서 직접 재기 어려운 값을 범위와 함께 추정하고, 목표를 주어 설계 후보를 봅니다. '
            f'계산은 서비스 층이 체결 팩을 불러 낸 것이고, 결과는 계산값이며 검증 전입니다.</p>{static}{form}'
            f'<div class="steps" id="wb-out"></div><script id="wb-data" type="application/json">{data}</script><script>{JS}</script></section>')
