"""체결 화면 (대화 중심): 왼쪽에 대화, 오른쪽에 결과. C4 표현.

구성과 규칙 (docs/fastening_screen.md)
- 처음에는 인사와 입력창, 추천 문구만 보인다. 말을 하면 왼쪽에 대화가 쌓이고 오른쪽에 결과가 열린다.
- 고정되는 곳: 왼쪽 목록, 입력창과 추천 문구, 결과의 제목·그림·숫자 셋·묶음 단추. 흐르는 곳: 대화와, 결과에서 펼친 묶음의 안쪽 둘뿐이다.
  좁은 화면에서는 위의 이름 줄과 아래의 입력창만 고정하고 그 사이가 한 줄기로 흐른다.
- 새 답이 오면 맨 아래를 보고 있을 때만 따라 내려간다. 위를 읽고 있으면 "최신 답으로" 단추가 뜬다.
- 색은 바뀐 곳을 알리는 황동색 하나와, 경계를 넘었을 때의 빨강만 쓴다. 값의 지위는 결과 제목 옆 한 줄로 적고 전체는 "믿어도 되는가"에 둔다.

3D 보기는 fastening_live의 것을 그대로 쓴다 (꼭짓점이 옮겨 가고 바뀐 부품이 빛난다).
"""
from __future__ import annotations

import html
import json
from typing import Any, Mapping

from cont.view.diagnosis_html import CSS
from cont.view.fastening_html import EXTRA_CSS
from cont.view.fastening_live import GROUPS, LIVE_CSS, LIVE_JS
from cont.view.field_image import FIELD_CSS

IDEAS = (("예제 조인트로 시작해 줘", "M10 볼트로 두께 15 mm 판 두 장을 체결합니다"),
         ("응력 분포를 보여 줘", "판 안에서 압축이 퍼지는 모습을 물리 이미지로 봅니다"),
         ("이 결과를 믿어도 돼?", "근거, 불확실성, 맞지 않게 되는 조건을 봅니다"),
         ("현장에서는 무엇으로 재야 해?", "이 조인트에 맞는 센서와 연결을 추천합니다"))

_HELPERS = LIVE_JS[LIVE_JS.index("var $="):LIVE_JS.index("/* ---------- 3D 보기")]
_VIEWER = (LIVE_JS[LIVE_JS.index("/* ---------- 3D 보기"):LIVE_JS.index("$('#xr').addEventListener")]
           # 눌림 영역을 비쳐 보이게 그려 그 안의 볼트가 보이게 한다
           .replace("p.role.indexOf('plate')!==0&&(xray||p.role!=='zone')", "p.role.indexOf('plate')!==0&&p.role!=='zone'")
           .replace("plates.forEach(function(p){paint(p,0.2);});",
                    "now.parts.filter(function(p){return p.role==='zone';}).forEach(function(p){paint(p,0.34);});plates.forEach(function(p){paint(p,0.14);});"))
# 볼트의 색: 한 가지 색 계열 (금속 회색 → 황동색). 등가응력 ÷ 항복강도가 클수록 밝은 황동색이다
_HELPERS = _HELPERS.replace("var RAMP=[[0,[0.30,0.49,0.94]],[0.5,[0.27,0.76,0.65]],[0.8,[0.95,0.79,0.30]],[1,[0.94,0.32,0.29]]];",
                            "var RAMP=[[0,[0.66,0.70,0.74]],[0.5,[0.72,0.60,0.36]],[0.8,[0.85,0.64,0.25]],[1,[0.96,0.80,0.44]]];")
assert "paint(p,0.34)" in _VIEWER and "p.role!=='zone';})" in _VIEWER and "0.66,0.70,0.74" in _HELPERS       # fastening_live가 바뀌면 여기서 알아챈다

MARK = ('<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="13" fill="#101317"/>'
        '<path d="M18.5 10.2a6 6 0 1 0 0 7.6" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/><circle cx="14" cy="14" r="1.8" fill="#D9A441"/></svg>')

APP_CSS = """
:root,:root:root{color-scheme:light;--paper:#F7F7F8;--panel:#FFFFFF;--ink:#101317;--sub:#5A626B;--line:#E1E4E8;--mark:#8A5A0C;--markbg:rgba(138,90,12,.10);--bad:#B3261E;--sig:#3F4852;
--bg:var(--paper);--card:var(--panel);--vp1:#1B2027;--vp2:#12161B;--vink:#EEF1F4;--vsub:#A3ABB4;--vline:#2C343D;--glow:#D9A441;
--p-bolt:#AEB6BF;--p-plate1:#4A545F;--p-plate2:#3D4650;--zone:#D9A441}
html,body{height:100%}body{margin:0;overflow:hidden;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans KR","Segoe UI Variable Text","Segoe UI","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;letter-spacing:-.01em}
button,input{font:inherit;color:inherit}button{cursor:pointer}
.app svg,.top svg{display:inline-block;flex:none;width:16px;height:16px}.brand svg,.bot>svg{width:28px;height:28px}.side .new svg{width:18px;height:18px}#say.say button svg{width:20px;height:20px}
.stage .swap svg,.drawer svg{display:block;width:100%;height:auto}
main.conv{max-width:none;margin:0}
.app.app{max-width:none;margin:0;padding:0;gap:0;height:100dvh;display:grid;grid-template-columns:256px minmax(0,1fr);align-items:stretch}
.app[data-mode=talk]{grid-template-columns:256px minmax(360px,468px) minmax(0,1fr)}
/* 왼쪽 목록 */
.side{border-right:1px solid var(--line);padding:22px 14px;display:flex;flex-direction:column;min-height:0}
.brand{display:flex;align-items:center;gap:10px;padding:4px 8px 0;font-size:20px;font-weight:600;letter-spacing:-.02em}
.side .new{display:flex;align-items:center;gap:10px;height:46px;margin-top:22px;padding:0 16px;border-radius:23px;border:1px solid var(--line);background:#fff;font-size:14px;font-weight:500}
.side .new:hover{border-color:var(--ink)}.side .cur{margin-top:22px;font-size:12px;color:var(--sub);padding:0 14px}
.side .now{margin-top:8px;height:44px;display:flex;align-items:center;padding:0 14px;border-radius:12px;background:#fff;box-shadow:0 1px 2px rgba(16,19,23,.05),0 0 0 1px var(--line);font-size:14px;font-weight:500}
.side .now:empty{display:none}.side nav{margin-top:auto;display:flex;flex-direction:column;padding:0 14px;font-size:14px}.side nav a{height:36px;display:flex;align-items:center;color:var(--sub);text-decoration:none}.side nav a:hover{color:var(--ink)}
/* 대화 */
.conv{display:flex;flex-direction:column;min-height:0;min-width:0;padding:0 0 22px 32px}
.app[data-mode=empty] .conv{align-items:center;justify-content:center;padding:0 40px 40px}
.app[data-mode=empty] .conv>*{width:min(760px,100%)}.app[data-mode=empty] .thread,.app[data-mode=empty] .sugg,.app[data-mode=empty] #latest{display:none}
.app[data-mode=talk] .hello,.app[data-mode=talk] .ideas{display:none}
.hello{text-align:center;margin-bottom:28px}.hello h1{font-size:48px;font-weight:500;letter-spacing:-.035em;line-height:1.2;margin:0}.hello p{font-size:17px;color:var(--sub);margin:12px 0 0;line-height:1.6}
.thread{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:28px 18px 8px 0;display:flex;flex-direction:column;gap:22px;scrollbar-width:thin;scrollbar-color:#C3C9D0 transparent;
-webkit-mask-image:linear-gradient(transparent,#000 48px);mask-image:linear-gradient(transparent,#000 48px)}
.thread>:first-child{margin-top:auto}.thread:focus-visible{outline:2px solid var(--ink);outline-offset:-2px;border-radius:8px}
.bot,.me{scroll-margin-top:68px}.me{align-self:flex-end;max-width:84%;padding:12px 18px;border-radius:22px 22px 6px 22px;background:#E4E8EC;font-size:16px;line-height:1.55;animation:rise .3s ease}
.bot{display:flex;gap:14px;align-items:flex-start;animation:rise .35s ease}.bot>svg{flex:none;margin-top:2px}.bot .b{flex:1;min-width:0;display:flex;flex-direction:column;gap:12px;font-size:16px;line-height:1.7}
.bot .al{font-weight:500}.bot .al.low{color:var(--bad)}
.cells{display:flex;gap:8px;flex-wrap:wrap}.cell{flex:1 1 120px;padding:11px 14px;border-radius:14px;background:#fff;box-shadow:0 0 0 1px var(--line)}
.cell .k{font-size:12px;color:var(--sub);line-height:1.4}.cell .v{font-size:13px;color:var(--sub);font-variant-numeric:tabular-nums;line-height:1.4;margin-top:2px}.cell .v s{text-decoration:line-through}
.cell .v b{font-size:20px;font-weight:500;color:var(--ink);margin-left:8px}.cell.low .v b{color:var(--bad)}
.opts{display:grid;gap:8px}.opts .cand{font-size:12.5px;color:var(--sub);line-height:1.5}
.opts button{text-align:left;min-height:48px;padding:10px 16px;border-radius:14px;border:0;background:#fff;box-shadow:0 0 0 1px var(--line);font-size:15px;line-height:1.45}
.opts button:hover{box-shadow:0 0 0 1px var(--ink)}.opts button .d{display:block;font-size:12.5px;color:var(--sub)}
.bot details{font-size:13px;color:var(--sub)}.bot details summary{cursor:pointer}.bot details pre{white-space:pre-wrap;font:inherit;margin:6px 0 0;line-height:1.6}
#latest{align-self:center;display:flex;align-items:center;gap:8px;height:40px;padding:0 16px;margin-top:8px;border-radius:20px;border:1px solid var(--line);background:#fff;font-size:13px;box-shadow:0 2px 8px rgba(16,19,23,.08)}
#latest[hidden]{display:none}
.dock{display:flex;flex-direction:column;gap:12px;padding:14px 18px 0 0}.app[data-mode=empty] .dock{padding:0}
.sugg{display:flex;flex-wrap:wrap;gap:8px}.sugg button{min-height:44px;padding:0 16px;border-radius:22px;border:1px solid var(--line);background:#fff;font-size:14px;text-align:left}
.sugg button:hover{border-color:var(--ink)}.sugg button:first-child{border-color:var(--ink)}.sugg button:first-child::before{content:"추천";font-size:12px;font-weight:600;color:var(--mark);margin-right:10px}
.sugg button[disabled]{opacity:.45;cursor:default}
#say.say{display:flex;align-items:center;gap:12px;height:58px;padding:0 8px 0 24px;border-radius:29px;background:#fff;border:1px solid var(--line);box-shadow:0 1px 2px rgba(16,19,23,.04),0 10px 32px rgba(16,19,23,.08)}
.app[data-mode=empty] #say.say{height:64px;border-radius:32px}
#say.say:focus-within{border-color:var(--ink)}#say.say input{flex:1;min-width:0;height:44px;border:0;outline:none;background:transparent;font-size:16px;color:var(--ink);padding:0;border-radius:0}
#say.say input::placeholder{color:#8A929B}#say.say button{flex:none;width:44px;height:44px;padding:0;border:0;border-radius:22px;background:var(--ink);display:flex;align-items:center;justify-content:center}
#say.say button:hover{background:#000}#say.say button[disabled]{opacity:.4}
.ideas{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:24px}
.ideas button{display:flex;flex-direction:column;align-items:flex-start;gap:6px;padding:20px 22px;border-radius:20px;border:0;background:#fff;box-shadow:0 0 0 1px var(--line),0 1px 2px rgba(16,19,23,.04);text-align:left}
.ideas button:hover{box-shadow:0 0 0 1px var(--ink)}.ideas b{font-size:15px;font-weight:500}.ideas span{font-size:13px;color:var(--sub);line-height:1.5}
.fine{text-align:center;font-size:13px;color:var(--sub);margin:22px 0 0}.app[data-mode=talk] .fine{display:none}
/* 결과: 한 장의 카드 */
.result{display:none;min-height:0;min-width:0;padding:20px 24px 24px 28px}.app[data-mode=talk] .result{display:flex}
.rcard{flex:1;min-width:0;min-height:0;display:flex;flex-direction:column;gap:16px;padding:22px 22px 20px;border-radius:32px;background:#fff;box-shadow:0 1px 2px rgba(16,19,23,.04),0 16px 48px rgba(16,19,23,.07)}
.rhead{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:0 6px;flex-wrap:wrap}.rhead h2{font-size:22px;font-weight:600;letter-spacing:-.02em;margin:0}
.rhead h2 small{font-size:14px;font-weight:400;color:var(--sub);margin-left:12px;letter-spacing:0}.rhead .state{font-size:13px;color:var(--sub)}
.stage.stage{flex:1 1 300px;min-height:220px;border-radius:26px;background:radial-gradient(60% 70% at 50% 52%,#242B33,#14181D 100%);box-shadow:inset 0 0 0 1px rgba(255,255,255,.07)}
.rcard.open .stage.stage{flex:0 0 clamp(200px,32vh,300px)}
.stage .tabs{gap:24px;padding:10px 26px 0;align-items:center}.stage .tabs button{font-size:14px;height:44px;padding:0;border-bottom:2px solid transparent}
.stage .tabs button[aria-selected=true]{border-bottom-color:var(--glow)}.stage .tabs .sp{margin-left:auto}
.stage .tabs .xr{position:relative;border:1px solid var(--vline);border-radius:999px;right:auto;top:auto;flex:none;white-space:nowrap;height:36px;padding:0 14px 0 32px;font-size:13px;background:transparent;border-color:var(--vline)}.stage .tabs .xr[aria-pressed=true]{border-color:var(--glow)}
.stage .vp{flex:1;height:auto;min-height:0}.stage .pane{padding:4px 22px 0;overflow:auto;scrollbar-width:thin;scrollbar-color:#4A5561 transparent}.stage #pane-shape{padding:0;overflow:hidden}
.stage .hint{top:auto;bottom:16px;left:26px;right:auto}.stage .hint a{color:var(--vsub)}.stage .xray .hint{display:none}
.stage .key{left:26px;bottom:14px}.stage .key .sc{background:linear-gradient(90deg,#A8B2BC,#B89A5C 50%,#D9A441 80%,#F5CC70)}
.stage .badge{right:22px;bottom:14px;background:transparent}.stage .notes{top:14px;right:22px}.graphs{display:grid;gap:10px}
.stats{display:flex;gap:18px;padding:2px 6px 0}.stat{flex:1;min-width:0;padding-left:18px;border-left:1px solid var(--line);position:relative}.stat:first-child{padding-left:0;border-left:0}
.stat .k{font-size:13px;color:var(--sub);line-height:1.4}.stat .v{display:flex;align-items:baseline;flex-wrap:wrap;margin-top:4px}
.stat .num{font-size:32px;font-weight:300;letter-spacing:-.03em;line-height:1.15;font-variant-numeric:tabular-nums}.stat .v.low .num{color:var(--bad)}
.stat .u{font-size:14px;color:var(--sub);margin-left:6px}.stat .dl{font-size:13px;font-weight:500;color:var(--mark);margin-left:8px;font-variant-numeric:tabular-nums}.stat .dl:empty{display:none}
.stat .rg{font-size:12px;color:var(--sub);margin-top:2px;line-height:1.4}
.seg{display:flex;gap:8px}.seg button{flex:1;display:flex;align-items:center;justify-content:space-between;height:46px;padding:0 16px;border-radius:14px;border:1px solid transparent;background:var(--paper);font-size:14px}
.seg button:hover{border-color:var(--line)}.seg button[aria-expanded=true]{background:#fff;border-color:var(--ink);font-weight:600}
.seg svg{transition:transform .2s}.seg button[aria-expanded=true] svg{transform:rotate(180deg)}
.drawer{flex:1 1 0;min-height:0;overflow-y:auto;overscroll-behavior:contain;border-radius:16px;background:var(--paper);padding:6px 20px 18px;scrollbar-width:thin;scrollbar-color:#C3C9D0 transparent}
.drawer[hidden]{display:none}.drawer>div[hidden]{display:none}.drawer h3{font-size:14px;font-weight:600;margin:16px 0 6px}.drawer h3 small{font-weight:400;color:var(--sub);margin-left:8px}
.drawer .why{font-size:12.5px;color:var(--sub);margin:0 0 8px;line-height:1.55}.drawer .tr{grid-template-columns:96px 1fr;gap:10px 14px;font-size:14px;padding:12px 0 0;line-height:1.55}
.drawer table{background:#fff}.drawer .read .v{font-size:20px}
.app a:focus-visible,.app button:focus-visible,.app summary:focus-visible{outline:2px solid var(--ink);outline-offset:2px}.stage button:focus-visible,.stage canvas:focus-visible{outline-color:var(--glow)}
.top{display:none}
/* 좁은 화면: 이름 줄과 입력창만 고정하고 그 사이가 한 줄기로 흐른다 */
@media (max-width:900px){
body{overflow:auto}.app.app,.app[data-mode=talk]{display:block;height:auto;min-height:100dvh;padding:56px 0 150px}
.side{display:none}.top{display:flex;position:fixed;left:0;right:0;top:0;z-index:20;height:56px;align-items:center;justify-content:space-between;padding:0 16px;background:rgba(247,247,248,.94);backdrop-filter:blur(8px)}
.top .brand{padding:0;font-size:18px}.top button{height:40px;padding:0 14px;border-radius:20px;border:1px solid var(--line);background:#fff;font-size:13px}
.conv{padding:0 16px}.app[data-mode=empty] .conv{padding:8vh 16px 0;display:block}.hello h1{font-size:34px}.hello p{font-size:15px}.ideas{grid-template-columns:1fr}
.thread{overflow:visible;padding:16px 0 4px;-webkit-mask-image:none;mask-image:none}.me{font-size:15px}.bot .b{font-size:15px}
.dock{position:fixed;left:0;right:0;bottom:0;z-index:20;padding:10px 16px calc(14px + env(safe-area-inset-bottom));background:linear-gradient(rgba(247,247,248,0),var(--paper) 22%)}
.app[data-mode=empty] .dock{position:static;padding:0;background:none}
.sugg{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none}.sugg button{flex:none;white-space:nowrap}
.result{padding:8px 0 0}.rcard{padding:14px 14px 16px;border-radius:24px;gap:14px}.stage.stage,.rcard.open .stage.stage{flex:none;min-height:0}.stage .vp{height:auto}
.stage .tabs{gap:16px;padding:6px 16px 0;overflow-x:auto;scrollbar-width:none}.stage .tabs button{flex:none;white-space:nowrap;font-size:13px}.stage .pane{position:static;padding:4px 12px 12px}
.stage #pane-shape{position:relative}.stage .hint{display:none}.stage .key{position:static;padding:0 14px 12px;max-width:none}.stage .badge{display:none!important}
.stats{gap:12px;padding:0 2px}.stat{padding-left:12px}.stat .num{font-size:24px}.stat .k{font-size:12px}.seg{flex-direction:column}.seg button{flex:none}.thread .result{padding:0;display:block}.drawer{flex:none;overflow:visible;padding:4px 14px 14px}
#latest{position:fixed;left:50%;transform:translateX(-50%);bottom:150px;z-index:21}
}
@media (prefers-reduced-motion:reduce){*{animation-duration:.01s!important;transition-duration:.01s!important}}
"""

APP_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('app-data').textContent),cur=null,node=D.nodes[D.start],busy=false;
""" + _HELPERS + _VIEWER + r"""
var app=$('#app'),thread=$('#thread'),latest=$('#latest'),input=$('#say input'),btn=$('#say button'),card=$('#rcard');
var MARK=$('#mark').innerHTML,narrow=function(){return window.matchMedia('(max-width:900px)').matches;};
function lastBot(){var a=thread.querySelectorAll('.bot');return a[a.length-1];}
function atBottom(){if(narrow()){var b=lastBot();return !b||b.getBoundingClientRect().top<window.innerHeight;}return thread.scrollHeight-thread.scrollTop-thread.clientHeight<64;}
function toBottom(){if(narrow()){var b=lastBot();if(b)b.scrollIntoView({block:'start'});else window.scrollTo(0,document.documentElement.scrollHeight);}else thread.scrollTop=thread.scrollHeight;latest.hidden=true;}
function watch(){latest.hidden=atBottom()||app.dataset.mode!=='talk';}
thread.addEventListener('scroll',watch);window.addEventListener('scroll',watch);latest.addEventListener('click',toBottom);

/* ---------- 결과: 보기와 묶음 ---------- */
var tabs=document.querySelectorAll('.tabs button[data-v]');
function view(v){tabs.forEach(function(x){var on=x.dataset.v===v;x.setAttribute('aria-selected',on?'true':'false');if(on)x.classList.remove('new');});
document.querySelectorAll('.pane').forEach(function(p){p.classList.toggle('on',p.id==='pane-'+v);});if(v==='shape')V.draw();}
tabs.forEach(function(b){b.addEventListener('click',function(){view(b.dataset.v);});});
function dot(v,on){var b=$('.tabs button[data-v="'+v+'"]');if(b)b.classList.toggle('new',on&&b.getAttribute('aria-selected')!=='true');}
$('#xr').addEventListener('click',function(){var on=this.getAttribute('aria-pressed')!=='true';this.setAttribute('aria-pressed',on?'true':'false');V.hidden(on,cur?cur.hidden.use:0);});
var segs=document.querySelectorAll('.seg button'),drawer=$('#drawer');
function open(name){var same=name&&!drawer.hidden&&!$('#d-'+name).hidden;if(same)name=null;
segs.forEach(function(b){b.setAttribute('aria-expanded',b.dataset.d===name?'true':'false');});
['values','trust','sensing'].forEach(function(k){$('#d-'+k).hidden=k!==name;});drawer.hidden=!name;card.classList.toggle('open',!!name);if(name)drawer.scrollTop=0;setTimeout(V.draw,0);}
segs.forEach(function(b){b.addEventListener('click',function(){open(b.dataset.d);});});

/* ---------- 상태를 결과에 반영 ---------- */
function show(s,animate){var prev=cur;cur=s;
$('#rt').firstChild.nodeValue=s.size+' 볼트 조인트';$('#rsub').textContent='강도 등급 '+s.grade+' · '+s.sub;$('#now').textContent=s.size+' 볼트 조인트';
s.core.forEach(function(t,i){var el=$('#core'+i),v=$('.num',el),old=prev?prev.core[i]:null,from=old&&old.value!=null?old.value:t.value,ch=animate&&old&&t.value!=null&&fmt(from,t.digits)!==fmt(t.value,t.digits);
$('.k',el).textContent=t.label;$('.rg',el).textContent=t.range;$('.v',el).classList.toggle('low',!!t.low);
$('.dl',el).textContent=ch?((t.value>from?'+':'−')+fmt(Math.abs(t.value-from),t.digits)):'';
if(t.value==null)v.textContent='-';else if(ch)tween(750,function(e){v.textContent=fmt(from+(t.value-from)*e,t.digits);});else v.textContent=fmt(t.value,t.digits);});
$('#sensing').innerHTML=s.sensing;$('#trust').innerHTML=s.trust.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>';}).join('');
s.tiles.forEach(function(t,i){var el=$('#tile'+i),v=$('.num',el),dl=$('.dl',el),from=prev?prev.tiles[i].value:t.value,ch=animate&&prev&&fmt(from,t.digits)!==fmt(t.value,t.digits);
$('.rg',el).textContent=t.range||'';el.classList.toggle('moved',!!ch);dl.textContent=ch?('이전 '+fmt(from,t.digits)):'';v.textContent=fmt(t.value,t.digits);});
var top=Math.max.apply(null,s.safety.map(function(x){return x.value||0;}).concat(prev?prev.safety.map(function(x){return x.value||0;}):[]).concat([2]))*1.05;
s.safety.forEach(function(x,i){var r=$('#sf'+i),f=$('.fill',r),n=$('.n',r),was=$('.was',r),old=prev?prev.safety[i].value:null;
r.classList.toggle('off',x.value==null);r.title=x.value==null?x.note:'';var ch=animate&&old!=null&&x.value!=null&&fmt(old,2)!==fmt(x.value,2);r.classList.toggle('moved',!!ch);if(ch)was.style.left=(Math.min(old/top,1)*100)+'%';
$('.one',r).style.left=(100/top)+'%';f.style.width=(x.value==null?0:Math.min(x.value/top,1)*100)+'%';f.classList.toggle('low',x.value!=null&&x.value<1);n.classList.toggle('low',x.value!=null&&x.value<1);n.textContent=x.value==null?'-':fmt(x.value,2);});
['section','diagram','torque','field'].forEach(function(k){var box=$('#sw-'+k),ch=animate&&prev&&prev.views[k]!==s.views[k];dot(k==='diagram'||k==='torque'?'graph':k,!!ch);box.innerHTML=s.views[k];});
V.hidden($('#xr').getAttribute('aria-pressed')==='true',s.hidden.use);$('#useat').style.left=(Math.min(s.hidden.use,1)*100)+'%';$('#usev').textContent=fmt(s.hidden.use,2);$('#usedet').textContent=fmt(s.hidden.stress,0)+' ÷ '+fmt(s.hidden.yield,0)+' MPa';
V.set(s.viewer,animate&&!!prev);V.mark(animate?s.marks:{glow:[],tags:[],notes:[]});dot('shape',animate&&s.marks.glow.length>0);
$('#more').innerHTML=s.more;}

/* ---------- 대화 ---------- */
function addUser(t){var el=document.createElement('div');el.className='me';el.textContent=t;thread.appendChild(el);toBottom();}
function addBot(m){var stick=atBottom(),b=m.brief,h='<div>'+esc(m.talk.text)+(m.talk.alert?' <span class="al'+(m.talk.alert_low?' low':'')+'">'+esc(m.talk.alert)+'</span>':'')+'</div>';
if(b&&b.chips.length)h+='<div class="cells">'+b.chips.slice(0,3).map(function(c){var low=c.label.indexOf('안전율')>=0&&c.to<1;return '<div class="cell'+(low?' low':'')+'"><div class="k">'+esc(c.label)+(c.unit?' ('+esc(c.unit)+')':'')+'</div><div class="v"><s>'+fmt(c.from,c.digits)+'</s><b>'+fmt(c.to,c.digits)+'</b></div></div>';}).join('')+'</div>';
if(b&&b.options.length)h+='<div class="opts"><div class="cand">생성 후보입니다. 같은 계산식으로 구한 대안이며 검증 전입니다.</div>'+b.options.map(function(o){return '<button type="button" data-say="'+esc(o.say)+'"><b>'+o.n+'번</b> '+esc(o.what)+'<span class="d">'+esc(o.detail)+'</span></button>';}).join('')+'</div>';
if(m.detail)h+='<details><summary>자세히</summary><pre>'+esc(m.detail)+'</pre></details>';
var el=document.createElement('div');el.className='bot';el.innerHTML=MARK+'<div class="b">'+h+'</div>';thread.appendChild(el);if(narrow())return;if(stick)toBottom();else latest.hidden=false;}
function suggest(list){var box=$('#sugg');box.innerHTML=(list||[]).map(function(t){return '<button type="button" data-say="'+esc(t)+'">'+esc(t)+'</button>';}).join('');}
function apply(m){if(app.dataset.mode!=='talk'){app.dataset.mode='talk';input.placeholder='이어서 말해 보세요';}
if(m.state&&m.state!==cur)show(m.state,true);addBot(m);if(m.ui){if(m.ui.view){drawer.hidden=true;open(null);}if(m.ui.view)view(m.ui.view==='diagram'||m.ui.view==='torque'?'graph':m.ui.view);if(m.ui.open){drawer.hidden=true;open(m.ui.open);}}
suggest(m.suggest);place();if(narrow())toBottom();}
var result=$('.result');
function place(){if(narrow()){if(app.dataset.mode==='talk')thread.appendChild(result);}else if(result.parentNode!==app)app.appendChild(result);V.draw();}
window.matchMedia('(max-width:900px)').addEventListener('change',place);
function lock(on){busy=on;input.disabled=btn.disabled=on;}
function send(text){text=(text||'').trim();if(!text||busy)return;addUser(text);input.value='';
if(app.dataset.mode!=='talk'){app.dataset.mode='talk';}
if(D.ask_url){lock(true);fetch(D.ask_url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text})}).then(function(r){return r.json();})
.then(function(m){apply(m);}).catch(function(){addBot({talk:{text:'답을 받지 못했습니다.',alert:'서버가 켜져 있는지 확인해 주세요.',alert_low:true}});}).then(function(){lock(false);if(!narrow())input.focus();});return;}
var id=node.next[text];
if(id==null){addBot({talk:{text:'이 화면은 미리 만든 대화를 보여 주는 공개 시연입니다. 아래 추천 문구를 눌러 주세요. 직접 말로 바꿔 보려면 코드를 받아 실행하면 됩니다.',alert:'',alert_low:false}});suggest(Object.keys(node.next));return;}
node=D.nodes[id];apply({state:D.states[node.sid],talk:node.talk,brief:node.brief,ui:node.ui,detail:node.detail,suggest:Object.keys(node.next)});}
$('#say').addEventListener('submit',function(e){e.preventDefault();send(input.value);});
document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('[data-say]');if(b&&!b.disabled)send(b.dataset.say);});
function fresh(){if(D.ask_url){fetch(D.reset_url,{method:'POST'}).then(function(){location.reload();},function(){location.reload();});}else location.reload();}
document.querySelectorAll('[data-new]').forEach(function(b){b.addEventListener('click',fresh);});
show(D.states[node.sid],false);suggest(D.ask_url?node.suggest:Object.keys(node.next));
if(!D.ask_url)input.placeholder='추천 문구를 눌러 보세요';
document.body.dataset.ready='1';
})();
"""

CHEV = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
UP = '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 15.5V5M5.5 9.5L10 5l4.5 4.5" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
PLUS = '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M9 3.5v11M3.5 9h11" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>'
DOWN = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v9M4 8.5L8 12.5l4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def render_app(data: Mapping[str, Any], ask_url: str | None = None, title: str = "ConT · 볼트 조인트",
               links: Mapping[str, str] | None = None, downloads: tuple[tuple[str, str], ...] = ()) -> str:
    """data: {"states": {sid: state}, "nodes": {nid: {sid, talk, brief, ui, detail, suggest, next}}, "start": nid}.

    ask_url이 있으면 말을 서버에 보내 그 답으로 바뀐다. 없으면 nodes의 next를 따라가며 미리 만든 대화를 보여 준다.
    """
    e = html.escape
    first = data["states"][data["nodes"][data["start"]]["sid"]]
    links = links or {}

    def tile(i: int, t: dict[str, Any]) -> str:
        return (f'<div class="r" id="tile{i}"><div class="k">{e(t["label"])}</div><div class="v"><span class="num"></span><span class="u">{e(t["unit"])}</span></div>'
                f'<div class="rg"></div><div class="dl"></div></div>')

    why = {"hidden": "조임 토크는 잴 수 있지만, 그 토크가 만든 체결력은 직접 잴 수 없습니다. 아래는 관측으로 복원한 값이 아니라 계산 모형으로 구한 값입니다.",
           "seen": "지금은 센서로 관측한 값이 아니라 사람이 넣은 값입니다."}
    groups = "".join(f'<h3>{e(name)}<small>{e(status)} · {e(desc)}</small></h3><p class="why">{e(why[key])}</p><div class="read">'
                     + "".join(tile(i, t) for i, t in enumerate(first["tiles"]) if t["group"] == key) + "</div>" for key, name, status, desc in GROUPS)
    rows = "".join(f'<div class="row" id="sf{i}"><div>{e(s["label"])}</div><div class="bar"><div class="fill"></div><div class="was"></div><div class="one"></div></div>'
                   f'<div class="n"></div></div>' for i, s in enumerate(first["safety"]))
    stats = "".join(f'<div class="stat" id="core{i}"><div class="k"></div><div class="v"><span class="num"></span><span class="u">{e(c["unit"])}</span><span class="dl"></span></div>'
                    f'<div class="rg"></div></div>' for i, c in enumerate(first["core"]))
    files = "".join(f' <a href="{e(u)}" download>{e(n)} 내려받기</a>' for n, u in downloads)
    nav = "".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a>' for n, u in links.items())
    ideas = "".join(f'<button type="button" data-say="{e(t)}"><b>{e(t)}</b><span>{e(s)}</span></button>' for t, s in IDEAS)
    payload = dict(data, ask_url=ask_url, reset_url="/reset" if ask_url else None)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = f"""<div class="top"><div class="brand">{MARK}ConT</div><button type="button" data-new>새 설계</button></div>
<div class="app" id="app" data-mode="empty">
<aside class="side"><div class="brand">{MARK}ConT</div><button type="button" class="new" data-new>{PLUS}새 설계</button>
<div class="cur">지금 설계</div><div class="now" id="now"></div><nav aria-label="바로가기">{nav}</nav></aside>
<main class="conv">
<div class="hello"><h1>무엇을 설계할까요?</h1><p>말로 설명하면 물리로 계산하고, 3D와 물리 이미지로 보여 드립니다.</p></div>
<div class="thread" id="thread" tabindex="0" role="log" aria-live="polite" aria-label="대화"></div>
<button type="button" id="latest" hidden>{DOWN}최신 답으로</button>
<div class="dock"><div class="sugg" id="sugg" aria-label="이렇게 말해 보세요"></div>
<form id="say" class="say"><input type="text" aria-label="말로 설계하기" placeholder="볼트 조인트를 말로 설명해 보세요" autocomplete="off"><button type="submit" aria-label="보내기">{UP}</button></form></div>
<div class="ideas">{ideas}</div>
<p class="fine">모든 값은 계산값입니다. 실측과 대조하기 전이므로 설계 판단의 근거로 쓰지 않습니다.</p>
</main>
<section class="result" aria-label="결과"><div class="rcard" id="rcard">
<div class="rhead"><h2 id="rt">&#8203;<small id="rsub"></small></h2><span class="state">계산값 · 검증 전</span></div>
<div class="stage">
<div class="tabs" role="tablist" aria-label="보기"><button type="button" role="tab" data-v="shape" aria-selected="true">3D CAD</button>
<button type="button" role="tab" data-v="section" aria-selected="false">단면</button><button type="button" role="tab" data-v="graph" aria-selected="false">그래프</button>
<button type="button" role="tab" data-v="field" aria-selected="false">물리 이미지</button><span class="sp"></span><button type="button" class="xr" id="xr" aria-pressed="true">숨은 물리</button></div>
<div class="vp">
<div class="pane on" id="pane-shape"><canvas id="cv" tabindex="0" role="img" aria-label="볼트 조인트 3D 형상. 끌거나 화살표 키로 돌리고 휠이나 +, - 키로 확대합니다"></canvas>
<div class="notes" id="notes" aria-live="polite"></div><div class="hint"><span id="cvmsg"></span>끌어서 돌리고 휠로 확대합니다.{files}</div>
<div class="key"><div>볼트의 색: 등가응력 ÷ 항복강도 <b id="usev"></b> <span id="usedet"></span></div><div class="sc"><i id="useat"></i></div><div class="ends"><span>0</span><span>1.0</span></div>
<div class="z"><i></i>판이 눌리는 영역. 계산 모형의 모양이며 관측한 것이 아닙니다.</div></div>
<div class="badge">숨은 물리 <b>해석</b> · 관측 없음</div></div>
<div class="pane" id="pane-section"><div class="swap" id="sw-section"></div></div>
<div class="pane" id="pane-graph"><div class="graphs"><div class="swap" id="sw-diagram"></div><div class="swap" id="sw-torque"></div></div></div>
<div class="pane" id="pane-field"><div class="swap" id="sw-field"></div></div>
</div></div>
<div class="stats">{stats}</div>
<div class="seg"><button type="button" data-d="values" aria-expanded="false" aria-controls="drawer">값 전체{CHEV}</button>
<button type="button" data-d="trust" aria-expanded="false" aria-controls="drawer">믿어도 되는가{CHEV}</button>
<button type="button" data-d="sensing" aria-expanded="false" aria-controls="drawer">현장에서 재려면{CHEV}</button></div>
<div class="drawer" id="drawer" hidden tabindex="0">
<div id="d-values" hidden>{groups}<h3>결과: 안전율<small>해석 · 검은 선이 1.0</small></h3><div class="gauges">{rows}</div><div id="more"></div></div>
<div id="d-trust" hidden><dl class="tr" id="trust"></dl></div>
<div id="d-sensing" hidden><div id="sensing"></div></div>
</div>
</div></section>
</div>
<template id="mark">{MARK}</template>
<script type="application/json" id="app-data">{blob}</script><script>{APP_JS}</script>"""
    fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">')
    return (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            f"<title>{e(title)}</title>{fonts}<style>{CSS}{EXTRA_CSS}{LIVE_CSS}{FIELD_CSS}{APP_CSS}</style></head><body>\n{body}\n</body></html>")
